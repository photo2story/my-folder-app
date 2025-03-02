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
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH, DISCORD_WEBHOOK_URL, STATIC_DATA_PATH
from config_assets import DOCUMENT_TYPES
import logging
import pandas as pd
import orjson
import time

# JSON 파일 저장 경로 설정
RESULTS_DIR = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self):
        self.searcher = ProjectDocumentSearcher(verbose=False)

    async def _get_session(self):
        """aiohttp 세션 관리"""
        return aiohttp.ClientSession()

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

    async def send_to_discord(self, data):
        """디스코드로 결과 전송 (간소화)"""
        if not DISCORD_WEBHOOK_URL:
            print(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2))
            return

        async with aiohttp.ClientSession() as session:
            try:
                message = (
                    f"📋 **Project Audit Result**\n"
                    f"ID: {data['project_id']}\n"
                    f"Department: {data['department']}\n"
                    f"Name: {data['project_name']}\n"
                    f"Path: {data['original_folder']}\n\n"
                    f"📑 Documents:\n"
                )

                found_docs = []
                missing_docs = []
                for doc_type, doc_list in data['documents'].items():
                    doc_name = DOCUMENT_TYPES[doc_type]['name']
                    if doc_list:  # 리스트가 비어있지 않으면 발견된 것으로 간주
                        found_docs.append(f"{doc_name} ({len(doc_list)}개)")
                    else:
                        missing_docs.append(doc_name)

                if found_docs:
                    message += "✅ Found:\n- " + "\n- ".join(found_docs) + "\n\n"
                if missing_docs:
                    message += "❌ Missing:\n- " + "\n- ".join(missing_docs)

                message += f"\n⏰ {data['timestamp']}"

                async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=10) as response:
                    if response.status != 204:
                        logger.warning(f"Webhook response status: {response.status}")
                        print(message)
            except Exception as e:
                logger.error(f"Discord send error: {str(e)}")
                print(message)

    async def get_project_info_by_dept(self, project_id, department_code=None):
        """프로젝트 정보 조회 (간소화)"""
        numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
        df = pd.read_csv(PROJECT_LIST_CSV, dtype={'department_code': str, 'project_id': str})
        
        if department_code:
            department_code = str(department_code).zfill(5)
            project = df[(df['project_id'] == numeric_project_id) & (df['department_code'].str.zfill(5) == department_code)]
        else:
            project = df[df['project_id'] == numeric_project_id]

        if len(project) == 0:
            logger.error(f"Project ID {numeric_project_id} not found for department {department_code}")
            return None

        row = project.iloc[0]
        full_path = os.path.join(NETWORK_BASE_PATH, str(row['original_folder']))
        return {
            'project_id': str(row['project_id']),
            'department_code': str(row['department_code']).zfill(5),
            'department_name': str(row['department_name']),
            'project_name': str(row['project_name']),
            'original_folder': full_path
        }

    async def audit_project(self, project_id, department_code=None, use_ai=False):
        start_time = time.time()
        try:
            logger.info(f"\n=== 프로젝트 {project_id} (ID: {re.sub(r'[^0-9]', '', str(project_id))}) 감사 시작 ===")
            
            # 프로젝트 정보 조회
            project_info = await self.get_project_info_by_dept(project_id, department_code)
            if not project_info:
                raise ValueError(f'Project ID {project_id} not found for department {department_code}')
            
            # 문서 검색 (search_project_data.py에서 가져옴, 리스트 형식 유지)
            search_start = time.time()
            search_result = await self.searcher.search_all_documents(project_info['project_id'], project_info['department_code'])
            search_time = time.time() - search_start
            
            if not search_result or 'documents' not in search_result:
                raise ValueError(f"문서 검색 결과가 유효하지 않습니다: {project_id}")
            
            documents = search_result['documents']  # 리스트 형식 그대로 사용 (search_project_data.py와 동일)
            total_files = sum(len(doc_list) for doc_list in documents.values() if doc_list)
            found_count = sum(1 for doc_list in documents.values() if doc_list)
            
            logger.info(f"\n=== 문서 검색 완료 ({search_time:.2f}초) ===")
            logger.info(f"- 발견된 문서 유형: {found_count}/{len(DOCUMENT_TYPES)}개")
            logger.info(f"- 총 발견 파일 수: {total_files}개")
            
            # AI 분석 (옵션)
            ai_analysis = None
            ai_time = 0
            if use_ai:
                logger.info("\n=== AI 분석 시작 ===")
                ai_start = time.time()
                ai_input = {
                    'project_id': project_id,
                    'project_info': project_info,
                    'documents': documents
                }
                ai_analysis = await analyze_with_gemini(ai_input, await self._get_session())
                ai_time = time.time() - ai_start
                logger.info(f"=== AI 분석 완료 ({ai_time:.2f}초) ===")
            
            # 결과 구성 (documents를 리스트로 유지)
            result = {
                'project_id': project_info['project_id'],
                'project_name': project_info['project_name'],
                'department': f"{project_info['department_code']}_{project_info['department_name']}",
                'documents': documents,  # 리스트 형식 유지
                'original_folder': project_info['original_folder'],
                'ai_analysis': ai_analysis if use_ai else None,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance': {
                    'total_time': time.time() - start_time,
                    'search_time': search_time,
                    'ai_time': ai_time,
                    'save_time': 0
                }
            }
            
            # 결과 저장
            save_start = time.time()
            json_path = await self.save_audit_result(result, project_info['department_code'])
            if json_path:
                result['json_file'] = json_path
                result['performance']['save_time'] = time.time() - save_start
                logger.info(f"\n결과 저장 완료: {json_path}")
            
            # Discord로 결과 전송
            await self.send_to_discord(result)
            
            logger.info(f"\n=== 감사 완료 ({result['performance']['total_time']:.2f}초) ===")
            logger.info(f"- 총 소요 시간: {result['performance']['total_time']:.2f}초")
            logger.info(f"- 문서 검색 시간: {search_time:.2f}초")
            logger.info(f"- AI 분석 시간: {ai_time:.2f}초")
            logger.info(f"- JSON 저장 시간: {result['performance']['save_time']:.2f}초")
            logger.info(f"- 발견된 문서 유형: {found_count}/{len(DOCUMENT_TYPES)}개")
            logger.info(f"- 총 발견 파일 수: {total_files}개")

            return result
            
        except Exception as e:
            error_msg = f"프로젝트 {project_id} 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            error_result = {
                'error': str(e),
                'project_id': project_id,
                'department_code': department_code,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance': {'total_time': time.time() - start_time}
            }
            await self.send_to_discord(error_result)
            return error_result

    async def audit_multiple_projects(self, project_ids, department_codes, use_ai=False):
        """다중 프로젝트 배치 감사 (병렬 처리)"""
        numeric_project_ids = [re.sub(r'[^0-9]', '', str(pid)) for pid in project_ids]
        tasks = [asyncio.create_task(self.audit_project(pid, dept, use_ai)) for pid, dept in zip(numeric_project_ids, department_codes)]
        return await asyncio.gather(*tasks)

    async def process_audit_targets(self, filters=None, use_ai=False):
        """감사 대상 리스트를 생성하고 배치로 감사 수행"""
        from audit_target_generator import select_audit_targets  # 동적 임포트

        try:
            audit_targets_df, project_ids, department_codes = select_audit_targets(filters)
            numeric_project_ids = [re.sub(r'[^0-9]', '', str(pid)) for pid in project_ids]
            results = await self.audit_multiple_projects(numeric_project_ids, department_codes, use_ai)
            
            audit_targets_df['AuditResult'] = [
                result.get('ai_analysis', 'No result') if 'error' not in result else f"Error: {result['error']}"
                for result in results
            ]
            
            output_csv = os.path.join(STATIC_DATA_PATH, 'audit_results.csv')
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
    
    logger.info("=== 프로젝트 문서 검색 시작 ===")
    service = AuditService()
    
    if args.project_id:
        numeric_project_ids = [re.sub(r'[^0-9]', '', str(pid)) for pid in args.project_id]
        department_codes = args.department_code if args.department_code else [None] * len(numeric_project_ids)
        if len(department_codes) != len(numeric_project_ids):
            raise ValueError("부서 코드와 프로젝트 ID의 개수가 일치해야 합니다.")
        
        if len(numeric_project_ids) == 1:
            asyncio.run(service.audit_project(args.project_id[0], department_codes[0], args.use_ai))
        else:
            asyncio.run(service.audit_multiple_projects(numeric_project_ids, department_codes, args.use_ai))
    else:
        asyncio.run(service.process_audit_targets(use_ai=args.use_ai))
    
    logger.info("\n=== 검색 완료 ===")
    
# python audit_service.py
# python audit_service.py --project-id 20180076 --department-code 01010 --use-ai
# python audit_service.py --project-id 20240178 --department-code 06010 --use-ai
# python audit_service.py --project-id 20240178 --use-ai