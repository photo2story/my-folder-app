# my_flask_app/audit_service.py
import os
import asyncio
import aiofiles
from datetime import datetime
import json
import aiohttp
from pathlib import Path
from search_project_data import ProjectDocumentSearcher
from gemini import analyze_with_gemini, clear_analysis_cache
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH, DISCORD_WEBHOOK_URL, STATIC_DATA_PATH, get_full_path
from config_assets import DOCUMENT_TYPES
import traceback
import time
import logging
import pandas as pd
import orjson
from functools import lru_cache  # lru_cache import 추가

# JSON 파일 저장 경로 설정
RESULTS_DIR = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self):
        self.searcher = ProjectDocumentSearcher(verbose=False)
        self._cache = {}
        self._session = None
        self._last_request_time = 0  # AI 요청 시간 추적용
        
    async def _get_session(self):
        if not hasattr(self, '_session') or (self._session is None or self._session.closed):
            self._session = aiohttp.ClientSession()
        return self._session

    async def save_audit_result(self, result, department_code):
        try:
            logger.debug("\n[DEBUG] === Saving Audit Result to JSON ===")
            project_id = result['project_id']
            
            # 부서 코드로 파일명 생성
            filename = f"audit_{department_code}_{project_id}.json"
            filepath = Path(RESULTS_DIR) / filename
            
            logger.debug(f"[DEBUG] Saving to: {filepath}")
            if not os.path.exists(RESULTS_DIR):
                os.makedirs(RESULTS_DIR, exist_ok=True)
            elif filepath.parent != Path(RESULTS_DIR) and not os.path.exists(filepath.parent):
                os.makedirs(filepath.parent, exist_ok=True)
            
            json_data = orjson.dumps(result, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS).decode('utf-8')
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(json_data)
            
            logger.debug(f"[DEBUG] JSON file saved successfully")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"[DEBUG] Error saving JSON file: {str(e)}")
            return None

    async def send_progress_message(self, ctx, message):
        session = await self._get_session()
        try:
            if ctx is None or isinstance(ctx, bool):
                logger.warning(f"[DEBUG] Invalid ctx provided, skipping Discord message: {message}")
                return
            if ctx and hasattr(ctx, 'send'):
                await ctx.send(message)
            elif DISCORD_WEBHOOK_URL:
                async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}) as response:
                    await response.read()
        except Exception as e:
            logger.error(f"[DEBUG] Error sending progress message: {str(e)}")

    @lru_cache(maxsize=1)
    def _load_project_df(self):
        return pd.read_csv(PROJECT_LIST_CSV, dtype={'department_code': str, 'project_id': str})

    async def get_project_info_by_dept(self, project_id, department_code=None):
        df = self._load_project_df()
        if department_code:
            project = df[(df['project_id'] == str(project_id)) & (df['department_code'] == str(department_code))]
        else:
            project = df[df['project_id'] == str(project_id)]
        
        if len(project) == 0:
            logger.error(f"Project ID {project_id} not found in project list for department {department_code}")
            return None
        
        row = project.iloc[0]
        return {
            'department_code': str(row['department_code']).zfill(5),
            'department_name': row['department_name'],
            'project_name': row['project_name'],
            'original_folder': get_full_path(row['original_folder'], verbose=False)
        }

    async def audit_project(self, project_id, department_code=None, use_ai=False, ctx=None):
        session = None
        start_time = time.time()
        try:
            session = await self._get_session()
            
            logger.info(f"\n=== 프로젝트 {project_id} 감사 시작 ===")
            
            # 부서 코드가 지정되지 않았으면 기본 부서 선택
            project_info = await self.get_project_info_by_dept(project_id, department_code)
            if not project_info:
                raise ValueError(f'Project ID {project_id} not found in project list for department {department_code}')
            
            # 프로젝트 정보 추출
            project_path = project_info['original_folder']
            dept_code = project_info['department_code']
            dept_name = project_info['department_name']
            
            logger.info(f"부서: {dept_code}_{dept_name}")
            logger.info(f"이름: {project_info['project_name']}")
            
            # 네트워크 드라이브 캐싱 추가
            logger.debug(f"Attempting to cache network path: {project_path}")
            project_path = await self.searcher._cache_network_files(project_path) if hasattr(self.searcher, '_cache_network_files') else project_path
            logger.debug(f"Cached project path: {project_path}")
            
            if not Path(project_path).exists():
                raise FileNotFoundError(
                    f'Project path {project_path} does not exist. '
                    f'Ensure {NETWORK_BASE_PATH} drive is accessible.'
                )
            
            # 문서 검색 수행
            logger.info("\n=== 문서 검색 시작 ===")
            search_start = time.time()
            search_result = await self.searcher.process_single_project(project_id, department_code)
            if not search_result or 'performance' not in search_result:
                raise ValueError(f"프로젝트 {project_id} 검색 실패 또는 성능 데이터 누락")
            
            search_time = search_result['performance']['search_time']
            all_documents = search_result['documents']
            
            # 검색 결과를 audit_project 형식으로 변환
            result = {
                'project_id': str(project_id),
                'department': f"{dept_code}_{dept_name}",
                'project_name': str(project_info['project_name']),
                'project_path': project_path,
                'documents': {
                    doc_type: {
                        'exists': bool(files),
                        'details': files
                    } for doc_type, files in all_documents.items()
                },
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance': {
                    'total_time': time.time() - start_time,
                    'search_time': search_time,
                    'document_counts': search_result['performance']['document_counts'],
                    'ai_time': 0,
                    'save_time': 0
                }
            }
            
            # 중간 결과 보고
            found_count = sum(1 for docs in result['documents'].values() if docs['exists'])
            total_count = len(DOCUMENT_TYPES)
            logger.info(f"\n=== 문서 검색 완료 ({search_time:.2f}초) ===")
            logger.info(f"- 발견된 문서 유형: {found_count}/{total_count}개")
            logger.info(f"- 총 발견 파일 수: {sum(len(docs['details']) for docs in result['documents'].values() if docs['exists'])}개")
            
            # AI 분석 수행 (요청 시)
            if use_ai:
                logger.info("\n=== AI 분석 시작 ===")
                ai_start = time.time()
                try:
                    result['ai_analysis'] = await analyze_with_gemini(result, session)
                    result['performance']['ai_time'] = time.time() - ai_start
                    logger.info(f"=== AI 분석 완료 ({result['performance']['ai_time']:.2f}초) ===")
                except Exception as ai_err:
                    logger.error(f"AI 분석 실패: {str(ai_err)}")
                    result['ai_analysis'] = f"AI analysis failed: {str(ai_err)}"
            
            # JSON 파일로 저장
            logger.info("\n=== 결과 저장 중 ===")
            save_start = time.time()
            json_path = await self.save_audit_result(result, dept_code)
            if json_path:
                result['json_file'] = json_path
                result['performance']['save_time'] = time.time() - save_start
                logger.info(f"결과 저장 완료: {json_path}")
            
            # 최종 결과 전송
            await self.send_to_discord(result, ctx)
            
            total_time = time.time() - start_time
            result['performance']['total_time'] = total_time
            logger.info(f"\n=== 감사 완료 ({total_time:.2f}초) ===")
            logger.info(f"성능 요약:")
            logger.info(f"- 총 소요 시간: {total_time:.2f}초")
            logger.info(f"- 문서 검색 시간: {search_time:.2f}초")
            logger.info(f"- AI 분석 시간: {result['performance']['ai_time']:.2f}초")
            logger.info(f"- JSON 저장 시간: {result['performance']['save_time']:.2f}초")
            logger.info(f"- 발견된 문서 유형: {found_count}/{total_count}개")
            logger.info(f"- 총 발견 파일 수: {sum(len(docs['details']) for docs in result['documents'].values() if docs['exists'])}개")
            return result
            
        except Exception as e:
            error_result = {
                'error': str(e),
                'project_id': project_id,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance': {
                    'total_time': time.time() - start_time
                }
            }
            logger.error(f"\n=== 감사 실패 ===")
            logger.error(f"프로젝트 {project_id} 처리 중 오류 발생: {str(e)}")
            await self.send_to_discord(error_result, ctx)
            return error_result
        finally:
            if session:
                await session.close()

    async def send_to_discord(self, data, ctx=None):
        session = await self._get_session()
        try:
            logger.debug("\n[DEBUG] === Sending to Discord ===")
            
            # 에러 결과 처리
            if 'error' in data:
                logger.debug(f"[DEBUG] Sending error message for project {data['project_id']}")
                message = (
                    f"❌ **Audit Error**\n"
                    f"Project ID: {data['project_id']}\n"
                    f"Error: {data['error']}\n"
                    f"Time: {data['timestamp']}"
                )
                await self.send_progress_message(ctx, message)
                return

            logger.debug(f"[DEBUG] Preparing success message for project {data['project_id']}")
            
            # 정상 결과 처리
            message = (
                f"📋 **Project Audit Result**\n"
                f"ID: {data['project_id']}\n"
                f"Department: {data['department']}\n"
                f"Name: {data['project_name']}\n"
                f"Path: {data['project_path']}\n\n"
                f"📑 Documents:\n"
            )

            # 문서 상태 요약
            found_docs = []
            missing_docs = []
            for doc_type, info in data['documents'].items():
                doc_name = DOCUMENT_TYPES[doc_type]['name']
                if info['exists']:
                    found_docs.append(f"{doc_name} ({len(info['details'])}개)")
                else:
                    missing_docs.append(doc_name)

            logger.debug(f"[DEBUG] Found documents: {len(found_docs)}")
            logger.debug(f"[DEBUG] Missing documents: {len(missing_docs)}")

            if found_docs:
                message += "✅ Found:\n- " + "\n- ".join(found_docs) + "\n\n"
            if missing_docs:
                message += "❌ Missing:\n- " + "\n- ".join(missing_docs) + "\n\n"

            if 'ai_analysis' in data:
                logger.debug("[DEBUG] Including AI analysis in message")
                message += f"🤖 AI Analysis:\n{data['ai_analysis']}\n\n"

            if 'json_file' in data:
                logger.debug("[DEBUG] Including JSON file path in message")
                message += f"\n💾 Results saved to: {data['json_file']}"

            message += f"\n⏰ {data['timestamp']}"
            
            # 메시지 전송
            await self.send_progress_message(ctx, message)
            logger.debug("[DEBUG] === Discord Message Sent ===\n")
            
        except Exception as e:
            error_msg = f"Discord notification error: {str(e)}"
            logger.error(f"\n[DEBUG] ERROR in send_to_discord: {error_msg}")
            if ctx:
                await ctx.send(f"❌ {error_msg}")

    def clear_cache(self):
        """서비스 캐시 초기화"""
        self._cache.clear()
        self.searcher.clear_cache()
        clear_analysis_cache()
        
    async def close(self):
        """리소스 정리"""
        if hasattr(self, '_session') and self._session:
            await self._session.close()
            self._session = None

    async def generate_summary_report(self, results):
        """전체 감사 결과에 대한 종합 보고서 생성"""
        try:
            logger.info("\n[DEBUG] === Generating Summary Report ===")
            
            # 결과 파일명 생성
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            summary_filename = f"summary_report_{timestamp}.json"
            summary_path = os.path.join(RESULTS_DIR, summary_filename)
            
            # 통계 데이터 수집
            summary = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_projects': len(results),
                'successful_audits': sum(1 for r in results if 'error' not in r),
                'failed_audits': sum(1 for r in results if 'error' in r),
                'document_statistics': {
                    doc_type: {
                        'found': 0,
                        'missing': 0
                    } for doc_type in DOCUMENT_TYPES.keys()
                },
                'department_statistics': {},
                'detailed_results': results
            }
            
            # 부서별, 문서별 통계 수집
            for result in results:
                if 'error' not in result:
                    dept = result['department']
                    if dept not in summary['department_statistics']:
                        summary['department_statistics'][dept] = {
                            'total': 0,
                            'documents_found': 0,
                            'documents_missing': 0
                        }
                    
                    dept_stats = summary['department_statistics'][dept]
                    dept_stats['total'] += 1
                    
                    for doc_type, info in result['documents'].items():
                        if info['exists']:
                            summary['document_statistics'][doc_type]['found'] += 1
                            dept_stats['documents_found'] += 1
                        else:
                            summary['document_statistics'][doc_type]['missing'] += 1
                            dept_stats['documents_missing'] += 1
            
            # 보고서 저장
            if not os.path.exists(RESULTS_DIR):
                os.makedirs(RESULTS_DIR, exist_ok=True)
            json_data = orjson.dumps(summary, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS).decode('utf-8')
            async with aiofiles.open(summary_path, 'w', encoding='utf-8') as f:
                await f.write(json_data)
            
            logger.info(f"[DEBUG] Summary report saved to: {summary_path}")
            return summary_path, summary
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to generate summary report: {str(e)}")
            return None, None

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="프로젝트 문서 검색")
    parser.add_argument('--project-id', type=str, required=True, help="검색할 프로젝트 ID")
    parser.add_argument('--department-code', type=str, default=None, help="부서 코드 (예: 01010, 01030)")
    parser.add_argument('--use-ai', action='store_true', help="AI 분석 사용")
    args = parser.parse_args()
    
    if args.use_ai:
        logging.getLogger().setLevel(logging.INFO)
    
    logger.info("=== 프로젝트 문서 검색 시작 ===")
    service = AuditService()
    
    asyncio.run(service.audit_project(args.project_id, args.department_code, args.use_ai))
    
    logger.info("\n=== 검색 완료 ===")
    asyncio.run(service.close())
# python audit_service.py
# python audit_service.py --project-id 20180076 --department-code 01010 --use-ai