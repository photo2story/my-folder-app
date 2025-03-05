# my-folder-app/bot.py



import os
import sys
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import tasks, commands
from discord.ext.commands import Context
import certifi
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import google.generativeai as genai
import requests
from datetime import datetime
import pandas as pd
import traceback
import json
import re
import logging  # logging 모듈 추가
import aiofiles

os.environ['SSL_CERT_FILE'] = certifi.where()

# 플라스크 앱 디렉토리 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'my_flask_app')))

# 사용자 정의 모듈 임포트
from config import DOCUMENT_TYPES, PROJECT_LIST_CSV, NETWORK_BASE_PATH, STATIC_PATH, STATIC_DATA_PATH, DISCORD_WEBHOOK_URL
from search_project_data import ProjectDocumentSearcher
from audit_service import AuditService
from export_report import generate_summary_report  # 기존 import 유지, generate_combined_report 추가로 임포트
from generate_summary import generate_combined_report  # generate_summary.py에서 함수 임포트
from get_project import get_project_info
from audit_message import send_audit_to_discord, send_audit_status_to_discord  # audit_message.py 임포트

# JSON 파일 저장 경로 설정
# 변경: 감사 결과를 'static/results/'에 저장
AUDIT_RESULTS_DIR = os.path.join(STATIC_PATH, 'results')  # static/data/results
os.makedirs(AUDIT_RESULTS_DIR, exist_ok=True)


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)  # logger 객체 전역으로 초기화

# 디버깅을 위한 로깅 함수
async def log_debug(ctx, message, error=None):
    debug_msg = f"🔍 DEBUG: {message}"
    if error:
        debug_msg += f"\n❌ Error: {str(error)}"
        debug_msg += f"\n🔍 Traceback:\n```python\n{traceback.format_exc()}```"
    await ctx.send(debug_msg)

# 명시적으로 .env 파일 경로를 지정하여 환경 변수 로드
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

TOKEN = os.getenv('DISCORD_APPLICATION_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')  # Gemini API 키 로드

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='', intents=intents)

# 중복 메시지 처리
processed_message_ids = set()

def check_duplicate_message():
    async def predicate(ctx):
        if ctx.message.id in processed_message_ids:
            return False
        processed_message_ids.add(ctx.message.id)
        return True
    return commands.check(predicate)

bot_started = False

# 서비스 인스턴스 생성
audit_service = AuditService()

# Gemini API 설정, 디스코드에서 제미니와 대화하기 위한 모델 생성
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

@bot.event
async def on_ready():
    """봇이 준비되었을 때 실행되는 이벤트"""
    global bot_started
    if not bot_started:
        logger.info(f'Logged in as {bot.user.name}')
        print()  # 빈 줄 출력
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            await channel.send(f'Bot has successfully logged in as {bot.user.name}')
        else:
            logger.error(f'Failed to get channel with ID {CHANNEL_ID}')
        bot_started = True
        await bot.change_presence(activity=discord.Game(name="audit 명령어로 프로젝트 감사"))

@bot.command(name='test_audit')
async def test_audit(ctx, project_id: str):
    project_id = "20240178"
    await audit(ctx, project_id)  # audit 명령어 호출


@bot.command()
@check_duplicate_message()
async def ping(ctx):
    try:
        await ctx.send(f'pong: {bot.user.name}')
        logger.info(f'Ping command received and responded with pong.')
    except Exception as e:
        logger.error(f"Error in ping command: {e}")

@bot.command()
@check_duplicate_message()
async def gchat(ctx, *, query: str = None):
    if query is None or query.strip() == "":
        await ctx.send("제미니와 대화하려면 메시지를 입력해주세요.")
        return

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(query)
        await ctx.send(response.text)
    except Exception as e:
        await ctx.send(f"Gemini와의 대화 중 오류가 발생했습니다: {e}")
        logger.error(f"Error in gchat command: {e}")

async def analyze_with_gemini(project_data):
    """Gemini AI를 사용하여 프로젝트 문서를 분석"""
    try:
        # 분석을 위한 프롬프트 구성
        prompt = f"""
프로젝트 ID {project_data['project_id']}에 대한 문서 분석을 수행해주세요.

프로젝트 정보:
- 부서: {project_data['department']}
- 프로젝트명: {project_data['project_name']}
- 상태: {project_data.get('status', 'Unknown')}
- 계약자: {project_data.get('contractor', 'Unknown')}

문서 현황:
"""
        for doc_type, info in project_data['documents'].items():
            doc_name = DOCUMENT_TYPES[doc_type]['name']
            status = "있음" if info['exists'] else "없음"
            files_count = len(info['details']) if info['exists'] else 0
            prompt += f"- {doc_name}: {status} (파일 {files_count}개)\n"
            if info['exists'] and files_count > 0:
                prompt += "  파일 목록:\n"
                for file in info['details'][:3]:  # 처음 3개만 표시
                    prompt += f"    - {os.path.basename(file)}\n"

        prompt += """
위 정보를 바탕으로 다음 사항을 분석해주세요:
1. 필수 문서의 존재 여부와 완성도
2. 누락된 중요 문서가 있다면 어떤 것인지
3. 프로젝트 문서화 상태에 대한 전반적인 평가
4. 개선이 필요한 부분에 대한 제안

분석 결과를 명확하고 구체적으로 제시해주세요."""

        # Gemini API 호출
        response = model.generate_content(prompt)
        
        # 응답 형식화
        analysis = f"""프로젝트 문서 분석 결과:
{response.text}"""
        
        return analysis
    except Exception as e:
        logger.error(f"Error in analyze_with_gemini: {e}")
        return f"AI 분석 중 오류 발생: {str(e)}"

@bot.command(name='audit')
async def audit(ctx, *, query: str = None):
    """프로젝트 감사 명령어"""
    try:
        if not query:
            help_message = (
                "🔍 프로젝트 감사 명령어 사용법:\n"
                "!audit {projectID} - 특정 프로젝트 ID 감사 (예: !audit 20240178)\n"
                "!audit all - audit_targets_new.csv에 있는 모든 프로젝트 감사"
            )
            await send_audit_status_to_discord(ctx, help_message)
            return

        # 쿼리 파싱
        args = query.split()
        if len(args) < 1:
            await send_audit_status_to_discord(ctx, "❌ 올바른 형식이 아닙니다. !audit {projectID} 또는 !audit all를 입력하세요.")
            return

        if args[0].lower() == 'all':
            # audit_targets_new.csv에 있는 모든 프로젝트 감사
            await send_audit_status_to_discord(ctx, "🔍 audit_targets_new.csv에 있는 모든 프로젝트 감사를 시작합니다...")
            
            # audit_targets_new.csv 로드
            audit_targets_csv = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
            if not os.path.exists(audit_targets_csv):
                await send_audit_status_to_discord(ctx, f"❌ audit_targets_new.csv 파일을 찾을 수 없습니다: {audit_targets_csv}")
                logger.error(f"CSV file not found: {audit_targets_csv}")
                return
            
            df = pd.read_csv(audit_targets_csv, encoding='utf-8-sig')
            # ProjectID에서 앞의 영문자(A-Z) 한 글자 제거
            df['ProjectID'] = df['ProjectID'].apply(lambda x: re.sub(r'^[A-Za-z]', '', str(x)))
            total_projects = len(df)
            
            await send_audit_status_to_discord(ctx, f"📊 총 {total_projects}개 프로젝트를 처리합니다...")
            
            # 결과 저장용 리스트
            all_results = []
            success_count = 0
            error_count = 0
            
            # 각 프로젝트 감사 수행 (ProjectID만 사용)
            for idx, row in df.iterrows():
                project_id = str(row['ProjectID'])  # ProjectID만 사용
                search_folder = str(row['search_folder'])
                
                progress = f"({idx + 1}/{total_projects})"
                
                if idx % 10 == 0:  # 진행상황 10개 단위로 보고
                    await send_audit_status_to_discord(ctx, f"🔄 진행중... {progress}")
                
                await send_audit_status_to_discord(ctx, f"🔍 프로젝트 {project_id} 감사를 시작합니다...")
                try:
                    if search_folder in ["No folder", "No directory"]:
                        # No folder 또는 No directory인 경우 0,0,0,0,0,0,0 출력 (폴더 검색 생략, 성과 없음)
                        result = {
                            "project_id": project_id,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "documents_found": 0,
                            "risk_level": 0,
                            "missing_docs": 0,
                            "department": row['Depart'],
                            "status": row['Status'],
                            "contractor": row['Contractor'],
                            "project_name": row['ProjectName'],
                            "result": "0,0,0,0,0,0,0 (Folder missing)"
                        }
                        all_results.append(result)
                        success_count += 1
                        await send_audit_status_to_discord(ctx, f"✅ 프로젝트 {project_id} 감사 완료: 0,0,0,0,0,0,0 (Folder missing) {progress}")
                        logger.info(f"Project {project_id}: No folder/No directory, returning default result 0,0,0,0,0,0,0")
                    else:
                        # 경로가 있는 경우 직접 검색
                        result = await audit_service.audit_project(project_id, None, False, ctx)  # ProjectID만 전달
                        if 'error' not in result:
                            all_results.append(result)
                            success_count += 1
                            await send_audit_status_to_discord(ctx, f"✅ 프로젝트 {project_id} 감사 완료: {result.get('timestamp', '시간정보 없음')} {progress}")
                        else:
                            error_count += 1
                            await send_audit_status_to_discord(ctx, f"❌ 프로젝트 {project_id} 감사 실패: {result['error']} {progress}")
                    await asyncio.sleep(1)  # 각 프로젝트 감사 사이에 1초 대기
                except Exception as e:
                    error_count += 1
                    error_msg = f"Error processing project {project_id}: {str(e)}"
                    logger.error(error_msg)
                    await send_audit_status_to_discord(ctx, f"❌ {error_msg} {progress}")
                    continue
                
            # 종합 보고서 생성 (generate_combined_report 호출)
            results_dir = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results')
            output_path = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'report', 'combined_report')
            summary_path = await generate_combined_report(results_dir, output_path, verbose=True)
            
            # 결과 출력 (기존 보고서에 종합 보고서 추가)
            report = (
                "📋 전체 감사 완료 보고서\n"
                "------------------------\n"
                f"✅ 감사 성공: {success_count}개\n"
                f"❌ 감사 실패: {error_count}개\n"
                f"📊 총 처리: {total_projects}개\n"
                "------------------------\n"
                "📈 위험도 분석:\n"
            )
            
            if summary_path:
                report += f"\n✅ 통합 보고서가 생성되었습니다: {summary_path}"
            else:
                report += "\n❌ 통합 보고서 생성에 실패했습니다."
            
            # 감사 결과를 현재 채널에 표시
            await ctx.send(report)
            
            # 결과를 JSON 파일로 저장
            results_dir = os.path.join(STATIC_PATH, 'results')
            os.makedirs(results_dir, exist_ok=True)
            output_path = os.path.join(results_dir, f'audit_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            
            async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(all_results, ensure_ascii=False, indent=2))
            
            logger.info(f"감사 결과 저장 완료: {output_path}")
            
            # 통합 보고서 생성
            report_dir = os.path.join(STATIC_PATH, 'report')
            os.makedirs(report_dir, exist_ok=True)
            summary_path = await generate_combined_report(results_dir, os.path.join(report_dir, 'combined_report'), verbose=True)
            
            # 통합 보고서 상태를 report에 추가
            if summary_path:
                report += f"\n✅ 통합 보고서가 생성되었습니다: {summary_path}"
            else:
                report += "\n❌ 통합 보고서 생성에 실패했습니다."
            
            # 최종 결과를 현재 채널에 표시
            await ctx.send(report)
            
            logger.info(f"감사 결과 저장 완료: {output_path}")

        else:
            # 단일 프로젝트 감사 (project_id로 실행)
            project_id = args[0]  # projectID로 입력
            numeric_project_id = re.sub(r'[^0-9]', '', project_id)  # 숫자만 추출
            department_code = None  # 기본값 (PROJECT_LIST_CSV에서 자동 매핑)
            
            await send_audit_status_to_discord(ctx, f"🔍 프로젝트 {project_id} 감사를 시작합니다...")
            try:
                result = await audit_service.audit_project(numeric_project_id, department_code, False, ctx)  # 기본 감사 (AI 없이)
                if 'error' in result:
                    await send_audit_status_to_discord(ctx, f"❌ 감사 실패: {result['error']}")
                else:
                    # result가 리스트일 경우 첫 번째 요소, 단일 딕셔너리일 경우 그대로 사용
                    audit_result = result[0] if isinstance(result, list) else result
                    await send_audit_status_to_discord(ctx, f"✅ 프로젝트 {project_id} 감사 완료: {audit_result.get('timestamp', '시간정보 없음')}")
                    
                    # 결과 디렉토리 및 파일 경로 설정
                    results_dir = os.path.join(STATIC_PATH, 'results')
                    os.makedirs(results_dir, exist_ok=True)
                    # 결과를 JSON 파일로 저장 (리스트 형태로 저장)
                    audit_results = [audit_result] if isinstance(audit_result, dict) else audit_result
                    output_path = os.path.join(results_dir, f'audit_{numeric_project_id}.json')
                    async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(audit_results, ensure_ascii=False, indent=2))
                    
                    logger.info(f"감사 결과 저장 완료: {output_path}")
                    
                    # 통합 보고서 생성
                    report_dir = os.path.join(STATIC_PATH, 'report')
                    os.makedirs(report_dir, exist_ok=True)
                    summary_path = await generate_combined_report(results_dir, os.path.join(report_dir, 'combined_report'), verbose=True)
                    
                    # 통합 보고서 상태를 report에 추가
                    # report 내용 생성
                    report = f"📋 **프로젝트 ID {numeric_project_id} 감사 결과**\n"
                    report += "------------------------\n"
                    report += f"부서: {audit_result.get('department', 'Unknown')}\n"
                    report += f"프로젝트명: {audit_result.get('project_name', 'Unknown')}\n"
                    report += f"상태: {audit_result.get('status', 'Unknown')}\n"
                    report += f"계약자: {audit_result.get('contractor', 'Unknown')}\n"
                    report += "------------------------\n"
                    report += "📑 문서 현황:\n"

                    for doc_type, info in audit_result.get('documents', {}).items():
                        doc_name = DOCUMENT_TYPES.get(doc_type, {}).get('name', doc_type)
                        if info.get('exists', False):
                            report += f"✅ {doc_name}: {len(info.get('details', []))}개\n"
                        else:
                            report += f"❌ {doc_name}: 없음\n"

                    report += "------------------------\n"
                    report += f"⏰ 감사 완료: {audit_result.get('timestamp', '시간정보 없음')}\n"

                    # 통합 보고서가 생성된 경우 추가
                    if summary_path:
                        report += f"📊 통합 보고서: {summary_path}\n"
                    else:
                        report += "❌ 통합 보고서 생성 실패\n"

                    # ✅ 메시지를 한 번만 전송
                    await ctx.send(report)
            except Exception as e:
                error_msg = f"Error processing project {project_id}: {str(e)}"
                logger.error(error_msg)
                await send_audit_status_to_discord(ctx, f"❌ {error_msg}")

    except Exception as e:
        await log_debug(ctx, f"감사 명령어 실행 중 오류 발생", error=e)
        await send_audit_status_to_discord(ctx, f"❌ 오류 발생: {str(e)}")

@bot.command(name='clear_cache')
async def clear_cache(ctx):
    """캐시 초기화 명령어"""
    try:
        audit_service.searcher.clear_cache()  # ProjectDocumentSearcher의 clear_cache 호출
        await ctx.send("캐시가 초기화되었습니다.")
        logger.info("Cache cleared successfully")
    except Exception as e:
        await ctx.send(f"캐시 초기화 중 오류 발생: {str(e)}")
        logger.error(f"Error clearing cache: {e}")

@bot.command(name='project')
async def project(ctx, *, project_id: str = None):
    """프로젝트 정보 조회 명령어"""
    try:
        if not project_id:
            help_message = (
                "🔍 프로젝트 정보 조회 명령어 사용법:\n"
                "!project [project_id] - 프로젝트 ID로 프로젝트 조회 (예: !project 20180076)"
            )
            await ctx.send(help_message)
            return

        # 숫자만 추출
        numeric_project_id = re.sub(r'[^0-9]', '', project_id)
        
        # 디버그 메시지 출력
        await ctx.send(f"🔍 프로젝트 ID {numeric_project_id} 검색 중...")
        
        # get_project.py에서 프로젝트 데이터 조회
        project_info = get_project_info(numeric_project_id)  # get_project_info 사용
        
        # 디버그: 반환된 데이터 구조 확인
        logger.debug(f"Debug - Project Info: {project_info}")
        
        if not project_info:
            await ctx.send(f"❌ 프로젝트 ID {numeric_project_id}에 해당하는 데이터가 없습니다.")
            return

        # 디스코드에 결과 전송
        message = f"📋 **프로젝트 ID {numeric_project_id} 정보**\n"
        message += "------------------------\n"
        
        # 딕셔너리 형태로 모든 키-값 쌍 출력
        for key, value in project_info.items():
            message += f"**{key}**: {value}\n"
        
        message += "------------------------\n"
        message += f"\n프로젝트 감사를 실행하려면 다음 명령어를 사용하세요:\n"
        message += f"!audit {numeric_project_id}"
        
        await ctx.send(message)

    except Exception as e:
        await log_debug(ctx, f"프로젝트 조회 명령어 실행 중 오류 발생\n반환된 데이터: {project_info if 'project_info' in locals() else 'None'}", error=e)
        await ctx.send(f"❌ 오류 발생: {str(e)}")



async def run_bot():
    """봇 실행"""
    await bot.start(TOKEN)

def run_server():
    port = int(os.environ.get('PORT', 5000))
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print(f'Starting server on port {port}')
    httpd.serve_forever()

if __name__ == '__main__':
    # HTTP 서버 시작
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # 봇 실행
    asyncio.run(run_bot())

r"""
Remove-Item -Recurse -Force .venv

python3 -m venv .venv
.\\.venv\Scripts\activate
pip install --force-reinstall ./mplchart-0.0.8-py3-none-any.whl
pip install -r requirements.txt



source .venv/bin/activate
python bot.py
.\\.venv\Scripts\activate   
python app.py   
docker build -t asia.gcr.io/my-flask-app-429017/bot .
docker push asia.gcr.io/my-flask-app-429017/bot
gcloud run deploy bot --image asia.gcr.io/my-flask-app-429017/bot --platform managed --region asia-northeast3 --allow-unauthenticated

원격저장소 내용으로 강제 업데이트
git fetch origin
git checkout main
git reset --hard origin/main
로컬내용을 원격저장소에 강제업데이트

git reset --hard c108992
git push origin main --force
git add .
git commit -m "Reverted to commit hard c108992 and continued work"

git log --grep="


nix-shell
"""