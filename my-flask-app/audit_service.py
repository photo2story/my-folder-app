# my-flask-app/audit_service.py
import os
import asyncio
import aiofiles
from datetime import datetime
import json
import aiohttp
import re
from pathlib import Path
from search_project_data import ProjectDocumentSearcher
from gemini import analyze_with_gemini, clear_analysis_cache
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH, DISCORD_WEBHOOK_URL, STATIC_DATA_PATH, get_full_path, AUDIT_FILTERS, AUDIT_FILTERS_depart
from config_assets import DOCUMENT_TYPES, DEPARTMENT_MAPPING, DEPARTMENT_NAMES
import traceback
import time
import logging
import pandas as pd
import orjson
from functools import lru_cache
from diskcache import Cache
import tempfile
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
import psutil
from gemini import DocumentAnalyzer

# JSON 파일 저장 경로 설정
RESULTS_DIR = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

class AuditService:
    def __init__(self):
        self.searcher = ProjectDocumentSearcher(verbose=False)
        cache_dir = os.path.join(tempfile.gettempdir(), 'audit_cache')
        self._cache = Cache(directory=cache_dir, size_limit=1024*1024*1024)  # 1GB 캐시
        self._session = None
        self._last_request_time = 0  # AI 요청 시간 추적용
        cpu_count = multiprocessing.cpu_count()
        self.executor = ThreadPoolExecutor(max_workers=min(32, max(4, cpu_count * 2)))
        self.document_analyzer = DocumentAnalyzer()
        
    async def _get_session(self):
        """aiohttp 세션 관리"""
        if self._session is None or self._session.closed:
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
        """진행 상황 메시지 전송"""
        session = await self._get_session()
        try:
            if not DISCORD_WEBHOOK_URL:
                logger.warning("[DEBUG] No Discord webhook URL configured, using console output")
                print(message)
                return
            
            # Webhook으로 우선 전송, 타임아웃 설정
            try:
                async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 204:
                        logger.debug("[DEBUG] Message sent via webhook successfully")
                    else:
                        logger.warning(f"[DEBUG] Webhook response status: {response.status}, Response: {await response.text()}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"[DEBUG] Webhook error: {str(e)}, falling back to console output")
                print(message)
            
            # ctx가 유효한 경우 추가 전송
            if ctx and hasattr(ctx, 'send'):
                await ctx.send(message)
                logger.debug("[DEBUG] Message sent via ctx.send")
            else:
                logger.debug("[DEBUG] Using webhook or console for progress message")
                
        except Exception as e:
            logger.error(f"[DEBUG] Progress message error: {str(e)}, using console output")
            print(message)

    @lru_cache(maxsize=1)
    def _load_project_df(self):
        return pd.read_csv(PROJECT_LIST_CSV, dtype={'department_code': str, 'project_id': str})

    async def get_project_info_by_dept(self, project_id, department_code=None):
        try:
            cache_key = f"project_info:{project_id}:{department_code}"
            cached_result = self._cache.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for project info: {project_id}")
                return cached_result

            numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
            df = pd.read_csv(PROJECT_LIST_CSV, dtype={'department_code': str, 'project_id': str})
            
            if department_code:
                department_code = str(department_code).zfill(5)
            
            # 기본 검색
            if department_code:
                project = df[(df['project_id'] == numeric_project_id) & 
                           (df['department_code'].str.zfill(5) == department_code)]
            else:
                project = df[df['project_id'] == numeric_project_id]
            
            if len(project) == 0:
                # 대체 검색 (부서 코드 없이)
                alt_project = df[df['project_id'] == numeric_project_id]
                if len(alt_project) > 0:
                    logger.warning(f"Department code {department_code} not found for project {numeric_project_id}, using first match")
                    project = alt_project.iloc[0:1]
                else:
                    logger.error(f"Project ID {numeric_project_id} not found in project list")
                    return None
            
            row = project.iloc[0]
            dept_code = str(row['department_code']).zfill(5)
            dept_name = str(row['department_name'])
            logger.debug(f"[DEBUG] Found project - ID: {numeric_project_id}, Dept: {dept_code}, Name: {dept_name}")
            
            # 네트워크 드라이브 상태 확인 및 재시도
            retry_count = 3
            for attempt in range(retry_count):
                if os.path.exists(NETWORK_BASE_PATH):
                    break
                logger.warning(f"Network drive {NETWORK_BASE_PATH} not accessible, attempt {attempt + 1}/{retry_count}")
                await asyncio.sleep(1)
            
            if not os.path.exists(NETWORK_BASE_PATH):
                raise FileNotFoundError(f"Network drive {NETWORK_BASE_PATH} remains inaccessible after {retry_count} attempts")
            
            original_folder = str(row['original_folder'])
            full_path = get_full_path(original_folder, check_exists=False)
            logger.debug(f"[DEBUG] Original path: {original_folder}")
            logger.debug(f"[DEBUG] Full path: {full_path}")
            
            result = {
                'project_id': str(row['project_id']),
                'department_code': dept_code,
                'department_name': dept_name,
                'project_name': str(row['project_name']),
                'original_folder': full_path
            }
            
            # 결과 캐싱 (1시간)
            self._cache.set(cache_key, result, expire=3600)
            return result
            
        except Exception as e:
            logger.error(f"Error in get_project_info_by_dept for {project_id}: {str(e)}")
            logger.debug(f"Debug info - Project ID: {project_id}, Department: {department_code}, CSV: {PROJECT_LIST_CSV}")
            return None

    async def audit_project(self, project_id, department_code=None, use_ai=False, ctx=None):
        start_time = time.time()
        session = None
        try:
            session = await self._get_session()
            numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
            logger.info(f"\n=== 프로젝트 {project_id} (ID: {numeric_project_id}) 감사 시작 ===")
            
            # 프로젝트 정보 조회 (캐시 활용)
            project_info = await self.get_project_info_by_dept(project_id, department_code)
            if not project_info:
                raise ValueError(f'Project ID {project_id} not found for department {department_code}')
            
            # 진행 상황 메시지
            progress_msg = f"🔍 프로젝트 감사 진행 중: {project_info['project_name']} ({project_info['department_name']})"
            await self.send_progress_message(ctx, progress_msg)
            
            # 문서 검색 실행
            search_start = time.time()
            search_result = await self.searcher.search_all_documents(
                project_info['project_id'],
                project_info['department_code']
            )
            search_time = time.time() - search_start
            
            # 문서 검색 결과 유효성 검사
            if not search_result or 'documents' not in search_result:
                logger.error(f"문서 검색 결과가 유효하지 않습니다: {project_id}, Result: {search_result}")
                raise ValueError(f"문서 검색 결과가 유효하지 않습니다: {project_id}")
            
            documents = search_result['documents']
            performance = search_result.get('performance', {'search_time': search_time, 'document_counts': {}})
            
            # 문서 유형 및 파일 수 요약
            found_count = sum(1 for docs in documents.values() if docs['exists'])
            total_files = sum(len(docs['details']) for docs in documents.values() if docs['exists'])
            
            logger.info(f"\n=== 문서 검색 완료 ({search_time:.2f}초) ===")
            logger.info(f"- 발견된 문서 유형: {found_count}/{len(DOCUMENT_TYPES)}개")
            logger.info(f"- 총 발견 파일 수: {total_files}개")
            
            # 각 문서 유형별 상세 로그
            for doc_type in documents:
                if documents[doc_type]['exists']:
                    logger.info(f"{doc_type}: {len(documents[doc_type]['details'])}개 발견 ({performance.get('document_counts', {}).get(doc_type, 0):.2f}초)")
            
            # AI 분석 (옵션)
            ai_analysis = None
            ai_time = 0
            if use_ai:
                logger.info("\n=== AI 분석 시작 ===")
                ai_start = time.time()
                try:
                    ai_input = {
                        'project_id': project_id,  # project_id 명시적으로 포함
                        'project_info': project_info,
                        'documents': documents
                    }
                    ai_analysis = await analyze_with_gemini(ai_input, session)
                    ai_time = time.time() - ai_start
                    logger.info(f"=== AI 분석 완료 ({ai_time:.2f}초) ===")
                except Exception as ai_err:
                    logger.error(f"AI 분석 실패: {str(ai_err)}")
                    ai_analysis = f"AI analysis failed: {str(ai_err)}"
            
            # 결과 구성
            result = {
                'project_id': project_info['project_id'],
                'project_name': project_info['project_name'],
                'department': f"{project_info['department_code']}_{project_info['department_name']}",
                'documents': documents,
                'original_folder': project_info['original_folder'],  # 경로 추가
                'ai_analysis': ai_analysis if use_ai else None,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance': {
                    'total_time': time.time() - start_time,
                    'search_time': search_time,
                    'ai_time': ai_time,
                    'save_time': 0,
                    'metrics': {
                        'network_io_time': search_time,
                        'cache_hits': getattr(self.searcher, 'cache_hits', 0),
                        'cache_misses': getattr(self.searcher, 'cache_misses', 0),
                        'file_count': total_files,
                        'memory_usage': psutil.Process().memory_info().rss
                    }
                }
            }
            
            # 결과 저장
            save_start = time.time()
            json_path = await self.save_audit_result(result, project_info['department_code'])
            if json_path:
                result['json_file'] = json_path
                result['performance']['save_time'] = time.time() - save_start
                logger.info(f"\n=== 결과 저장 중 ===\n결과 저장 완료: {json_path}")
            
            # Discord로 결과 전송
            await self.send_to_discord(result, ctx)
            
            logger.info(f"\n=== 감사 완료 ({result['performance']['total_time']:.2f}초) ===")
            logger.info("성능 요약:")
            logger.info(f"- 총 소요 시간: {result['performance']['total_time']:.2f}초")
            logger.info(f"- 문서 검색 시간: {search_time:.2f}초")
            logger.info(f"- AI 분석 시간: {ai_time:.2f}초")
            logger.info(f"- JSON 저장 시간: {result['performance']['save_time']:.2f}초")
            logger.info(f"- 발견된 문서 유형: {found_count}/{len(DOCUMENT_TYPES)}개")
            logger.info(f"- 총 발견 파일 수: {total_files}개")
            logger.info(f"- Cache stats: Hits={result['performance']['metrics']['cache_hits']}, Misses={result['performance']['metrics']['cache_misses']}")

            return result
            
        except Exception as e:
            error_msg = f"프로젝트 {project_id} 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            error_result = {
                'error': str(e),
                'project_id': project_id,
                'department_code': department_code,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance': {
                    'total_time': time.time() - start_time
                }
            }
            await self.send_to_discord(error_result, ctx)
            return error_result
        finally:
            if session and not session.closed:
                await session.close()

    async def audit_multiple_projects(self, project_ids, department_codes, use_ai=False, ctx=None):
        """다중 프로젝트 배치 감사 (병렬 처리)"""
        numeric_project_ids = [re.sub(r'[^0-9]', '', str(pid)) for pid in project_ids]
        tasks = []
        
        for pid, dept in zip(numeric_project_ids, department_codes):
            task = asyncio.create_task(self.audit_project(pid, dept, use_ai, ctx))
            tasks.append(task)
        
        # 결과 수집 및 캐시 통계
        results = []
        cache_stats = {'hits': 0, 'misses': 0}
        
        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)
            if 'performance' in result and 'metrics' in result['performance']:
                cache_stats['hits'] += result['performance']['metrics'].get('cache_hits', 0)
                cache_stats['misses'] += result['performance']['metrics'].get('cache_misses', 0)
        
        logger.info(f"Cache statistics - Hits: {cache_stats['hits']}, Misses: {cache_stats['misses']}")
        return results

    async def send_to_discord(self, data, ctx=None):
        """디스코드로 결과 전송"""
        try:
            logger.debug("\n[DEBUG] === Sending to Discord ===")
            
            if 'error' in data:
                project_id = data.get('project_id', 'Unknown')
                logger.debug(f"[DEBUG] Sending error message for project {project_id}")
                message = (
                    f"❌ **Audit Error**\n"
                    f"Project ID: {project_id}\n"
                    f"Error: {data['error']}\n"
                    f"Time: {data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
                )
            else:
                message = (
                    f"📋 **Project Audit Result**\n"
                    f"ID: {data['project_id']}\n"
                    f"Department: {data['department']}\n"
                    f"Name: {data['project_name']}\n"
                    f"Path: {data['original_folder']}\n\n"  # original_folder 추가
                    f"📑 Documents:\n"
                )

                found_docs = []
                missing_docs = []
                for doc_type, info in data['documents'].items():
                    doc_name = DOCUMENT_TYPES[doc_type]['name']
                    if info['exists']:
                        found_docs.append(f"{doc_name} ({len(info['details'])}개)")
                    else:
                        missing_docs.append(doc_name)

                if found_docs:
                    message += "✅ Found:\n- " + "\n- ".join(found_docs) + "\n\n"
                if missing_docs:
                    message += "❌ Missing:\n- " + "\n- ".join(missing_docs) + "\n\n"

                if 'ai_analysis' in data:
                    message += f"🤖 AI Analysis:\n{data['ai_analysis']}\n\n"

                if 'json_file' in data:
                    message += f"\n💾 Results saved to: {data['json_file']}"

                message += f"\n⏰ {data['timestamp']}"

            session = await self._get_session()
            try:
                # Webhook으로 우선 전송, 타임아웃 설정
                if DISCORD_WEBHOOK_URL:
                    try:
                        async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}, timeout=aiohttp.ClientTimeout(total=10)) as response:
                            if response.status == 204:
                                logger.debug("[DEBUG] Message sent via webhook successfully")
                            else:
                                logger.warning(f"[DEBUG] Webhook response status: {response.status}, Response: {await response.text()}")
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        logger.error(f"[DEBUG] Webhook error: {str(e)}, falling back to console output")
                        print(message)
                
                # ctx가 유효한 경우 추가 전송
                if ctx and hasattr(ctx, 'send'):
                    await ctx.send(message)
                    logger.debug("[DEBUG] Message sent via ctx.send")
                else:
                    logger.debug("[DEBUG] Using webhook or console for result message")
                    
            except Exception as e:
                logger.error(f"[DEBUG] Error sending Discord message: {str(e)}, using console output")
                print(message)
            finally:
                if session:
                    await session.close()
                    
        except Exception as e:
            logger.error(f"[DEBUG] Error in send_to_discord: {str(e)}, using console output")
            print(f"❌ Error sending message: {str(e)}")

    def clear_cache(self):
        """캐시 초기화"""
        self._cache.clear()
        self.searcher.clear_cache()
        self.document_analyzer.clear_cache()
        logger.info("All caches cleared")

    async def close(self):
        """리소스 정리"""
        if self._session and not self._session.closed:
            await self._session.close()
        self.executor.shutdown(wait=True)
        self._cache.close()
        await self.document_analyzer.close()
        logger.info("AuditService resources cleaned up")

    async def generate_summary_report(self, results):
        """전체 감사 결과에 대한 종합 보고서 생성"""
        try:
            logger.info("\n[DEBUG] === Generating Summary Report ===")
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            summary_filename = f"summary_report_{timestamp}.json"
            summary_path = os.path.join(RESULTS_DIR, summary_filename)
            
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

    async def process_audit_targets(self, filters=None, use_ai=False, ctx=None):
        """감사 대상 리스트를 생성하고 배치로 감사 수행"""
        from audit_target_generator import select_audit_targets  # 동적 임포트

        try:
            # 감사 대상 생성
            audit_targets_df, project_ids, department_codes = select_audit_targets(filters)
            
            # project_ids에서 알파벳 제거
            numeric_project_ids = [re.sub(r'[^0-9]', '', str(pid)) for pid in project_ids]
            
            # 배치 감사 실행
            results = await self.audit_multiple_projects(numeric_project_ids, department_codes, use_ai, ctx)
            
            # 감사 결과 audit_targets_df에 추가
            audit_targets_df['AuditResult'] = [
                result.get('ai_analysis', 'No result') if 'error' not in result else f"Error: {result['error']}" 
                for result in results
            ]
            
            # 결과 저장 (audit_results.csv)
            output_csv = os.path.join(STATIC_DATA_PATH, 'audit_results.csv')
            audit_targets_df.to_csv(output_csv, index=False, encoding='utf-8-sig')
            
            logger.info(f"감사 결과가 {output_csv}에 저장되었습니다. 총 프로젝트 수: {len(audit_targets_df)}")
            
            # Discord로 요약 메시지 전송
            summary_message = (
                f"📊 **Audit Summary**\n"
                f"Total Projects: {len(audit_targets_df)}\n"
                f"Successful: {sum(1 for r in results if 'error' not in r)}\n"
                f"Failed: {sum(1 for r in results if 'error' in r)}"
            )
            await self.send_progress_message(ctx, summary_message)
            
            return audit_targets_df, results
            
        except Exception as e:
            logger.error(f"감사 대상 처리 오류: {str(e)}")
            await self.send_progress_message(ctx, f"❌ Audit processing error: {str(e)}")
            return None, None

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="프로젝트 문서 검색")
    parser.add_argument('--project-id', type=str, nargs='+', required=False, help="검색할 프로젝트 ID (여러 개 가능)")
    parser.add_argument('--department-code', type=str, nargs='+', default=None, help="부서 코드 (여러 개 가능, 예: 01010, 06010)")
    parser.add_argument('--use-ai', action='store_true', help="AI 분석 사용")
    parser.add_argument('--year', type=int, nargs='+', default=AUDIT_FILTERS['year'], help="필터링할 준공 연도 (기본값: 2024)")
    parser.add_argument('--status', type=str, nargs='+', default=['진행', '중지'], help="필터링할 진행 상태 (기본값: 진행, 중지)")
    parser.add_argument('--is-main-contractor', type=str, nargs='+', default=AUDIT_FILTERS['is_main_contractor'], help="필터링할 주관사 여부 (기본값: 주관사, 비주관사)")
    parser.add_argument('--department', type=str, nargs='+', default=AUDIT_FILTERS['department'] or AUDIT_FILTERS_depart, help="필터링할 부서 코드 (기본값: 01010, 06010)")
    args = parser.parse_args()
    
    if args.use_ai:
        logging.getLogger().setLevel(logging.INFO)
    
    logger.info("=== 프로젝트 문서 검색 시작 ===")
    service = AuditService()
    
    if args.project_id:
        # project_ids에서 알파벳 제거
        numeric_project_ids = [re.sub(r'[^0-9]', '', str(pid)) for pid in args.project_id]
        department_codes = args.department_code if args.department_code else [None] * len(numeric_project_ids)
        if len(department_codes) != len(numeric_project_ids):
            raise ValueError("부서 코드와 프로젝트 ID의 개수가 일치해야 합니다.")
        
        # 단일 또는 다중 프로젝트 감사
        if len(numeric_project_ids) == 1:
            asyncio.run(service.audit_project(args.project_id[0], department_codes[0] if department_codes[0] else None, args.use_ai))
        else:
            asyncio.run(service.audit_multiple_projects(numeric_project_ids, department_codes, args.use_ai))
    else:
        # 필터링 조건으로 감사 대상 생성 및 배치 감사
        filters = {
            'year': args.year,
            'status': args.status,
            'is-main-contractor': args.is_main_contractor,
            'department': args.department
        }
        asyncio.run(service.process_audit_targets(filters, args.use_ai))
    
    logger.info("\n=== 검색 완료 ===")
    asyncio.run(service.close())
    
# python audit_service.py
# python audit_service.py --project-id 20180076 --department-code 01010 --use-ai
# python audit_service.py --project-id 20240178 --department-code 06010 --use-ai