# /my_flask_app/audit_service.py

import os
import re
import json
import time
import logging
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
import aiohttp
import asyncio
from config import (
    STATIC_DATA_PATH, CONTRACT_STATUS_CSV, NETWORK_BASE_PATH, RESULTS_DIR,
    DISCORD_WEBHOOK_URL, TAVILY_API_KEY
)
from config_assets import (
    DOCUMENT_TYPES, DEPARTMENT_MAPPING, DEPARTMENT_NAMES
)
from search_project_data import ProjectDocumentSearcher
from tavily import TavilyClient

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self):
        self.searcher = ProjectDocumentSearcher(verbose=False)
        self._session = None
        self.tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

    async def _get_session(self) -> aiohttp.ClientSession:
        """aiohttp 세션 생성"""
        return aiohttp.ClientSession()

    def load_contract_data(self) -> pd.DataFrame:
        """contract_status.csv에서 프로젝트 정보를 로드"""
        try:
            df = pd.read_csv(CONTRACT_STATUS_CSV, encoding='utf-8-sig')
            if '사업코드' not in df.columns or 'PM부서' not in df.columns or '진행상태' not in df.columns or '사업명' not in df.columns or '주관사' not in df.columns:
                raise ValueError("CSV must contain '사업코드', 'PM부서', '진행상태', '사업명', and '주관사' columns")

            def map_department(pm_dept: str) -> str:
                dept_name = pm_dept.strip()
                dept_code = DEPARTMENT_MAPPING.get(dept_name, '99999')
                if dept_code == '99999':
                    logger.warning(f"Unknown department: {dept_name}, mapped to default code '99999'. Please update DEPARTMENT_MAPPING.")
                logger.debug(f"Mapping department: {dept_name} -> {dept_code}")
                return dept_code

            df['ProjectID'] = df['사업코드'].apply(lambda x: str(x))
            df['Depart_Code'] = df['PM부서'].apply(map_department)
            df['Depart'] = df['Depart_Code'].map(DEPARTMENT_NAMES).fillna(df['PM부서'])
            logger.debug(f"Loaded contract data: {df[['ProjectID', 'Depart_Code', 'Depart']].to_dict(orient='records')}")
            df['Contractor'] = df['주관사'].apply(lambda x: '주관사' if x == '주관사' else '비주관사')
            return df[['ProjectID', 'Depart_Code', 'Depart', '진행상태', '사업명', 'Contractor']]
        except Exception as e:
            logger.error(f"Failed to load contract data from {CONTRACT_STATUS_CSV}: {str(e)}")
            return pd.DataFrame()

    async def search_projects_by_id(self, project_id: str) -> List[Dict[str, Any]]:
        """프로젝트 ID로 프로젝트 검색"""
        projects = []
        contract_df = self.load_contract_data()
        numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
        contract_match = contract_df[contract_df['ProjectID'].str.replace(r'[^0-9]', '', regex=True) == numeric_project_id]

        if not contract_match.empty:
            row = contract_match.iloc[0]
            original_project_id = row['ProjectID']
            dept_code = row['Depart_Code']
            dept_name = row['Depart']
            project_name = row['사업명']
            status = row['진행상태']
            contractor = row['Contractor']
            search_folder = None
            processed_documents = {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES}

            for base_path in [NETWORK_BASE_PATH]:
                project_path = os.path.join(base_path, f"{dept_code}_{numeric_project_id}")
                if os.path.exists(project_path):
                    search_folder = project_path
                    for doc_type in DOCUMENT_TYPES:
                        doc_path = os.path.join(project_path, doc_type)
                        if os.path.exists(doc_path):
                            processed_documents[doc_type]['exists'] = True
                            processed_documents[doc_type]['details'] = [f for f in os.listdir(doc_path) if os.path.isfile(os.path.join(doc_path, f))]
                    break

            logger.info(f"=== 프로젝트 {project_id} 검색 시작 (부서: {dept_code}_{dept_name}) ===")
            projects.append({
                'project_id': original_project_id,
                'department_code': dept_code,
                'department': f"{dept_code}_{dept_name}",
                'department_name': dept_name,
                'project_name': project_name,
                'original_folder': search_folder,
                'status': status,
                'contractor': contractor,
                'documents': processed_documents
            })
        return projects

    async def save_audit_result(self, result: Dict[str, Any]) -> None:
        """감사 결과를 저장"""
        try:
            project_id = result.get('project_id')
            department = result.get('department', 'Unknown_Unknown')
            department_code = department.split('_')[0] if '_' in department else 'Unknown'

            result_folder = os.path.join(RESULTS_DIR, department)
            os.makedirs(result_folder, exist_ok=True)

            result_file = os.path.join(result_folder, f"audit_{project_id}.json")
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=4)

            logger.info(f"✅ 감사 결과 저장 완료: {result_file}")
        except Exception as e:
            logger.error(f"감사 결과 저장 실패: {str(e)}")

    async def _send_single_to_discord(self, message: str) -> None:
        """Discord로 메시지 전송"""
        if not DISCORD_WEBHOOK_URL:
            logger.warning("Discord Webhook URL이 설정되지 않았습니다.")
            return

        async with aiohttp.ClientSession() as session:
            try:
                payload = {"content": message}
                async with session.post(DISCORD_WEBHOOK_URL, json=payload) as response:
                    if response.status != 204:
                        logger.error(f"Discord 메시지 전송 실패: {response.status}")
            except Exception as e:
                logger.error(f"Discord 메시지 전송 중 오류: {str(e)}")

    async def audit_project(self, project_id: str, department_code: Optional[str] = None, use_ai: bool = False, ctx: Optional[Any] = None) -> Dict[str, Any]:
        """단일 프로젝트 감사"""
        start_time = time.time()
        try:
            logger.info(f"\n=== 프로젝트 {project_id} (ID: {re.sub(r'[^0-9]', '', str(project_id))}) 감사 시작 ===")
            if ctx:
                await self._send_single_to_discord(f"🔍 프로젝트 {project_id} 감사를 시작합니다...")

            # audit_targets_new.csv에서 원래 ProjectID 가져오기
            csv_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
            original_project_id = project_id
            try:
                df = pd.read_csv(csv_path, encoding='utf-8-sig')
                numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
                project_row = df[df['ProjectID'].str.replace(r'[^0-9]', '', regex=True) == numeric_project_id]
                if not project_row.empty:
                    original_project_id = project_row['ProjectID'].iloc[0]
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
                            await self._send_single_to_discord(f"\n=== AI 분석 시작 ({dept_name}) ===")
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
                            ai_analysis = await self.analyze_with_tavily_mcp(ai_input)
                        except Exception as e:
                            logger.error(f"AI 분석 오류: {str(e)}")
                            ai_analysis = f"AI 분석 중 오류 발생: {str(e)}"
                        ai_time = time.time() - ai_start
                        if ctx:
                            await self._send_single_to_discord(f"=== AI 분석 완료 ({ai_time:.2f}초) ({dept_name})\nAI Analysis: {ai_analysis}")
                        logger.info(f"=== AI 분석 완료 ({ai_time:.2f}초) ({dept_name})\nAI Analysis: {ai_analysis}")

                    save_start = time.time()
                    await self.save_audit_result(result)
                    save_time = time.time() - save_start

                    total_time = time.time() - start_time
                    result['ai_analysis'] = ai_analysis
                    result['performance'] = {
                        'total_time': total_time,
                        'search_time': search_time,
                        'ai_time': ai_time,
                        'save_time': save_time
                    }

                    if ctx:
                        await self._send_single_to_discord(f"✅ 프로젝트 {project_id} 감사 완료 ({total_time:.2f}초)")
                    logger.info(f"✅ 프로젝트 {project_id} 감사 완료 ({total_time:.2f}초)")
                    return result
                else:
                    logger.warning(f"프로젝트 {project_id}에 대한 계약 데이터를 찾을 수 없습니다.")
                    if ctx:
                        await self._send_single_to_discord(f"⚠️ 프로젝트 {project_id}에 대한 계약 데이터를 찾을 수 없습니다.")
                    return {}
            else:
                project_info = projects[0]
                result = {
                    'project_id': project_info.get('project_id'),
                    'project_name': project_info.get('project_name'),
                    'department': project_info.get('department'),
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
                ai_analysis = None
                ai_time = 0
                if use_ai:
                    if ctx:
                        await self._send_single_to_discord(f"\n=== AI 분석 시작 ({project_info['department_name']}) ===")
                    logger.info(f"\n=== AI 분석 시작 ({project_info['department_name']}) ===")
                    ai_start = time.time()
                    ai_input = {
                        'project_id': project_info['project_id'],
                        'department': project_info['department_name'],
                        'project_name': project_info['project_name'],
                        'status': project_info['status'],
                        'contractor': project_info['contractor'],
                        'documents': project_info['documents'],
                        'csv_data': {
                            'Depart_ProjectID': f"{project_info['department_code']}_{re.sub(r'[^0-9]', '', str(project_id))}",
                            'Depart': project_info['department_name'],
                            'Status': project_info['status'],
                            'Contractor': project_info['contractor'],
                            'ProjectName': project_info['project_name'],
                            **{f'{doc_type}_exists': 1 if project_info['documents'][doc_type]['exists'] else 0 for doc_type in DOCUMENT_TYPES.keys()},
                            **{f'{doc_type}_count': len(project_info['documents'][doc_type]['details']) for doc_type in DOCUMENT_TYPES.keys()}
                        }
                    }
                    try:
                        ai_analysis = await self.analyze_with_tavily_mcp(ai_input)
                    except Exception as e:
                        logger.error(f"AI 분석 오류: {str(e)}")
                        ai_analysis = f"AI 분석 중 오류 발생: {str(e)}"
                    ai_time = time.time() - ai_start
                    if ctx:
                        await self._send_single_to_discord(f"=== AI 분석 완료 ({ai_time:.2f}초) ({project_info['department_name']})\nAI Analysis: {ai_analysis}")
                    logger.info(f"=== AI 분석 완료 ({ai_time:.2f}초) ({project_info['department_name']})\nAI Analysis: {ai_analysis}")

                save_start = time.time()
                await self.save_audit_result(result)
                save_time = time.time() - save_start

                total_time = time.time() - start_time
                result['ai_analysis'] = ai_analysis
                result['performance'] = {
                    'total_time': total_time,
                    'search_time': search_time,
                    'ai_time': ai_time,
                    'save_time': save_time
                }

                if ctx:
                    await self._send_single_to_discord(f"✅ 프로젝트 {project_id} 감사 완료 ({total_time:.2f}초)")
                logger.info(f"✅ 프로젝트 {project_id} 감사 완료 ({total_time:.2f}초)")
                return result

        except Exception as e:
            logger.error(f"프로젝트 {project_id} 감사 중 오류: {str(e)}")
            if ctx:
                await self._send_single_to_discord(f"❌ 프로젝트 {project_id} 감사 중 오류 발생: {str(e)}")
            return {}

    async def audit_multiple_projects(self, project_ids: List[str], use_ai: bool = False, ctx: Optional[Any] = None) -> List[Dict[str, Any]]:
        """여러 프로젝트 감사"""
        results = []
        for project_id in project_ids:
            result = await self.audit_project(project_id, use_ai=use_ai, ctx=ctx)
            if result:
                results.append(result)
        return results

    async def process_audit_targets(self, use_ai: bool = False, ctx: Optional[Any] = None) -> List[Dict[str, Any]]:
        """audit_targets_new.csv에서 프로젝트 목록을 가져와 감사"""
        try:
            df = pd.read_csv(os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv'), encoding='utf-8-sig')
            project_ids = df['ProjectID'].tolist()
            logger.info(f"총 {len(project_ids)}개의 프로젝트를 감사합니다: {project_ids}")
            return await self.audit_multiple_projects(project_ids, use_ai=use_ai, ctx=ctx)
        except Exception as e:
            logger.error(f"audit_targets_new.csv 처리 중 오류: {str(e)}")
            if ctx:
                await self._send_single_to_discord(f"❌ audit_targets_new.csv 처리 중 오류 발생: {str(e)}")
            return []

    async def analyze_with_tavily_mcp(self, ai_input: Dict[str, Any]) -> str:
        """Tavily MCP 검색을 통해 AI 분석 수행"""
        try:
            project_id = ai_input['project_id']
            project_name = ai_input['project_name']
            department = ai_input['department']
            status = ai_input['status']
            contractor = ai_input['contractor']
            documents = ai_input['documents']

            # 문서 상태 요약
            doc_summary = "\n".join([f"- {doc_type}: {'Exists' if details['exists'] else 'Not Found'}" for doc_type, details in documents.items()])

            # 검색 쿼리 생성
            query = f"프로젝트 ID: {project_id}, 프로젝트명: {project_name}, 부서: {department}, 진행상태: {status}, 주관사: {contractor}\n문서 상태:\n{doc_summary}"
            logger.info(f"Tavily MCP 검색 쿼리: {query}")

            # Tavily MCP 검색 수행
            response = self.tavily_client.search(query=query, search_depth="advanced", max_results=5)
            if response and 'results' in response:
                analysis = "Tavily MCP 검색 결과:\n"
                for result in response['results']:
                    analysis += f"- {result['title']}: {result['url']}\n  {result['content'][:200]}...\n"
                return analysis
            else:
                return "Tavily MCP 검색 결과가 없습니다."
        except Exception as e:
            logger.error(f"Tavily MCP 분석 중 오류: {str(e)}")
            return f"Tavily MCP 분석 중 오류 발생: {str(e)}"

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="프로젝트 감사 서비스")
    parser.add_argument('--project-id', type=str, help="감사할 프로젝트 ID")
    parser.add_argument('--department', type=str, help="특정 부서만 감사 (예: 01010 for 도로부)")
    parser.add_argument('--use-ai', action='store_true', help="AI 분석 사용 여부")
    args = parser.parse_args()

    audit_service = AuditService()
    loop = asyncio.get_event_loop()

    if args.project_id:
        result = loop.run_until_complete(audit_service.audit_project(args.project_id, use_ai=args.use_ai))
        print(json.dumps(result, ensure_ascii=False, indent=4))
    elif args.department:
        # 특정 부서의 프로젝트들만 감사
        dept_code = args.department.zfill(5)  # 5자리로 패딩
        print(f"부서 {dept_code}의 프로젝트들을 감사합니다...")
        
        # contract_status.csv에서 해당 부서의 프로젝트들 필터링
        contract_df = audit_service.load_contract_data()
        dept_projects = contract_df[contract_df['Depart_Code'] == dept_code]
        
        if dept_projects.empty:
            print(f"부서 {dept_code}에 해당하는 프로젝트가 없습니다.")
        else:
            project_ids = dept_projects['ProjectID'].tolist()
            print(f"감사할 프로젝트 목록: {project_ids}")
            results = loop.run_until_complete(audit_service.audit_multiple_projects(project_ids, use_ai=args.use_ai))
            print(json.dumps(results, ensure_ascii=False, indent=4))
    else:
        results = loop.run_until_complete(audit_service.process_audit_targets(use_ai=args.use_ai))
        print(json.dumps(results, ensure_ascii=False, indent=4))
    
# python audit_service.py
# python audit_service.py --project-id 20180076 --use-ai
# python audit_service.py --project-id 20240178 --use-ai
# python audit_service.py --project-id 20190088 --use-ai # 준공폴더,9999
# python audit_service.py --project-id 20240001 --use-ai
# python audit_service.py --department 01010 --use-ai  # 도로부만 감사
# python audit_service.py --department 04010 --use-ai  # 도시계획부만 감사 