# /my_flask_app/audit_service.py


import os
import asyncio
import aiofiles
from datetime import datetime
import json
import aiohttp
import re
from pathlib import Path
from search_project_data import ProjectDocumentSearcher
from gemini import analyze_with_gemini
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH, DISCORD_WEBHOOK_URL, STATIC_DATA_PATH, CONTRACT_STATUS_CSV
from config_assets import DOCUMENT_TYPES, DEPARTMENT_MAPPING, DEPARTMENT_NAMES, AUDIT_FILTERS  # AUDIT_FILTERS 추가
import logging
import pandas as pd
import orjson
import time
from get_project import get_project_info  # get_project.py에서 함수 임포트

# JSON 파일 저장 경로 설정
RESULTS_DIR = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self):
        self.searcher = ProjectDocumentSearcher(verbose=False)
        self._session = None

    async def _get_session(self):
        """aiohttp 세션 관리"""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """세션 정리"""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def save_audit_result(self, result, department_code):
        """감사 결과를 JSON으로 저장"""
        project_id = result['project_id']
        filename = f"audit_{department_code}_{project_id}.json"
        filepath = Path(RESULTS_DIR) / filename
        
        if not os.path.exists(RESULTS_DIR):
            os.makedirs(RESULTS_DIR, exist_ok=True)
        
        json_data = orjson.dumps(result, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS).decode('utf-8')
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(json_data)
        return str(filepath)

    async def send_to_discord(self, data, ctx=None):
        """디스코드로 결과 전송 (ctx가 있으면 채널에 직접 전송, 없으면 웹훅 사용, 데이터 유형 처리 개선)"""
        # data가 리스트일 경우 각 요소를 개별적으로 처리
        if isinstance(data, list):
            success = True
            for item in data:
                if not await self._send_single_to_discord(item, ctx):
                    success = False
            return success
        else:
            return await self._send_single_to_discord(data, ctx)

    async def _send_single_to_discord(self, data, ctx=None):
        """단일 감사 결과를 Discord로 전송 (내부 함수)"""
        if not isinstance(data, dict):
            logger.error(f"Invalid audit data format: {data}")
            return False

        message = (
            f"📋 **Project Audit Result**\n"
            f"ID: {data.get('project_id', 'Unknown')}\n"
            f"Department: {data.get('department', data.get('department_code', 'Unknown'))}\n"
            f"Name: {data.get('project_name', f'Project {data.get('project_id', 'Unknown')}')}\n"
            f"Path: {data.get('project_path', 'Unknown')}\n\n"  # 'original_folder' 대신 'project_path' 사용
            f"📑 Documents:\n"
        )

        found_docs = []
        missing_docs = []
        documents = data.get('documents', {})
        for doc_type, doc_info in documents.items():
            doc_name = DOCUMENT_TYPES.get(doc_type, {}).get('name', doc_type)
            if doc_info.get('exists', False):  # exists가 True인 경우
                found_docs.append(f"{doc_name} ({len(doc_info.get('details', []))}개)")
            else:
                missing_docs.append(doc_name)

        if found_docs:
            message += "✅ Found:\n- " + "\n- ".join(found_docs) + "\n\n"
        if missing_docs:
            message += "❌ Missing:\n- " + "\n- ".join(missing_docs)

        if 'ai_analysis' in data and data['ai_analysis']:
            message += f"\n🤖 AI Analysis:\n{data['ai_analysis']}"

        message += f"\n⏰ {data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"

        try:
            if ctx:
                # ctx가 있는 경우 디스코드 채널에 직접 메시지 전송
                await ctx.send(message)
                logger.info(f"Sent audit result to Discord channel: {message}")
            elif DISCORD_WEBHOOK_URL:
                # ctx가 없으면 웹훅으로 전송
                async with aiohttp.ClientSession() as session:
                    async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=10) as response:
                        if response.status != 204:
                            logger.warning(f"Webhook response status: {response.status}")
                            print(f"Failed to send to Discord webhook: {message}")
                            return False
                logger.info("Audit result successfully sent to Discord webhook")
            else:
                print(message)
            return True
        except Exception as e:
            logger.error(f"Error sending to Discord: {str(e)}")
            if ctx:
                await ctx.send(f"❌ 디스코드 전송 오류: {str(e)}")
            else:
                print(f"Failed to send to Discord: {message}")
            return False

    async def search_projects_by_id(self, project_id, department_code=None):
        """project_id와 department_code를 기반으로 프로젝트 정보 및 폴더를 찾아 검색 (get_project_info 사용, process_single_project 호출, max_found=3 고정)"""
        numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
        projects = []
        
        # 1) get_project_info를 호출하여 프로젝트 정보 찾기 (비동기 처리로 변환, department_code 동적 전달)
        loop = asyncio.get_event_loop()
        project_info = await loop.run_in_executor(None, lambda: get_project_info(project_id, department_code=department_code))
        if not project_info:
            logger.error(f"Project ID {numeric_project_id} not found in project list or contract status for department {department_code or '01010'}")
            return projects

        # 부서 코드와 프로젝트 경로 추출
        dept_code = project_info['department_code']
        dept_name = project_info['department_name']
        folder_path = project_info['original_folder']
        
        # 경로 존재 여부 확인
        if not await asyncio.to_thread(os.path.exists, folder_path):
            logger.error(f"Project folder does not exist: {folder_path}")
            return projects

        # 2) search_project_data.py의 process_single_project 호출 (project_id와 department_code 동적 전달, max_found=3 고정)
        search_result = await self.searcher.process_single_project(project_id, department_code)
        if search_result and 'documents' in search_result:
            documents = search_result['documents']
            total_files = sum(len(doc_info) for doc_info in documents.values() if doc_info)  # process_single_project의 반환 형식 반영
            if total_files > 0:
                projects.append({
                    'project_id': numeric_project_id,
                    'department_code': dept_code,
                    'department_name': dept_name,
                    'project_name': project_info['project_name'],
                    'original_folder': folder_path,
                    'documents': documents
                })
                logger.info(f"Found project path for {numeric_project_id} in {dept_code}_{dept_name}: {folder_path}")
        
        return projects

    async def audit_project(self, project_id, department_code=None, use_ai=False, ctx=None):
        """단일 프로젝트 감사 (project_id와 부서 코드를 기반으로 검색 및 처리, use-ai 옵션으로 제미니 분석 추가)"""
        start_time = time.time()
        try:
            logger.info(f"\n=== 프로젝트 {project_id} (ID: {re.sub(r'[^0-9]', '', str(project_id))}) 감사 시작 ===")
            
            if ctx:
                await ctx.send(f"🔍 프로젝트 {project_id} 감사를 시작합니다...")

            # project_id와 department_code로 부서와 폴더를 찾아 검색
            projects = await self.search_projects_by_id(project_id, department_code)
            if not projects:
                raise ValueError(f'Project ID {project_id} not found in project list or contract status for department {department_code or "01010"}')
            
            # 부서별로 감사 수행 (중복 제거)
            all_results = []
            for project_info in projects:
                result = {
                    'project_id': project_info.get('project_id'),
                    'project_name': project_info.get('project_name'),
                    'department': f"{project_info.get('department_code')}_{project_info.get('department_name')}",
                    'documents': {},
                    'project_path': project_info.get('original_folder'),
                    'ai_analysis': None,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'performance': {
                        'total_time': 0,
                        'search_time': 0,
                        'ai_time': 0,
                        'save_time': 0
                    }
                }
                
                # 문서 검색 시간 (이미 search_projects_by_id에서 수행)
                search_time = time.time() - start_time
                
                # documents 데이터 구조화 (gemini.py가 기대하는 형식으로 변환)
                for doc_type, doc_data in project_info['documents'].items():
                    if isinstance(doc_data, list):  # 리스트로 반환된 경우
                        result['documents'][doc_type] = {
                            'exists': len(doc_data) > 0,
                            'details': [{'name': path} for path in doc_data]
                        }
                    elif isinstance(doc_data, dict):  # 이미 딕셔너리로 반환된 경우
                        result['documents'][doc_type] = {
                            'exists': doc_data.get('exists', False),
                            'details': [{'name': path} for path in doc_data.get('details', []) if isinstance(path, str)] or []
                        }
                    else:
                        logger.warning(f"Unknown documents format for {doc_type}: {doc_data}")
                        result['documents'][doc_type] = {
                            'exists': False,
                            'details': []
                        }
                
                # AI 분석 (use-ai 옵션에 따라 조건부 실행)
                ai_analysis = None
                ai_time = 0
                if use_ai:
                    if ctx:
                        await ctx.send(f"\n=== AI 분석 시작 ({project_info['department_name']}) ===")
                    logger.info(f"\n=== AI 분석 시작 ({project_info['department_name']}) ===")
                    ai_start = time.time()
                    
                    # AI 분석을 위한 데이터 구조화
                    ai_input = {
                        'project_id': project_info['project_id'],
                        'department': project_info['department_name'],
                        'project_name': project_info['project_name'],
                        'documents': result['documents']  # 구조화된 documents 사용
                    }
                    
                    try:
                        ai_analysis = await analyze_with_gemini(ai_input, await self._get_session())
                    except Exception as e:
                        logger.error(f"AI 분석 오류: {str(e)}")
                        ai_analysis = f"AI 분석 중 오류 발생: {str(e)}"
                    
                    ai_time = time.time() - ai_start
                    if ctx:
                        await ctx.send(f"=== AI 분석 완료 ({ai_time:.2f}초) ({project_info['department_name']})\nAI Analysis: {ai_analysis}")
                    logger.info(f"=== AI 분석 완료 ({ai_time:.2f}초) ({project_info['department_name']})\nAI Analysis: {ai_analysis}")
                
                result['ai_analysis'] = ai_analysis if use_ai else None
                result['performance']['search_time'] = search_time
                result['performance']['ai_time'] = ai_time
                
                # 결과 저장
                save_start = time.time()
                json_path = await self.save_audit_result(result, project_info['department_code'])
                if json_path:
                    result['result_file'] = json_path  # 'json_file' 대신 'result_file' 사용
                    result['performance']['save_time'] = time.time() - save_start
                    if ctx:
                        await ctx.send(f"\n결과 저장 완료 ({project_info['department_name']}): {json_path}")
                    logger.info(f"\n결과 저장 완료 ({project_info['department_name']}): {json_path}")
                
                # Discord로 결과 전송
                await self.send_to_discord(result, ctx)
                result['performance']['total_time'] = time.time() - start_time
                all_results.append(result)
            
            if ctx:
                await ctx.send(f"\n=== 모든 부서에 대한 감사 완료 ({time.time() - start_time:.2f}초) ===")
            
            logger.info(f"\n=== 모든 부서에 대한 감사 완료 ({time.time() - start_time:.2f}초) ===")
            logger.info(f"- 총 소요 시간: {time.time() - start_time:.2f}초")
            logger.info(f"- 발견된 부서: {len(projects)}개")
            logger.info(f"- 총 발견 파일 수: {sum(len(doc_info.get('details', [])) for p in projects for doc_info in p['documents'].values() if isinstance(doc_info, dict))}")

            return all_results[0] if len(all_results) == 1 else all_results
            
        except Exception as e:
            error_msg = f"프로젝트 {project_id} 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            if ctx:
                await ctx.send(f"❌ 오류 발생: {error_msg}")
            error_result = {
                'error': str(e),
                'project_id': project_id,
                'department_code': department_code,
                'department': f"{department_code}_{DEPARTMENT_NAMES.get(department_code, 'Unknown')}" if department_code else 'Unknown',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance': {'total_time': time.time() - start_time}
            }
            await self.send_to_discord(error_result, ctx)
            return error_result

    async def audit_multiple_projects(self, project_ids, department_codes, use_ai=False):
        """다중 프로젝트 배치 감사 (병렬 처리)"""
        numeric_project_ids = [re.sub(r'[^0-9]', '', str(pid)) for pid in project_ids]
        tasks = [asyncio.create_task(self.audit_project(pid, dept, use_ai)) for pid, dept in zip(numeric_project_ids, department_codes)]
        return await asyncio.gather(*tasks)

    async def process_audit_targets(self, filters=None, use_ai=False):
        """감사 대상 리스트를 생성하고 배치로 감사 수행 (권한 문제 해결)"""
        from audit_target_generator import select_audit_targets  # 동적 임포트

        try:
            # static/data 디렉토리 존재 여부 및 권한 확인
            data_dir = os.path.join(STATIC_DATA_PATH, 'data')
            os.makedirs(data_dir, exist_ok=True)  # 디렉토리 생성, 이미 존재하면 무시
            
            # 권한 확인 및 수정 (Windows에서 필요 시)
            if not os.access(data_dir, os.W_OK):
                logger.warning(f"No write permission for {data_dir}. Attempting to change permissions...")
                try:
                    import stat
                    os.chmod(data_dir, stat.S_IWRITE | stat.S_IREAD)
                    logger.info(f"Permissions updated for {data_dir}")
                except Exception as e:
                    logger.error(f"Failed to update permissions for {data_dir}: {str(e)}")
                    raise

            # 감사 대상 선택
            audit_targets_df, project_ids, department_codes = select_audit_targets(filters or AUDIT_FILTERS)
            numeric_project_ids = [re.sub(r'[^0-9]', '', str(pid)) for pid in project_ids]
            results = await self.audit_multiple_projects(numeric_project_ids, department_codes, use_ai)
            
            # 결과 저장
            audit_targets_df['AuditResult'] = [
                result.get('ai_analysis', 'No result') if 'error' not in result else f"Error: {result['error']}"
                for result in results
            ]
            
            output_csv = os.path.join(STATIC_DATA_PATH, 'data', 'audit_results.csv')  # data 서브디렉토리 사용
            audit_targets_df.to_csv(output_csv, index=False, encoding='utf-8-sig')
            logger.info(f"감사 결과가 {output_csv}에 저장되었습니다. 총 프로젝트 수: {len(audit_targets_df)}")
            return audit_targets_df, results
            
        except Exception as e:
            logger.error(f"감사 대상 처리 오류: {str(e)}")
            return None, None

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="프로젝트 문서 검색")
    parser.add_argument('--project-id', type=str, nargs='+', required=False, help="검색할 프로젝트 ID (여러 개 가능)")
    parser.add_argument('--department-code', type=str, nargs='+', default=None, help="부서 코드 (여러 개 가능, 예: 01010, 06010)")
    parser.add_argument('--use-ai', action='store_true', help="AI 분석 사용")
    args = parser.parse_args()
    
    async def main():
        logger.info("=== 프로젝트 문서 검색 시작 ===")
        service = AuditService()
        
        try:
            if args.project_id:
                numeric_project_ids = [re.sub(r'[^0-9]', '', str(pid)) for pid in args.project_id]
                department_codes = args.department_code if args.department_code else [None] * len(numeric_project_ids)
                if len(department_codes) != len(numeric_project_ids):
                    raise ValueError("부서 코드와 프로젝트 ID의 개수가 일치해야 합니다.")
                
                if len(numeric_project_ids) == 1:
                    await service.audit_project(args.project_id[0], department_codes[0], args.use_ai, ctx=None)
                else:
                    await service.audit_multiple_projects(numeric_project_ids, department_codes, args.use_ai)
            else:
                await service.process_audit_targets(use_ai=args.use_ai)
        finally:
            await service.close()
            logger.info("\n=== 검색 완료 ===")
    
    asyncio.run(main())
    
# python audit_service.py
# python audit_service.py --project-id 20180076 --department-code 01010 --use-ai
# python audit_service.py --project-id 20240178 --use-ai
# python audit_service.py --project-id 20240178 --department-code 06010 --use-ai
# python audit_service.py --project-id 20240178 --use-ai