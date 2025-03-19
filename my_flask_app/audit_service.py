# /my_flask_app/audit_service.py

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
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH, DISCORD_WEBHOOK_URL, STATIC_DATA_PATH, STATIC_PATH, CONTRACT_STATUS_CSV, RESULTS_DIR
from config_assets import DOCUMENT_TYPES, DEPARTMENT_MAPPING, DEPARTMENT_NAMES, AUDIT_FILTERS
import logging
import pandas as pd
import orjson
import time
from get_project import get_project_info
import ast
from audit_message import send_audit_to_discord, send_audit_status_to_discord
from git_operations import sync_files_to_github  # git_operations 임포트

# JSON 파일 저장 경로 설정
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
        """감사 결과를 부서별 폴더에 JSON으로 저장하며, 잘못된 문자열을 변환"""
        project_id = result['project_id']
        department = result.get('department', f"{department_code}_Unknown").replace('.', '_')  # .을 _로 교체
        if not re.match(r'^\d+_\w+$', department):
            logger.warning(f"Invalid department format: {department}, normalizing...")
            department = re.sub(r'[^0-9a-zA-Z_]', '_', department)

        department_folder = os.path.join(RESULTS_DIR, department)
        filename = f"audit_{project_id}.json"
        filepath = os.path.join(department_folder, filename)

        if not os.path.exists(department_folder):
            os.makedirs(department_folder, exist_ok=True)
            logger.info(f"Created department folder: {department_folder}")

        def fix_document_details(details):
            if isinstance(details, list):
                corrected_details = []
                for item in details:
                    if isinstance(item, str):  # 문자열인 경우 JSON 변환 시도
                        try:
                            corrected_item = json.loads(item.replace("'", "\""))
                        except json.JSONDecodeError:
                            corrected_item = item  # 변환 실패 시 원본 유지
                        corrected_details.append(corrected_item)
                    else:
                        corrected_details.append(item)  # 딕셔너리 등은 그대로 추가
                return corrected_details
            return details

        for doc_type, doc_info in result.get('documents', {}).items():
            if 'details' in doc_info:
                doc_info['details'] = fix_document_details(doc_info['details'])
                logger.debug(f"Fixed {doc_type} details: {doc_info['details']}")

        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(result, ensure_ascii=False, indent=2))

        logger.info(f"✅ 감사 결과 저장 완료: {filepath}")

        # 저장 후 GitHub에 업로드
        await sync_files_to_github(filepath)  # 특정 파일만 업로드
        logger.info(f"✅ 감사 결과 GitHub에 업로드 완료: {filepath}")

        return filepath

    async def _send_single_to_discord(self, data, ctx=None):
        """단일 감사 결과를 Discord로 전송 (내부 함수)"""
        if not isinstance(data, dict):
            logger.error(f"Invalid audit data format: {data}")
            return False

        if data.get('project_id') == 'Unknown' and data.get('department') == 'Unknown':
            logger.warning("Skipping Unknown project result")
            return True

        message = (
            f"📋 **Project Audit Result**\n"
            f"ID: {data.get('project_id', 'Unknown')}\n"
            f"Department: {data.get('department', data.get('department_code', 'Unknown'))}\n"
            f"Name: {data.get('project_name') or 'Project ' + str(data.get('project_id', 'Unknown'))}\n"
            f"Status: {data.get('status', 'Unknown')}\n"
            f"Contractor: {data.get('contractor', 'Unknown')}\n"
            f"Path: {data.get('project_path', 'Unknown')}\n\n"
            f"📑 Documents:\n"
        )

        found_docs = []
        missing_docs = []
        documents = data.get('documents', {})
        
        for doc_type in DOCUMENT_TYPES.keys():
            doc_info = documents.get(doc_type, {'exists': False, 'details': []})
            doc_name = DOCUMENT_TYPES.get(doc_type, {}).get('name', doc_type)
            if doc_info.get('exists', False):
                count = len(doc_info.get('details', []))
                found_docs.append(f"{doc_name} ({count}개)")
            else:
                missing_docs.append(f"{doc_type} (0개)")

        if found_docs:
            message += "✅ Found:\n- " + "\n- ".join(found_docs) + "\n\n"
        if missing_docs:
            message += "❌ Missing:\n- " + "\n- ".join(missing_docs) + "\n\n"

        if 'ai_analysis' in data and data['ai_analysis']:
            message += f"\n🤖 AI Analysis:\n{data['ai_analysis']}"

        message += f"\n⏰ {data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"

        try:
            if ctx:
                await ctx.send(message)
                logger.info(f"Sent audit result to Discord channel: {message}")
            elif DISCORD_WEBHOOK_URL:
                async with aiohttp.ClientSession() as session:
                    async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=10) as response:
                        if response.status != 204:
                            logger.warning(f"Webhook response status: {response.status}")
                            return False
                    logger.info("Audit result successfully sent to Discord webhook")
                    return True
            else:
                print(message)
                return True
        except Exception as e:
            logger.error(f"Error sending to Discord: {str(e)}")
            if ctx:
                await ctx.send(f"❌ 디스코드 전송 오류: {str(e)}")
            return False

    def load_contract_data(self):
        """contract_status.csv에서 프로젝트 정보를 로드"""
        try:
            df = pd.read_csv(CONTRACT_STATUS_CSV, encoding='utf-8-sig')
            if '사업코드' not in df.columns or 'PM부서' not in df.columns or '진행상태' not in df.columns or '사업명' not in df.columns or '주관사' not in df.columns:
                raise ValueError("CSV must contain '사업코드', 'PM부서', '진행상태', '사업명', and '주관사' columns")

            def map_department(pm_dept):
                dept_name = pm_dept.strip()
                dept_code = DEPARTMENT_MAPPING.get(dept_name, '99999')
                return dept_code

            df['ProjectID'] = df['사업코드'].apply(lambda x: str(x))  # 숫자 제거 대신 원래 값 유지
            df['Depart_Code'] = df['PM부서'].apply(map_department)
            df['Depart'] = df['Depart_Code'].map(DEPARTMENT_NAMES).fillna(df['PM부서'])
            df['Contractor'] = df['주관사'].apply(lambda x: '주관사' if x == '주관사' else '비주관사')
            return df[['ProjectID', 'Depart_Code', 'Depart', '진행상태', '사업명', 'Contractor']]
        except Exception as e:
            logger.error(f"Failed to load contract data from {CONTRACT_STATUS_CSV}: {str(e)}")
            return pd.DataFrame()

    async def search_projects_by_id(self, project_id, department_code=None):
        """project_id만 기반으로 프로젝트 정보 및 폴더를 찾아 검색"""
        numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))  # 검색용 숫자 ID
        projects = []

        # audit_targets_new.csv에서 원래 ProjectID 가져오기
        csv_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
        original_project_id = project_id  # 기본값은 입력된 project_id
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            project_row = df[df['ProjectID'].str.replace(r'[^0-9]', '', regex=True) == numeric_project_id]
            if not project_row.empty:
                original_project_id = project_row['ProjectID'].iloc[0]  # 원래 형식 (예: C20240178)
                logger.debug(f"Found original ProjectID: {original_project_id}")
        except Exception as e:
            logger.error(f"Error reading audit_targets_new.csv: {str(e)}")

        # contract_status.csv에서 정보 가져오기
        contract_df = self.load_contract_data()
        contract_match = contract_df[contract_df['ProjectID'] == original_project_id]
        
        if not contract_match.empty:
            row = contract_match.iloc[0]
            dept_code = row['Depart_Code']
            dept_name = row['Depart']
            project_name = row['사업명']
            status = row['진행상태']
            contractor = row['Contractor']
        else:
            loop = asyncio.get_event_loop()
            project_info = await loop.run_in_executor(None, lambda: get_project_info(project_id))
            if not project_info:
                logger.warning(f"Project ID {numeric_project_id} not found, using defaults")
                dept_code = '99999'
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

        if not department_code:
            department_code = dept_code

        # audit_targets_new.csv에서 search_folder 확인
        search_folder = None
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            project_row = df[df['ProjectID'] == original_project_id]
            if not project_row.empty:
                search_folder = str(project_row['search_folder'].iloc[0])
                if search_folder in ["No folder", "No directory"]:
                    logger.warning(f"Project {original_project_id} has No folder, searching default path")
                    search_folder = None
        except Exception as e:
            logger.error(f"Error reading audit_targets_new.csv: {str(e)}")

        # project_list.csv에서 original_folder 확인
        if os.path.exists(PROJECT_LIST_CSV):
            try:
                df_projects = pd.read_csv(PROJECT_LIST_CSV, encoding='utf-8-sig')
                df_projects['project_id'] = df_projects['project_id'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
                project_row_pl = df_projects[df_projects['project_id'] == numeric_project_id]
                if not project_row_pl.empty:
                    original_folder = project_row_pl['original_folder'].iloc[0]
                    folder_path = os.path.join(NETWORK_BASE_PATH, original_folder)
                    if os.path.exists(folder_path):
                        search_folder = folder_path
                        logger.info(f"Found project folder: {search_folder}")
            except Exception as e:
                logger.error(f"Error reading project_list.csv: {str(e)}")

        # 기본 경로 검색
        if not search_folder or search_folder in ["No folder", "No directory"]:
            base_paths = [
                os.path.join(NETWORK_BASE_PATH, numeric_project_id),
                os.path.join(NETWORK_BASE_PATH, f"Y{numeric_project_id}"),
                os.path.join(NETWORK_BASE_PATH, f"{numeric_project_id}_")
            ]
            for path in base_paths:
                if os.path.exists(path):
                    search_folder = path
                    logger.info(f"Found default folder: {search_folder}")
                    break
            if not search_folder:
                logger.warning(f"No folder found for Project {original_project_id}")
                return [{
                    'project_id': original_project_id,  # 원래 project_id 사용
                    'department_code': dept_code,
                    'department_name': dept_name,
                    'project_name': project_name,
                    'original_folder': None,
                    'status': status,
                    'contractor': contractor,
                    'documents': {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES}
                }]

        if search_folder not in ["No folder", "No directory"]:
            if not await asyncio.to_thread(os.path.exists, search_folder):
                logger.error(f"Folder does not exist: {search_folder}")
                return [{
                    'project_id': original_project_id,
                    'department_code': dept_code,
                    'department_name': dept_name,
                    'project_name': project_name,
                    'original_folder': search_folder,
                    'status': status,
                    'contractor': contractor,
                    'documents': {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES}
                }]

            logger.debug(f"Searching project_id: {project_id} in folder: {search_folder}")
            search_result = await self.searcher.process_single_project(project_id)
            logger.debug(f"Raw search result: {search_result}")

            if search_result:
                documents = search_result.get('documents', {})
                logger.debug(f"Documents from search_result: {documents}")
                processed_documents = {}
                for doc_type, type_info in DOCUMENT_TYPES.items():
                    doc_data = documents.get(doc_type, [])
                    if isinstance(doc_data, list) and doc_data:
                        details = doc_data
                        processed_documents[doc_type] = {
                            'exists': len(details) > 0,
                            'details': details
                        }
                        logger.debug(f"Processed {doc_type}: exists={len(details) > 0}, details={details}")
                    else:
                        processed_documents[doc_type] = {
                            'exists': False,
                            'details': []
                        }
                        logger.debug(f"Processed {doc_type}: exists=False, details=[]")

                total_files = sum(len(doc_info['details']) for doc_info in processed_documents.values())
                logger.debug(f"Total files calculated: {total_files}")
                projects.append({
                    'project_id': original_project_id,
                    'department_code': dept_code,
                    'department_name': dept_name,
                    'project_name': project_name,
                    'original_folder': search_folder,
                    'status': status,
                    'contractor': contractor,
                    'documents': processed_documents
                })
                logger.info(f"Found project path: {search_folder}, Total files: {total_files}")
            else:
                logger.warning(f"No search result returned for {original_project_id}")
                projects.append({
                    'project_id': original_project_id,
                    'department_code': dept_code,
                    'department_name': dept_name,
                    'project_name': project_name,
                    'original_folder': search_folder,
                    'status': status,
                    'contractor': contractor,
                    'documents': {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES}
                })

        logger.debug(f"Returning projects: {projects}")
        return projects

    async def audit_project(self, project_id, department_code=None, use_ai=False, ctx=None):
        """단일 프로젝트 감사"""
        start_time = time.time()
        try:
            logger.info(f"\n=== 프로젝트 {project_id} (ID: {re.sub(r'[^0-9]', '', str(project_id))}) 감사 시작 ===")
            if ctx:
                await send_audit_status_to_discord(ctx, f"🔍 프로젝트 {project_id} 감사를 시작합니다...")

            # audit_targets_new.csv에서 원래 ProjectID 가져오기
            csv_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
            original_project_id = project_id
            try:
                df = pd.read_csv(csv_path, encoding='utf-8-sig')
                numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
                project_row = df[df['ProjectID'].str.replace(r'[^0-9]', '', regex=True) == numeric_project_id]
                if not project_row.empty:
                    original_project_id = project_row['ProjectID'].iloc[0]  # "C20240178"
                    logger.debug(f"Found original ProjectID: {original_project_id}")
            except Exception as e:
                logger.error(f"Error reading audit_targets_new.csv: {str(e)}")

            projects = await self.search_projects_by_id(project_id)
            if not projects:
                contract_df = self.load_contract_data()
                contract_match = contract_df[contract_df['ProjectID'] == original_project_id]
                if not contract_match.empty:
                    row = contract_match.iloc[0]
                    dept_code = row['Depart_Code']
                    dept_name = row['Depart']
                    project_name = row['사업명']
                    status = row['진행상태']
                    contractor = row['Contractor']
                    folder_path = None

                    result = {
                        'project_id': original_project_id,
                        'project_name': project_name,
                        'department': f"{dept_code}_{dept_name}",
                        'status': status,
                        'contractor': contractor,
                        'documents': {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES},
                        'project_path': folder_path,
                        'ai_analysis': None,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'performance': {
                            'total_time': 0,
                            'search_time': 0,
                            'ai_time': 0,
                            'save_time': 0
                        }
                    }
                    
                    search_time = time.time() - start_time
                    ai_analysis = None
                    ai_time = 0
                    if use_ai:
                        if ctx:
                            await ctx.send(f"\n=== AI 분석 시작 ({dept_name}) ===")
                        logger.info(f"\n=== AI 분석 시작 ({dept_name}) ===")
                        ai_start = time.time()
                        ai_input = {
                            'project_id': original_project_id,
                            'department': dept_name,
                            'project_name': project_name,
                            'status': status,
                            'contractor': contractor,
                            'documents': result['documents'],
                            'csv_data': {
                                'Depart_ProjectID': f"{dept_code}_{re.sub(r'[^0-9]', '', str(project_id))}",
                                'Depart': dept_name,
                                'Status': status,
                                'Contractor': contractor,
                                'ProjectName': project_name,
                                **{f'{doc_type}_exists': 0 for doc_type in DOCUMENT_TYPES.keys()},
                                **{f'{doc_type}_count': 0 for doc_type in DOCUMENT_TYPES.keys()}
                            }
                        }
                        try:
                            ai_analysis = await analyze_with_gemini(ai_input, await self._get_session())
                        except Exception as e:
                            logger.error(f"AI 분석 오류: {str(e)}")
                            ai_analysis = f"AI 분석 중 오류 발생: {str(e)}"
                        ai_time = time.time() - ai_start
                        if ctx:
                            await ctx.send(f"=== AI 분석 완료 ({ai_time:.2f}초) ({dept_name})\nAI Analysis: {ai_analysis}")
                        logger.info(f"=== AI 분석 완료 ({ai_time:.2f}초) ({dept_name})\nAI Analysis: {ai_analysis}")
                    
                    result['ai_analysis'] = ai_analysis if use_ai else None
                    result['performance']['search_time'] = search_time
                    result['performance']['ai_time'] = ai_time
                    
                    save_start = time.time()
                    json_path = await self.save_audit_result(result, dept_code)
                    if json_path:
                        result['result_file'] = json_path
                        result['performance']['save_time'] = time.time() - save_start
                        if ctx:
                            await ctx.send(f"\n결과 저장 완료 ({dept_name}): {json_path}")
                        logger.info(f"\n결과 저장 완료 ({dept_name}): {json_path}")
                    
                    result['performance']['total_time'] = time.time() - start_time
                    try:
                        await send_audit_to_discord(result)
                    except Exception as e:
                        logger.error(f"❌ 디스코드 전송 오류: {str(e)}")
                    
                    return [result]  # 리스트로 반환
                else:
                    raise ValueError(f"Project ID {project_id} not found")

            all_results = []
            for project_info in projects:
                result = {
                    'project_id': project_info.get('project_id'),
                    'project_name': project_info.get('project_name'),
                    'department': f"{project_info.get('department_code')}_{project_info.get('department_name')}",
                    'status': project_info.get('status', 'Unknown'),
                    'contractor': project_info.get('contractor', 'Unknown'),
                    'documents': project_info['documents'].copy(),
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
                
                search_time = time.time() - start_time
                logger.debug(f"Documents for project {project_info['project_id']}: {result['documents']}")  # 디버깅 로그 추가
                
                csv_data = {
                    'Depart_ProjectID': f"{project_info['department_code']}_{re.sub(r'[^0-9]', '', str(project_info['project_id']))}",
                    'Depart': project_info['department_name'],
                    'Status': project_info['status'],
                    'Contractor': project_info['contractor'],
                    'ProjectName': project_info['project_name'],
                    'contract_exists': 1 if result['documents'].get('contract', {}).get('exists', False) else 0,
                    'contract_count': len(result['documents'].get('contract', {}).get('details', [])),
                    'specification_exists': 1 if result['documents'].get('specification', {}).get('exists', False) else 0,
                    'specification_count': len(result['documents'].get('specification', {}).get('details', [])),
                    'initiation_exists': 1 if result['documents'].get('initiation', {}).get('exists', False) else 0,
                    'initiation_count': len(result['documents'].get('initiation', {}).get('details', [])),
                    'agreement_exists': 1 if result['documents'].get('agreement', {}).get('exists', False) else 0,
                    'agreement_count': len(result['documents'].get('agreement', {}).get('details', [])),
                    'budget_exists': 1 if result['documents'].get('budget', {}).get('exists', False) else 0,
                    'budget_count': len(result['documents'].get('budget', {}).get('details', [])),
                    'deliverable1_exists': 1 if result['documents'].get('deliverable1', {}).get('exists', False) else 0,
                    'deliverable1_count': len(result['documents'].get('deliverable1', {}).get('details', [])),
                    'deliverable2_exists': 1 if result['documents'].get('deliverable2', {}).get('exists', False) else 0,
                    'deliverable2_count': len(result['documents'].get('deliverable2', {}).get('details', [])),
                    'completion_exists': 1 if result['documents'].get('completion', {}).get('exists', False) else 0,
                    'completion_count': len(result['documents'].get('completion', {}).get('details', [])),
                    'certificate_exists': 1 if result['documents'].get('certificate', {}).get('exists', False) else 0,
                    'certificate_count': len(result['documents'].get('certificate', {}).get('details', [])),
                    'evaluation_exists': 1 if result['documents'].get('evaluation', {}).get('exists', False) else 0,
                    'evaluation_count': len(result['documents'].get('evaluation', {}).get('details', []))
                }
                logger.debug(f"Gemini AI CSV 데이터: {csv_data}")

                ai_analysis = None
                ai_time = 0
                if use_ai:
                    if ctx:
                        await ctx.send(f"\n=== AI 분석 시작 ({project_info['department_name']}) ===")
                    logger.info(f"\n=== AI 분석 시작 ({project_info['department_name']}) ===")
                    ai_start = time.time()
                    ai_input = {
                        'project_id': project_info['project_id'],
                        'department': project_info['department_name'],
                        'project_name': project_info['project_name'],
                        'status': project_info['status'],
                        'contractor': project_info['contractor'],
                        'documents': result['documents'],
                        'csv_data': csv_data
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
                
                save_start = time.time()
                json_path = await self.save_audit_result(result, project_info['department_code'])
                if json_path:
                    result['result_file'] = json_path
                    result['performance']['save_time'] = time.time() - save_start
                    if ctx:
                        await ctx.send(f"\n결과 저장 완료 ({project_info['department_name']}): {json_path}")
                    logger.info(f"\n결과 저장 완료 ({project_info['department_name']}): {json_path}")
                
                result['performance']['total_time'] = time.time() - start_time
                try:
                    await send_audit_to_discord(result)
                except Exception as e:
                    logger.error(f"❌ 디스코드 전송 오류: {str(e)}")
                
                all_results.append(result)
            
            if ctx:
                await ctx.send(f"\n=== 모든 부서에 대한 감사 완료 ({time.time() - start_time:.2f}초) ===")
            
            logger.info(f"\n=== 모든 부서에 대한 감사 완료 ({time.time() - start_time:.2f}초) ===")
            logger.info(f"- 총 소요 시간: {time.time() - start_time:.2f}초")
            logger.info(f"- 발견된 부서: {len(projects)}개")
            total_files = sum(len(doc_info.get('details', [])) for p in projects for doc_info in p['documents'].values() if isinstance(doc_info, dict))
            logger.info(f"- 총 발견 파일 수: {total_files}")
            logger.info(f"- 발견된 문서 유형 수: {len({doc_type for p in projects for doc_type in p['documents'].keys() if p['documents'][doc_type].get('exists', False)})}")

            valid_results = [r for r in all_results if r.get('project_id') != 'Unknown']
            return valid_results if valid_results else all_results  # 리스트 반환

        except Exception as e:
            error_msg = f"프로젝트 {project_id} 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            if ctx:
                await ctx.send(f"❌ 오류 발생: {error_msg}")
            error_result = {
                'error': str(e),
                'project_id': original_project_id,
                'department_code': department_code,
                'department': 'Unknown' if not department_code else f"{department_code}_{DEPARTMENT_NAMES.get(department_code, 'Unknown')}",
                'status': 'Unknown',
                'contractor': 'Unknown',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance': {
                    'total_time': time.time() - start_time,
                    'search_time': 0,
                    'ai_time': 0,
                    'save_time': 0
                }
            }
            try:
                await send_audit_to_discord(error_result)
            except Exception as e:
                logger.error(f"❌ 디스코드 전송 오류: {str(e)}")
            return [error_result]  # 리스트 반환

    async def audit_multiple_projects(self, project_ids, use_ai=False):
        """다중 프로젝트 배치 감사"""
        tasks = [asyncio.create_task(self.audit_project(pid, None, use_ai)) for pid in project_ids]  # 원래 ID 전달
        return await asyncio.gather(*tasks)

    async def process_audit_targets(self, filters=None, use_ai=False, skip_no_folder=False):
        """감사 대상 리스트 생성 및 배치 감사"""
        from audit_target_generator import select_audit_targets

        try:
            data_dir = os.path.join(STATIC_DATA_PATH)
            os.makedirs(data_dir, exist_ok=True)
            if not os.access(data_dir, os.W_OK):
                logger.warning(f"No write permission for {data_dir}, attempting to fix...")
                import stat
                os.chmod(data_dir, stat.S_IWRITE | stat.S_IREAD)

            audit_targets_df, project_ids, department_codes = select_audit_targets(filters or AUDIT_FILTERS)
            if audit_targets_df.empty or 'ProjectID' not in audit_targets_df.columns:
                if 'Depart_ProjectID' in audit_targets_df.columns:
                    audit_targets_df['ProjectID'] = audit_targets_df['Depart_ProjectID'].apply(lambda x: x.split('_')[-1])
                    logger.warning(f"Generated ProjectID from Depart_ProjectID")
                else:
                    logger.error("No valid ProjectID or Depart_ProjectID column")
                    return None, None

            logger.info(f"📊 총 {len(project_ids)}개 프로젝트 처리 시작...")
            results = []

            for idx, project_id in enumerate(project_ids):
                progress = f"({idx + 1}/{len(project_ids)})"
                if idx % 10 == 0:
                    logger.info(f"🔄 진행중... {progress}")
                
                logger.info(f"🔍 프로젝트 {project_id} 감사 시작...")
                try:
                    csv_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
                    df = pd.read_csv(csv_path, encoding='utf-8-sig')
                    project_row = df[df['ProjectID'] == str(project_id)]
                    search_folder = project_row['search_folder'].iloc[0] if not project_row.empty else None
                    
                    if skip_no_folder and search_folder in ["No folder", "No directory"]:
                        logger.info(f"Skipping project {project_id} (No folder, skip_no_folder=True)")
                        continue

                    if search_folder in ["No folder", "No directory"]:
                        result = {
                            "project_id": project_id,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "documents_found": 0,
                            "risk_level": 0,
                            "missing_docs": 0,
                            "department": project_row['Depart'].iloc[0] if not project_row.empty else "Unknown",
                            "status": project_row['Status'].iloc[0] if not project_row.empty else "Unknown",
                            "contractor": project_row['Contractor'].iloc[0] if not project_row.empty else "Unknown",
                            "project_name": project_row['ProjectName'].iloc[0] if not project_row.empty else "Unknown",
                            "result": "0,0,0,0,0,0,0 (Folder missing)"
                        }
                        results.append(result)
                        logger.info(f"✅ 프로젝트 {project_id} 완료: 0,0,0,0,0,0,0 (Folder missing) {progress}")
                    else:
                        result = await self.audit_project(project_id, None, use_ai, None)
                        if 'error' not in result[0]:
                            results.append(result[0])
                            logger.info(f"✅ 프로젝트 {project_id} 완료: {result[0].get('timestamp')} {progress}")
                        else:
                            logger.error(f"❌ 프로젝트 {project_id} 실패: {result[0]['error']} {progress}")
                    
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Error processing project {project_id}: {str(e)}")
                    continue
            
            audit_targets_df['AuditResult'] = [
                result.get('result', 'No result') if 'error' not in result else f"Error: {result['error']}"
                for result in results
            ]
            output_csv = os.path.join(STATIC_DATA_PATH, 'audit_results.csv')
            audit_targets_df.to_csv(output_csv, index=False, encoding='utf-8-sig')
            logger.info(f"감사 결과 저장: {output_csv}, 총 프로젝트 수: {len(audit_targets_df)}")
            return audit_targets_df, results
            
        except Exception as e:
            logger.error(f"감사 대상 처리 오류: {str(e)}")
            return None, None

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="프로젝트 문서 검색")
    parser.add_argument('--project-id', type=str, nargs='+', required=False, help="검색할 프로젝트 ID")
    parser.add_argument('--department-code', type=str, nargs='+', default=None, help="부서 코드")
    parser.add_argument('--use-ai', action='store_true', help="AI 분석 사용")
    parser.add_argument('--skip-no-folder', action='store_true', help="No folder 프로젝트 패스")
    args = parser.parse_args()
    
    async def main():
        logger.info("=== 프로젝트 문서 검색 시작 ===")
        service = AuditService()
        try:
            if args.project_id:
                if len(args.project_id) == 1:
                    await service.audit_project(args.project_id[0], None, args.use_ai, ctx=None)
                else:
                    await service.audit_multiple_projects(args.project_id, args.use_ai)
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