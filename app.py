# app.py
# my-folder-app/app.py
# app.py
import os
import sys
import asyncio
import threading
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, jsonify, request, make_response
from flask_discord import DiscordOAuth2Session
from flask_cors import CORS

# my-flask-app 모듈 임포트 경로 조정
sys.path.append(os.path.join(os.path.dirname(__file__), 'my-flask-app'))
from audit_service import AuditService

# 명시적으로 .env 파일 경로를 지정하여 환경 변수 로드
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
CORS(app)

# 서비스 인스턴스 생성
audit_service = AuditService()

app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI")
app.config["DISCORD_BOT_TOKEN"] = os.getenv("DISCORD_BOT_TOKEN")

discord_oauth = DiscordOAuth2Session(app)

@app.route('/')
def index():
    """메인 페이지"""
    return jsonify({
        'status': 'ok',
        'message': 'Project Audit API Server is running',
        'endpoints': {
            'audit_project': '/audit_project/<project_id>'
        },
        'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'version': '1.0.0'
    })

def _build_cors_preflight_response():
    """CORS preflight 응답 생성"""
    response = make_response()
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
    return response

@app.route('/audit_project/<project_id>', methods=['GET'])
async def audit_project(project_id):
    """특정 프로젝트의 문서 존재 여부를 감사하는 API"""
    try:
        # AuditService를 통한 프로젝트 감사 수행
        use_ai = request.args.get('use_ai', 'false').lower() == 'true'
        result = await audit_service.audit_project(project_id, use_ai=use_ai)
        
        # 에러 결과 처리
        if 'error' in result:
            return jsonify(result), 500
            
        # Discord 알림 전송 (선택적)
        try:
            await audit_service.send_to_discord(result)
        except Exception as webhook_err:
            print(f"Discord webhook error: {str(webhook_err)}")
        
        return jsonify(result), 200
        
    except Exception as e:
        error_result = {
            'error': str(e),
            'project_id': project_id,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        return jsonify(error_result), 500

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

if __name__ == '__main__':
    from bot import run_bot
    threading.Thread(target=run_flask).start()
    asyncio.run(run_bot())