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

os.environ['SSL_CERT_FILE'] = certifi.where()

# 플라스크 앱 디렉토리 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'my_flask_app')))

# 사용자 정의 모듈 임포트
from config import DOCUMENT_TYPES, PROJECT_LIST_CSV, NETWORK_BASE_PATH, STATIC_DATA_PATH, DISCORD_WEBHOOK_URL
from search_project_data import ProjectDocumentSearcher
from audit_service import AuditService
from export_report import generate_summary_report
from get_project import get_project_info
from audit_message import send_audit_to_discord, send_audit_status_to_discord  # audit_message.py 임포트

# JSON 파일 저장 경로 설정
AUDIT_RESULTS_DIR = os.path.join(STATIC_DATA_PATH, 'audit_results')
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
            total_projects = len(df)
            
            await send_audit_status_to_discord(ctx, f"📊 총 {total_projects}개 프로젝트를 처리합니다...")
            
            # 결과 저장용 리스트
            all_results = []
            success_count = 0
            error_count = 0
            
            # 각 프로젝트 감사 수행 (project_id 순회)
            for idx, row in df.iterrows():
                project_id_col = 'project_id'  # 기본 열 이름
                if 'project_id' not in df.columns:
                    possible_cols = ['ProjectID', '사업코드', 'projectId', 'Depart_ProjectID']
                    for col in possible_cols:
                        if col in df.columns:
                            project_id_col = col
                            break
                    if project_id_col == 'project_id':
                        raise KeyError("No valid project_id column found in audit_targets_new.csv")
                
                # Depart_ProjectID에서 부서코드와 사업코드를 추출
                project_id_value = str(row[project_id_col]).strip()
                if project_id_col == 'Depart_ProjectID':
                    # '부서코드_C사업코드' 형식에서 부서코드와 사업코드 분리 (예: '01010_C20070089' -> '01010', '20070089')
                    match = re.match(r'(\d+)_C(\d+)$', project_id_value)
                    if match:
                        department_code = match.group(1).zfill(5)  # 부서코드 (5자리로 패딩)
                        project_id = match.group(2)  # 사업코드 (project_id)
                    else:
                        # 정규식 매칭 실패 시 숫자만 추출 (백업)
                        parts = project_id_value.split('_')
                        if len(parts) > 1 and parts[1].startswith('C'):
                            department_code = re.sub(r'[^0-9]', '', parts[0]).zfill(5)
                            project_id = re.sub(r'[^0-9]', '', parts[1][1:])
                        else:
                            department_code = re.sub(r'[^0-9]', '', project_id_value.split('_')[0]).zfill(5)
                            project_id = re.sub(r'[^0-9]', '', project_id_value.split('_')[1] if len(project_id_value.split('_')) > 1 else project_id_value)
                else:
                    # 다른 열 이름의 경우 숫자만 추출
                    project_id = re.sub(r'[^0-9]', '', project_id_value)
                    department_code = None  # 부서코드는 별도로 추출 필요

                # 디버깅: 추출된 project_id와 department_code 출력
                logger.debug(f"Extracted project_id for row {idx + 1}: {project_id}")
                logger.debug(f"Extracted department_code for row {idx + 1}: {department_code}")

                # 부서 코드 열 확인 및 추출 (기본적으로 Depart_ProjectID에서 이미 추출했으므로 확인만)
                department_code_col = 'department_code'  # 기본 부서 코드 열 이름
                if 'department_code' not in df.columns:
                    possible_dept_cols = ['departmentCode', '부서코드', 'Depart', 'department']
                    for col in possible_dept_cols:
                        if col in df.columns:
                            department_code_col = col
                            break
                
                if department_code is None and department_code_col in row:
                    department_code = str(row[department_code_col]).zfill(5) if pd.notna(row[department_code_col]) else None
                    logger.debug(f"Overridden department_code from column {department_code_col}: {department_code}")

                # 상태와 계약자 정보 추출 (CSV에서 직접 가져오기)
                status = str(row.get('Status', 'Unknown')).strip()
                contractor = str(row.get('Contractor', 'Unknown')).strip()

                progress = f"({idx + 1}/{total_projects})"
                
                if idx % 10 == 0:  # 진행상황 10개 단위로 보고
                    await send_audit_status_to_discord(ctx, f"🔄 진행중... {progress}")
                
                # audit {projectID} 호출 방식으로 단일 프로젝트 감사
                await send_audit_status_to_discord(ctx, f"🔍 프로젝트 {project_id} 감사를 시작합니다...")
                try:
                    result = await audit_service.audit_project(project_id, department_code, False, ctx)  # 기본 감사 (AI 없이)
                    all_results.append(result)
                    
                    if 'error' not in result:
                        success_count += 1
                        await send_audit_status_to_discord(ctx, f"✅ 프로젝트 {project_id} 감사 완료: {result.get('timestamp', '시간정보 없음')} {progress}")
                        await send_audit_to_discord(result)  # 웹훅으로 결과 전송
                    else:
                        error_count += 1
                        await send_audit_status_to_discord(ctx, f"❌ 프로젝트 {project_id} 감사 실패: {result['error']} {progress}")
                except Exception as e:
                    error_count += 1
                    error_msg = f"Error processing project {project_id}: {str(e)}"
                    logger.error(error_msg)
                    await send_audit_status_to_discord(ctx, f"❌ {error_msg} {progress}")
                    continue
                
                await asyncio.sleep(1)  # 각 프로젝트 감사 사이에 1초 대기

            # 종합 보고서 생성
            summary_path, summary = await generate_summary_report(all_results, verbose=True)
            
            # 결과 출력
            report = (
                "📋 전체 감사 완료 보고서\n"
                "------------------------\n"
                f"✅ 감사 성공: {success_count}개\n"
                f"❌ 감사 실패: {error_count}개\n"
                f"📊 총 처리: {total_projects}개\n"
                "------------------------\n"
                "📈 위험도 분석:\n"
            )
            
            if summary and 'risk_levels' in summary:
                report += (
                    f"🔴 고위험: {summary['risk_levels']['high']}개\n"
                    f"🟡 중위험: {summary['risk_levels']['medium']}개\n"
                    f"🟢 저위험: {summary['risk_levels']['low']}개\n"
                )
            
            if summary_path:
                report += f"\n💾 종합 보고서 저장됨: {summary_path}"
                if 'csv_report' in summary:
                    report += f"\n📊 CSV 보고서 저장됨: {summary['csv_report']}"
            
            await send_audit_status_to_discord(ctx, report)
            await send_audit_to_discord(all_results)  # 웹훅으로 종합 결과 전송

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
                    await send_audit_to_discord(result)  # 웹훅으로 결과 전송
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