# my-flask-app/audit_service.py
import os
import asyncio
import aiofiles
from datetime import datetime
import json
import aiohttp
from pathlib import Path
from search_project_data import ProjectDocumentSearcher
from gemini import analyze_with_gemini, clear_analysis_cache
from config import DOCUMENT_TYPES, PROJECT_LIST_CSV, NETWORK_BASE_PATH, DISCORD_WEBHOOK_URL, STATIC_DATA_PATH
import traceback

# JSON 파일 저장 경로 설정
RESULTS_DIR = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

class AuditService:
    def __init__(self):
        self.searcher = ProjectDocumentSearcher()
        self._cache = {}
        self._session = None
        self._last_request_time = 0  # AI 요청 시간 추적용
        
    async def _get_session(self):
        """비동기 HTTP 세션 관리"""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def save_audit_result(self, result):
        """감사 결과를 JSON 파일로 비동기 저장"""
        try:
            print("\n[DEBUG] === Saving Audit Result to JSON ===")
            project_id = result['project_id']
            department = result['department'].split('_')[0]
            
            # 결과 JSON 파일명 생성
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"audit_{department}_{project_id}_{timestamp}.json"
            filepath = Path(RESULTS_DIR) / filename
            
            print(f"[DEBUG] Saving to: {filepath}")
            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                result['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                await f.write(json.dumps(result, ensure_ascii=False, indent=2))
            
            print(f"[DEBUG] JSON file saved successfully")
            return str(filepath)
            
        except Exception as e:
            print(f"[DEBUG] Error saving JSON file: {str(e)}")
            return None

    async def send_progress_message(self, ctx, message):
        """진행 상황 메시지를 Discord로 비동기 전송"""
        try:
            if ctx:
                await ctx.send(message)
            elif DISCORD_WEBHOOK_URL:
                session = await self._get_session()
                async with session.post(DISCORD_WEBHOOK_URL, json={'content': message}) as response:
                    await response.read()
        except Exception as e:
            print(f"[DEBUG] Error sending progress message: {str(e)}")

    async def audit_project(self, project_id, use_ai=False, ctx=None):
        """프로젝트 감사 수행 (비동기)"""
        session = None
        try:
            session = await self._get_session()  # 세션 생성
            
            await self.send_progress_message(ctx, f"🔍 프로젝트 {project_id} 감사를 시작합니다...")
            
            # 프로젝트 정보 조회
            project_info = await self.searcher.get_project_info(project_id)
            if not project_info:
                raise ValueError(f'Project ID {project_id} not found in project list')
            
            # 프로젝트 정보 추출
            project_path = project_info['original_folder']
            dept_code = str(project_info['department_code']).zfill(5)
            dept_name = project_info['department_name']
            
            await self.send_progress_message(ctx, 
                f"📂 프로젝트를 찾았습니다:\n"
                f"부서: {dept_code}_{dept_name}\n"
                f"이름: {project_info['project_name']}")
            
            if not Path(project_path).exists():
                raise FileNotFoundError(
                    f'Project path {project_path} does not exist. '
                    f'Ensure {NETWORK_BASE_PATH} drive is accessible.'
                )
            
            # 문서 검색 수행
            await self.send_progress_message(ctx, "🔎 문서 검색을 시작합니다...")
            all_documents = await self.searcher.search_all_documents(project_id)
            
            # 중간 결과 보고
            found_count = sum(1 for docs in all_documents.values() if docs)
            total_count = len(DOCUMENT_TYPES)
            await self.send_progress_message(ctx, 
                f"📊 문서 검색 완료: "
                f"총 {total_count}개 문서 유형 중 {found_count}개 유형 발견")
            
            # 결과 구성
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
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # AI 분석 수행 (요청 시)
            if use_ai:
                await self.send_progress_message(ctx, "🤖 AI 분석을 시작합니다...")
                try:
                    result['ai_analysis'] = await analyze_with_gemini(result, session)  # 세션 전달
                    await self.send_progress_message(ctx, "✨ AI 분석이 완료되었습니다")
                except Exception as ai_err:
                    print(f"[DEBUG] AI analysis failed: {str(ai_err)}")
                    result['ai_analysis'] = f"AI analysis failed: {str(ai_err)}"
            
            # JSON 파일로 저장
            await self.send_progress_message(ctx, "💾 결과를 저장하고 있습니다...")
            json_path = await self.save_audit_result(result)
            if json_path:
                result['json_file'] = json_path
            
            # 최종 결과 전송
            await self.send_to_discord(result, ctx)
            return result
            
        except Exception as e:
            error_result = {
                'error': str(e),
                'project_id': project_id,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            await self.send_to_discord(error_result, ctx)
            return error_result
        finally:
            if session:
                await session.close()  # 세션 정리

    async def send_to_discord(self, data, ctx=None):
        """Discord로 감사 결과 비동기 전송"""
        try:
            print("\n[DEBUG] === Sending to Discord ===")
            
            # 에러 결과 처리
            if 'error' in data:
                print(f"[DEBUG] Sending error message for project {data['project_id']}")
                message = (
                    f"❌ **Audit Error**\n"
                    f"Project ID: {data['project_id']}\n"
                    f"Error: {data['error']}\n"
                    f"Time: {data['timestamp']}"
                )
                await self.send_progress_message(ctx, message)
                return

            print(f"[DEBUG] Preparing success message for project {data['project_id']}")
            
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

            print(f"[DEBUG] Found documents: {len(found_docs)}")
            print(f"[DEBUG] Missing documents: {len(missing_docs)}")

            if found_docs:
                message += "✅ Found:\n- " + "\n- ".join(found_docs) + "\n\n"
            if missing_docs:
                message += "❌ Missing:\n- " + "\n- ".join(missing_docs) + "\n\n"

            if 'ai_analysis' in data:
                print("[DEBUG] Including AI analysis in message")
                message += f"🤖 AI Analysis:\n{data['ai_analysis']}\n\n"

            if 'json_file' in data:
                print("[DEBUG] Including JSON file path in message")
                message += f"\n💾 Results saved to: {data['json_file']}"

            message += f"\n⏰ {data['timestamp']}"
            
            # 메시지 전송
            await self.send_progress_message(ctx, message)
            print("[DEBUG] === Discord Message Sent ===\n")
            
        except Exception as e:
            error_msg = f"Discord notification error: {str(e)}"
            print(f"\n[DEBUG] ERROR in send_to_discord: {error_msg}")
            if ctx:
                await ctx.send(f"❌ {error_msg}")

    def clear_cache(self):
        """서비스 캐시 초기화"""
        self._cache = {}
        self.searcher.clear_cache()
        clear_analysis_cache()
        
    async def close(self):
        """리소스 정리"""
        if self._session:
            await self._session.close()
            self._session = None

    async def generate_summary_report(self, results):
        """전체 감사 결과에 대한 종합 보고서 생성"""
        try:
            print("\n[DEBUG] === Generating Summary Report ===")
            
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
            async with aiofiles.open(summary_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(summary, ensure_ascii=False, indent=2))
            
            print(f"[DEBUG] Summary report saved to: {summary_path}")
            return summary_path, summary
            
        except Exception as e:
            print(f"[ERROR] Failed to generate summary report: {str(e)}")
            return None, None

if __name__ == "__main__":
    async def run_test():
        service = AuditService()
        try:
            result = await service.audit_project("20180076", use_ai=True)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            await service.close()
    
    asyncio.run(run_test()) 

# python audit_service.py