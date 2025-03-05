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
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH, DISCORD_WEBHOOK_URL, STATIC_DATA_PATH,STATIC_PATH, CONTRACT_STATUS_CSV
from config_assets import DOCUMENT_TYPES, DEPARTMENT_MAPPING, DEPARTMENT_NAMES, AUDIT_FILTERS  # AUDIT_FILTERS 추가
import logging
import pandas as pd
import orjson
import time
from get_project import get_project_info  # get_project.py에서 함수 임포트
import ast
from audit_message import send_audit_to_discord, send_audit_status_to_discord  # ✅ 추가
import csv
from functools import lru_cache

# JSON 파일 저장 경로 설정
RESULTS_DIR = os.path.join(STATIC_PATH, 'results')  # ✅ `static/data/results` 폴더에 저장
os.makedirs(RESULTS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self):
        self.searcher = ProjectDocumentSearcher(verbose=False)
        self._session = None
        self.csv_path = os.path.join(STATIC_DATA_PATH, 'combined_report_20250305.csv')

    @lru_cache(maxsize=128)
    async def load_csv_data(self):
        """CSV 데이터를 로드하고 캐시"""
        projects = []
        try:
            with open(self.csv_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    projects.append(row)
            return projects
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            return []

    def convert_project_to_json(self, project):
        """프로젝트 데이터를 JSON 형식으로 변환"""
        documents = {
            'contract': {'exists': bool(int(project['contract_exists'])), 'details': []},
            'specification': {'exists': bool(int(project['specification_exists'])), 'details': []},
            'initiation': {'exists': bool(int(project['initiation_exists'])), 'details': []},
            'agreement': {'exists': bool(int(project['agreement_exists'])), 'details': []},
            'budget': {'exists': bool(int(project['budget_exists'])), 'details': []},
            'deliverable1': {'exists': bool(int(project['deliverable1_exists'])), 'details': []},
            'deliverable2': {'exists': bool(int(project['deliverable2_exists'])), 'details': []},
            'completion': {'exists': bool(int(project['completion_exists'])), 'details': []},
            'certificate': {'exists': bool(int(project['certificate_exists'])), 'details': []},
            'evaluation': {'exists': bool(int(project['evaluation_exists'])), 'details': []}
        }
        
        return {
            'project_id': project['project_id'],
            'project_name': project['project_name'],
            'department': project['department'],
            'status': project['Status'],
            'contractor': project['Contractor'],
            'documents': documents,
            'timestamp': project.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        }

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
        """감사 결과를 JSON으로 저장하며, 잘못된 문자열을 변환"""
        project_id = result['project_id']
        
        # 기존: audit_20240178_06010.json 형식
        # filename = f"audit_{project_id}_{department_code}.json"
        
        # 변경: audit_20240178.json 형식
        filename = f"audit_{project_id}.json"
        
        filepath = os.path.join(RESULTS_DIR, filename)
        
        if not os.path.exists(RESULTS_DIR):
            os.makedirs(RESULTS_DIR, exist_ok=True)
        
        # JSON 내 문자열 형태의 딕셔너리를 올바르게 변환
        def fix_document_details(details):
            if isinstance(details, list):
                corrected_details = []
                for item in details:
                    if isinstance(item, str):
                        try:
                            item = json.loads(item.replace("'", "\""))  # 문자열을 JSON으로 변환
                        except json.JSONDecodeError:
                            pass  # 변환 실패 시 원래 값 유지
                    corrected_details.append(item)
                return corrected_details
            return details

        # 모든 문서 항목에서 문자열로 저장된 딕셔너리를 변환
        for doc_type, doc_info in result.get('documents', {}).items():
            if 'details' in doc_info:
                doc_info['details'] = fix_document_details(doc_info['details'])

        # JSON 저장
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(result, ensure_ascii=False, indent=2))

        logger.info(f"✅ 감사 결과 저장 완료: {filepath}")
        return filepath


    async def _send_single_to_discord(self, data, ctx=None):
        """단일 감사 결과를 Discord로 전송 (내부 함수)"""
        if not isinstance(data, dict):
            logger.error(f"Invalid audit data format: {data}")
            return False

        # Unknown 프로젝트 결과는 전송하지 않음
        if data.get('project_id') == 'Unknown' and data.get('department') == 'Unknown':
            logger.warning("Skipping Unknown project result")
            return True

            message = (
                f"📋 **Project Audit Result**\n"
            f"ID: {data.get('project_id', 'Unknown')}\n"
            f"Department: {data.get('department', data.get('department_code', 'Unknown'))}\n"
            f"Name: {data.get('project_name', f'Project {data.get('project_id', 'Unknown')}')}\n"
            f"Status: {data.get('status', 'Unknown')}\n"  # Status 추가
            f"Contractor: {data.get('contractor', 'Unknown')}\n"  # Contractor 추가
            f"Path: {data.get('project_path', 'Unknown')}\n\n"  # 'original_folder' 대신 'project_path' 사용
                f"📑 Documents:\n"
            )

            found_docs = []
            missing_docs = []
        documents = data.get('documents', {})
        
        # 모든 DOCUMENT_TYPES를 순회하며 처리
        for doc_type in DOCUMENT_TYPES.keys():
            doc_info = documents.get(doc_type, {'exists': False, 'details': []})
            doc_name = DOCUMENT_TYPES.get(doc_type, {}).get('name', doc_type)
            if doc_info.get('exists', False):  # exists가 True인 경우
                count = len(doc_info.get('details', []))
                found_docs.append(f"{doc_name} ({count}개)")
                else:
                missing_docs.append(f"{doc_name} (0개)")  # 발견되지 않은 문서는 0개로 표시

            if found_docs:
                message += "✅ Found:\n- " + "\n- ".join(found_docs) + "\n\n"
            if missing_docs:
            message += "❌ Missing:\n- " + "\n- ".join(missing_docs) + "\n\n"

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
                try:
                    async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=10) as response:
                        if response.status != 204:
                            logger.warning(f"Webhook response status: {response.status}")
                                print(f"Failed to send to Discord webhook: {message}")
                                return False
                        logger.info("Audit result successfully sent to Discord webhook")
                        return True
                    except asyncio.TimeoutError:
                        logger.error("Timeout while sending to Discord webhook")
                        print(f"Timeout while sending to Discord webhook: {message}")
                        return False
                    except Exception as e:
                        logger.error(f"Error sending to Discord webhook: {str(e)}")
                        print(f"Failed to send to Discord webhook: {message}")
                        return False
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

    def load_contract_data(self):
        """contract_status.csv에서 프로젝트 정보를 로드"""
        try:
            df = pd.read_csv(CONTRACT_STATUS_CSV, encoding='utf-8-sig')
            if '사업코드' not in df.columns or 'PM부서' not in df.columns or '진행상태' not in df.columns or '사업명' not in df.columns or '주관사' not in df.columns:
                raise ValueError("CSV must contain '사업코드', 'PM부서', '진행상태', '사업명', and '주관사' columns")

            # PM부서에서 부서 코드로 매핑
            def map_department(pm_dept):
                dept_name = pm_dept.strip()
                dept_code = DEPARTMENT_MAPPING.get(dept_name, '99999')
                return dept_code

            # ProjectID 생성 (사업코드에서 알파벳 제거)
            df['ProjectID'] = df['사업코드'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
            
            # 부서 코드 매핑
            df['Depart_Code'] = df['PM부서'].apply(map_department)
            df['Depart'] = df['Depart_Code'].map(DEPARTMENT_NAMES).fillna(df['PM부서'])
            
            # Contractor 매핑
            df['Contractor'] = df['주관사'].apply(lambda x: '주관사' if x == '주관사' else '비주관사')
            
            return df[['ProjectID', 'Depart_Code', 'Depart', '진행상태', '사업명', 'Contractor']]
        except Exception as e:
            logger.error(f"Failed to load contract data from {CONTRACT_STATUS_CSV}: {str(e)}")
            return pd.DataFrame()

    async def search_projects_by_id(self, project_id, department_code=None):
        """project_id만 기반으로 프로젝트 정보 및 폴더를 찾아 검색 (부서 코드를 필수로 요구하지 않음)"""
        numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
        projects = []
        
        # 1) contract_status.csv에서 프로젝트 정보 가져오기 (부서 코드 없이 검색)
        contract_df = self.load_contract_data()
        contract_match = contract_df[contract_df['ProjectID'] == numeric_project_id]
        
        if not contract_match.empty:
            row = contract_match.iloc[0]
            dept_code = row['Depart_Code']
            dept_name = row['Depart']
            project_name = row['사업명']
            status = row['진행상태']
            contractor = row['Contractor']
        else:
            # contract_status.csv에 없으면 get_project_info로 기본 정보 가져오기 (부서 코드 없이)
            loop = asyncio.get_event_loop()
            project_info = await loop.run_in_executor(None, lambda: get_project_info(project_id))
            if not project_info:
                logger.warning(f"Project ID {numeric_project_id} not found in contract status, using default values")
                dept_code = '99999'  # 기본 부서 코드
                dept_name = 'Unknown'
                project_name = f'Project {numeric_project_id}'
                status = 'Unknown'
                contractor = 'Unknown'
            else:
                dept_code = project_info['department_code']
                dept_name = project_info['department_name']
                project_name = project_info['project_name']
                status = project_info.get('status', 'Unknown')
                contractor = project_info.get('contractor', 'Unknown')

        # 부서 코드가 없으면 contract_status.csv 또는 기본값 사용
        if not department_code:
            department_code = dept_code

        # audit_targets_new.csv에서 search_folder 확인 (없으면 기본 경로 검색)
        csv_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
        search_folder = None
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            project_row = df[df['ProjectID'] == str(project_id)]
            if not project_row.empty:
                search_folder = str(project_row['search_folder'].iloc[0])
                if search_folder in ["No folder", "No directory"]:
                    logger.warning(f"Project {project_id} has No folder/No directory in audit_targets_new.csv, searching default path")
                    search_folder = None  # 기본 경로로 검색
            else:
                logger.warning(f"Project {project_id} not found in audit_targets_new.csv, searching default path")
        except Exception as e:
            logger.error(f"Error reading audit_targets_new.csv: {str(e)}")

        # project_list.csv에서 original_folder 확인 (경로 검색)
        project_list_path = PROJECT_LIST_CSV
        if os.path.exists(project_list_path):
            try:
                df_projects = pd.read_csv(project_list_path, encoding='utf-8-sig')
                df_projects['project_id'] = df_projects['project_id'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
                project_row_pl = df_projects[df_projects['project_id'] == numeric_project_id]
                if not project_row_pl.empty:
                    original_folder = project_row_pl['original_folder'].iloc[0]
                    folder_path = os.path.join(NETWORK_BASE_PATH, original_folder)
                    if os.path.exists(folder_path):
                        search_folder = folder_path
                        logger.info(f"Found project folder for Project {project_id}: {search_folder}")
                    else:
                        logger.warning(f"Project folder not found: {folder_path}")
                else:
                    logger.warning(f"No project found in project_list.csv for numeric ID {numeric_project_id} (original: {project_id})")
            except Exception as e:
                logger.error(f"Error reading project_list.csv: {str(e)}")

        # 기본 경로 검색 (NETWORK_BASE_PATH 아래)
        if not search_folder or search_folder in ["No folder", "No directory"]:
            base_paths = [
                os.path.join(NETWORK_BASE_PATH, numeric_project_id),  # 기본 project_id
                os.path.join(NETWORK_BASE_PATH, f"Y{numeric_project_id}"),  # Y 접두사 포함
                os.path.join(NETWORK_BASE_PATH, f"{numeric_project_id}_")  # project_id_ 접미사
            ]
            for path in base_paths:
                if os.path.exists(path):
                    search_folder = path
                    logger.info(f"Found default folder path for Project {project_id}: {search_folder}")
                    break
            if not search_folder:
                logger.warning(f"No default folder path found for Project {project_id} after search on {NETWORK_BASE_PATH}")
                return [{
                    'project_id': numeric_project_id,
                    'department_code': dept_code,
                    'department_name': dept_name,
                    'project_name': project_name,
                    'original_folder': None,
                    'status': status,
                    'contractor': contractor,
                    'documents': {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES}
                }]

        # 경로 존재 여부 확인 (search_folder가 No folder/No directory가 아닌 경우)
        if search_folder not in ["No folder", "No directory"]:
            if not await asyncio.to_thread(os.path.exists, search_folder):
                logger.error(f"Project folder does not exist: {search_folder}")
                return [{
                    'project_id': numeric_project_id,
                    'department_code': dept_code,
                    'department_name': dept_name,
                    'project_name': project_name,
                    'original_folder': search_folder,
                    'status': status,
                    'contractor': contractor,
                    'documents': {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES}
                }]

            # 2) search_project_data.py의 process_single_project 호출 (project_id만 전달)
            search_result = await self.searcher.process_single_project(project_id)  # department_code 제거
            if search_result:
                logger.debug(f"Raw search result for project {numeric_project_id}: {search_result}")
                
                documents = search_result.get('documents', {})
                processed_documents = {}
                
                # 모든 DOCUMENT_TYPES를 순회하며 처리
                for doc_type, type_info in DOCUMENT_TYPES.items():
                    doc_data = documents.get(doc_type, [])
                    
                    if isinstance(doc_data, list):
                        # 리스트인 경우 (파일 경로 목록)
                        details = [{'name': str(path), 'path': str(path)} for path in doc_data if path]
                        processed_documents[doc_type] = {
                            'exists': bool(details),
                            'details': details
                        }
                        logger.debug(f"Processed list {doc_type}: {len(details)} files")
                    elif isinstance(doc_data, dict):
                        # 딕셔너리인 경우
                        details = doc_data.get('details', [])
                        if isinstance(details, list):
                            processed_details = [
                                {'name': str(item), 'path': str(item)} if isinstance(item, (str, Path))
                                else item if isinstance(item, dict) and 'name' in item
                                else {'name': str(item), 'path': str(item)}
                                for item in details if item
                            ]
                            processed_documents[doc_type] = {
                                'exists': bool(processed_details),
                                'details': processed_details
                            }
                            logger.debug(f"Processed dict {doc_type}: {len(processed_details)} files")
                    else:
                        # 기타 경우 빈 결과로 처리
                        processed_documents[doc_type] = {
                            'exists': False,
                            'details': []
                        }
                        logger.debug(f"Empty result for {doc_type}")

                total_files = sum(len(doc_info['details']) for doc_info in processed_documents.values())
                logger.info(f"Total processed files: {total_files}")

                if total_files > 0 or processed_documents:
                    projects.append({
                        'project_id': numeric_project_id,
                        'department_code': dept_code,
                        'department_name': dept_name,
                        'project_name': project_name,
                        'original_folder': search_folder,
                        'status': status,
                        'contractor': contractor,
                        'documents': processed_documents
                    })
                    logger.info(f"Found project path for {numeric_project_id}: {search_folder}")
                    logger.info(f"Project metadata - Status: {status}, Contractor: {contractor}")
                    logger.info(f"Total files found: {total_files}")
        
        return projects

    async def audit_project(self, project_id, department_code=None, use_ai=False, ctx=None):
        """단일 프로젝트 감사 (CSV 기반)"""
        try:
            # CSV 데이터에서 프로젝트 검색
            projects = await self.load_csv_data()
            for project in projects:
                if project['project_id'] == project_id:
                    result = self.convert_project_to_json(project)
                    
                    # AI 분석 추가 (use_ai가 True인 경우)
            if use_ai:
                        try:
                ai_input = {
                    'project_id': project_id,
                                'department': result['department'],
                                'project_name': result['project_name'],
                                'status': result['status'],
                                'contractor': result['contractor'],
                                'documents': result['documents'],
                                'csv_data': project
                            }
                            result['ai_analysis'] = await analyze_with_gemini(ai_input, await self._get_session())
                        except Exception as e:
                            logger.error(f"AI 분석 오류: {str(e)}")
                            result['ai_analysis'] = f"AI 분석 중 오류 발생: {str(e)}"
                    
                    # Discord로 결과 전송
                    try:
                        await send_audit_to_discord(result)
                    except Exception as e:
                        logger.error(f"❌ 디스코드 전송 오류: {str(e)}")
                    
                    return [result]  # 리스트로 반환하여 기존 인터페이스 유지
            
            raise Exception(f'Project ID {project_id} not found')
            
        except Exception as e:
            error_msg = f"프로젝트 {project_id} 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            if ctx:
                await ctx.send(f"❌ 오류 발생: {error_msg}")
            return [{
                'error': str(e),
                'project_id': project_id,
                'department_code': department_code,
                'department': 'Unknown',
                'status': 'Unknown',
                'contractor': 'Unknown',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }]

    async def audit_multiple_projects(self, project_ids=None, department_codes=None, use_ai=False):
        """다중 프로젝트 감사 (CSV 기반)"""
        try:
            projects = await self.load_csv_data()
            results = []
            
            # project_ids가 지정된 경우 해당 프로젝트만 처리
            if project_ids:
                target_projects = [p for p in projects if p['project_id'] in project_ids]
            else:
                target_projects = projects
            
            for project in target_projects:
                result = self.convert_project_to_json(project)
                
                if use_ai:
                    try:
                        ai_input = {
                            'project_id': project['project_id'],
                            'department': result['department'],
                            'project_name': result['project_name'],
                            'status': result['status'],
                            'contractor': result['contractor'],
                            'documents': result['documents'],
                            'csv_data': project
                        }
                        result['ai_analysis'] = await analyze_with_gemini(ai_input, await self._get_session())
                    except Exception as e:
                        logger.error(f"AI 분석 오류: {str(e)}")
                        result['ai_analysis'] = f"AI 분석 중 오류 발생: {str(e)}"
                
                results.append(result)
                
                # Discord로 결과 전송
                try:
                    await send_audit_to_discord(result)
                except Exception as e:
                    logger.error(f"❌ 디스코드 전송 오류: {str(e)}")
            
            return results
            
        except Exception as e:
            error_msg = f"다중 프로젝트 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            return [{
                'error': str(e),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }]

    async def process_audit_targets(self, filters=None, use_ai=False, skip_no_folder=False):
        """감사 대상 리스트를 생성하고 배치로 감사 수행 (CSV 기반)"""
        try:
            # CSV 데이터 로드
            projects = await self.load_csv_data()
            
            if not projects:
                raise Exception("No projects found in CSV data")
            
            # 필터 적용 (있는 경우)
            if filters:
                filtered_projects = []
                for project in projects:
                    match = True
                    for key, value in filters.items():
                        if key in project and str(project[key]) != str(value):
                            match = False
                            break
                    if match:
                        filtered_projects.append(project)
                projects = filtered_projects
            
            # 결과 처리
            results = []
            for project in projects:
                result = self.convert_project_to_json(project)
                if use_ai:
                    try:
                        ai_input = {
                            'project_id': project['project_id'],
                            'department': result['department'],
                            'project_name': result['project_name'],
                            'status': result['status'],
                            'contractor': result['contractor'],
                            'documents': result['documents'],
                            'csv_data': project
                        }
                        result['ai_analysis'] = await analyze_with_gemini(ai_input, await self._get_session())
                    except Exception as e:
                        logger.error(f"AI 분석 오류: {str(e)}")
                        result['ai_analysis'] = f"AI 분석 중 오류 발생: {str(e)}"
                
                results.append(result)
                
                # Discord로 결과 전송
                try:
                    await send_audit_to_discord(result)
                except Exception as e:
                    logger.error(f"❌ 디스코드 전송 오류: {str(e)}")
            
            # 결과를 DataFrame으로 변환
            df_results = pd.DataFrame(results)
            
            # CSV 파일로 저장
            output_csv = os.path.join(STATIC_DATA_PATH, 'audit_results.csv')
            df_results.to_csv(output_csv, index=False, encoding='utf-8-sig')
            
            logger.info(f"감사 결과가 {output_csv}에 저장되었습니다. 총 프로젝트 수: {len(df_results)}")
            return df_results, results
            
        except Exception as e:
            error_msg = f"감사 대상 처리 오류: {str(e)}"
            logger.error(error_msg)
            return None, None

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="프로젝트 문서 검색")
    parser.add_argument('--project-id', type=str, nargs='+', required=False, help="검색할 프로젝트 ID (여러 개 가능)")
    parser.add_argument('--use-ai', action='store_true', help="AI 분석 사용")
    parser.add_argument('--skip-no-folder', action='store_true', help="No folder/No directory 프로젝트를 패스")
    args = parser.parse_args()
    
    async def main():
    logger.info("=== 프로젝트 문서 검색 시작 ===")
    service = AuditService()
    
        try:
    if args.project_id:
                if len(args.project_id) == 1:
                    await service.audit_project(args.project_id[0], None, args.use_ai, ctx=None)
        else:
                    await service.audit_multiple_projects(args.project_id, None, args.use_ai)
    else:
                await service.process_audit_targets(use_ai=args.use_ai, skip_no_folder=args.skip_no_folder)
        finally:
            await service.close()
    logger.info("\n=== 검색 완료 ===")
    
    asyncio.run(main())
    
# python audit_service.py
# python audit_service.py --project-id 20180076 --use-ai
# python audit_service.py --project-id 20240178 --use-ai
# python audit_service.py --project-id 20190088 --use-ai # 준공폴더,9999
# python audit_service.py --project-id 20190088 --use-ai # 준공폴더,9999
# python audit_service.py --project-id 20240001 --use-ai 