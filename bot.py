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

os.environ['SSL_CERT_FILE'] = certifi.where()

# Add my-flask-app directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'my-flask-app')))

# 사용자 정의 모듈 임포트
from config import DOCUMENT_TYPES, PROJECT_LIST_CSV, NETWORK_BASE_PATH, STATIC_DATA_PATH
from search_project_data import ProjectDocumentSearcher
from audit_service import AuditService
from export_report import generate_summary_report

# JSON 파일 저장 경로 설정
AUDIT_RESULTS_DIR = os.path.join(STATIC_DATA_PATH, 'audit_results')
os.makedirs(AUDIT_RESULTS_DIR, exist_ok=True)

async def save_audit_result(result):
    """감사 결과를 JSON 파일로 저장"""
    try:
        project_id = result['project_id']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"audit_{project_id}_{timestamp}.json"
        filepath = os.path.join(AUDIT_RESULTS_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        return filepath
    except Exception as e:
        print(f"Error saving audit result: {e}")
        return None

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

# GITHUB_RAW_BASE_URL = "https://raw.githubusercontent.com/photo2story/my-flask-app/main/static/images"
# CSV_PATH = f"{GITHUB_RAW_BASE_URL}/stock_market.csv"
# GITHUB_RAW_BASE_URL = config.STATIC_IMAGES_PATH
# CSV_PATH = config.CSV_PATH

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

# Gemini API 설정,디스코드에서 제미니와 대화하기 위한 모델 생성
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# ping_command 비동기 함수 정의
async def ping_command():
    try:
        print("Executing ping command...")
        # Context를 생성하고 명령어 실행
        # Analysis logic
        await backtest_and_send(ctx, 'AAPL', option_strategy, bot)
    except Exception as e:
        print(f"Error in ping command: {e}")

        
@bot.event
async def on_ready():
    """봇이 준비되었을 때 실행되는 이벤트"""
    global bot_started
    if not bot_started:
        print(f'Logged in as {bot.user.name}')
        print() # 빈 줄 출력
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            await channel.send(f'Bot has successfully logged in as {bot.user.name}')
        else:
            print(f'Failed to get channel with ID {CHANNEL_ID}')
        bot_started = True
        await bot.change_presence(activity=discord.Game(name="audit 명령어로 프로젝트 감사"))

@bot.command()
@check_duplicate_message()
async def ping(ctx):
    try:
        await ctx.send(f'pong: {bot.user.name}')
        print(f'Ping command received and responded with pong.')
    except Exception as e:
        print(f"Error in ping command: {e}")

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
        

async def analyze_with_gemini(project_data):
    """Gemini AI를 사용하여 프로젝트 문서를 분석"""
    try:
        # 분석을 위한 프롬프트 구성
        prompt = f"""
프로젝트 ID {project_data['project_id']}에 대한 문서 분석을 수행해주세요.

프로젝트 정보:
- 부서: {project_data['department']}
- 프로젝트명: {project_data['project_name']}

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
        return f"AI 분석 중 오류 발생: {str(e)}"

@bot.command(name='audit')
async def audit(ctx, *, query: str = None):
    """프로젝트 감사 명령어"""
    try:
        if not query:
            help_message = (
                "🔍 프로젝트 감사 명령어 사용법:\n"
                "!audit [project_id] [department_code] [use_ai] - 특정 프로젝트 감사\n"
                "!audit all - 전체 프로젝트 감사\n"
                "use_ai는 'true' 또는 'use ai'로 입력 가능 (예: !audit 20240178 06010 true)"
            )
            await ctx.send(help_message)
            return

        # 쿼리 파싱 (project_id, department_code, use_ai 추출)
        args = query.split()
        if len(args) < 1:
            await ctx.send("❌ 올바른 형식이 아닙니다. !audit [project_id] [department_code] [use_ai]를 입력하세요.")
            return

        project_id = args[0].lower()
        department_code = None
        use_ai = False

        # project_id에서 숫자만 추출 (영문 접두사 제거)
        numeric_project_id = re.sub(r'[^0-9]', '', project_id)

        # department_code와 use_ai 추출
        if len(args) > 1:
            if re.match(r'^\d{5}$', args[1]):  # 5자리 숫자로 department_code 검증
                department_code = args[1].zfill(5)  # 5자리로 패딩
                if len(args) > 2:
                    use_ai = args[2].lower() in ['true', 'use ai']
            else:
                use_ai = args[1].lower() in ['true', 'use ai']
                if len(args) > 2 and re.match(r'^\d{5}$', args[2]):
                    department_code = args[2].zfill(5)

        if project_id == 'all':
            await ctx.send("🔍 전체 프로젝트 감사를 시작합니다...")
            
            # 프로젝트 목록 읽기
            df = pd.read_csv(PROJECT_LIST_CSV)
            total_projects = len(df)
            
            await ctx.send(f"📊 총 {total_projects}개 프로젝트를 처리합니다...")
            
            # 결과 저장용 리스트
            all_results = []
            success_count = 0
            error_count = 0
            
            # 각 프로젝트 감사 수행
            for idx, row in df.iterrows():
                try:
                    current_id = str(row['project_id'])
                    progress = f"({idx + 1}/{total_projects})"
                    
                    if idx % 10 == 0:  # 진행상황 10개 단위로 보고
                        await ctx.send(f"🔄 진행중... {progress}")
                    
                    result = await audit_service.audit_project(current_id, use_ai, ctx)
                    all_results.append(result)
                    
                    if 'error' not in result:
                        success_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    error_count += 1
                    print(f"Error processing project {current_id}: {str(e)}")
            
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
            
            await ctx.send(report)
            
        else:
            # 단일 프로젝트 감사 (numeric_project_id와 department_code 사용)
            result = await audit_service.audit_project(numeric_project_id, department_code, use_ai, ctx)
            if 'error' in result:
                await ctx.send(f"❌ 감사 실패: {result['error']}")
                
    except Exception as e:
        await log_debug(ctx, f"감사 명령어 실행 중 오류 발생", error=e)
        await ctx.send(f"❌ 오류 발생: {str(e)}")
        
        
@bot.command(name='clear_cache')
async def clear_cache(ctx):
    """캐시 초기화 명령어"""
    try:
        audit_service.clear_cache()
        await ctx.send("캐시가 초기화되었습니다.")
    except Exception as e:
        await ctx.send(f"캐시 초기화 중 오류 발생: {str(e)}")


@bot.command(name='project')
async def project(ctx, *, project_id: str = None):
    """프로젝트 정보 조회 명령어"""
    try:
        if not project_id or not re.match(r'^\d+$', project_id):  # 숫자만 포함된 project_id 확인
            help_message = (
                "🔍 프로젝트 정보 조회 명령어 사용법:\n"
                "!project [project_id] - 특정 프로젝트 ID로 정확히 일치하는 프로젝트 조회 (예: !project 20240178, 숫자만 입력, 접미사 없는 프로젝트만)"
            )
            await ctx.send(help_message)
            return

        # get_project.py에서 프로젝트 데이터 조회
        from get_project import get_project
        projects = get_project(project_id)

        if not projects:
            await ctx.send(f"❌ 프로젝트 ID {project_id}에 해당하는 정확히 일치하는 데이터가 없습니다 (접미사 없는 프로젝트).")
            return

        # 디스코드에 결과 전송 (가독성 개선)
        message = f"📋 **프로젝트 ID {project_id}에 해당하는 정확히 일치하는 프로젝트 목록 (접미사 없음)**\n"
        message += "------------------------\n"
        for idx, project in enumerate(projects, 1):
            message += f"\n{idx}. **사업코드**: {project['사업코드']}\n"
            message += f"   **사업명**: {project['사업명']}\n"
            message += f"   **부서**: {project['PM부서']} (코드: {project['부서코드']})\n"
            message += f"   **진행상태**: {project['진행상태']}\n"
            message += f"   **주관사 여부**: {project['주관사']}\n"
            message += "------------------------\n"
        
        message += "\n사용자가 원하는 프로젝트를 선택하세요 (예: !audit [사업코드] [use_ai])."
        await ctx.send(message)

    except Exception as e:
        await log_debug(ctx, f"프로젝트 조회 명령어 실행 중 오류 발생", error=e)
        await ctx.send(f"❌ 오류 발생: {str(e)}")

async def run_bot():
    """봇 실행"""
    await bot.start(TOKEN)

def run_server():
    port = int(os.environ.get('PORT', 8080))
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