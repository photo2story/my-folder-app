# app.py
import os
import sys
import asyncio
import threading
import requests
import io
from dotenv import load_dotenv
from flask import Flask, render_template, send_from_directory, jsonify, request, make_response
from flask_discord import DiscordOAuth2Session, requires_authorization, Unauthorized
from flask_cors import CORS


# Add my-flutter-app directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'my-flask-app')))

# 사용자 정의 모듈 임포트
import config  # config.py 임포트
from git_operations import move_files_to_images_folder
import pandas as pd


# 명시적으로 .env 파일 경로를 지정하여 환경 변수 로드
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
CORS(app)

app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI")
app.config["DISCORD_BOT_TOKEN"] = os.getenv("DISCORD_BOT_TOKEN")

discord_oauth = DiscordOAuth2Session(app)

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

# GitHub API URL
repo_url = 'https://api.github.com/repos/photo2story/my-foler-app/contents/static/images'

# .env 파일에서 GITHUB_TOKEN 가져오기
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# 헤더 설정 (인증을 위해 토큰 사용)
headers = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# 요청 보내기
response = requests.get(repo_url, headers=headers)

  

@app.route('/')
def index():
    return render_template('index.html')  # templates/index.html 파일을 렌더링

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory('', path)


# 로컬의 이미지 파일 경로 설정 (예: static/images 폴더 경로)
LOCAL_IMAGES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static', 'images'))

# 이미지 파일이 저장된 디렉토리 경로
IMAGE_DIRECTORY = 'static/images'

# 파일을 서빙하는 엔드포인트
@app.route('/static/images/<path:filename>')
def serve_image(filename):
    try:
        print(f"Serving image: {filename}")
        return send_from_directory(IMAGE_DIRECTORY, filename)
    except Exception as e:
        print(f"Error serving image {filename}: {e}")
        return jsonify({'error': str(e)}), 500

def fetch_csv_data(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        csv_data = response.content.decode('utf-8')
        df = pd.read_csv(io.StringIO(csv_data))
        df.fillna('', inplace=True)
        return df
    except requests.exceptions.RequestException as e:
        print(f'Error fetching CSV data: {e}')
        return None

@app.route('/data')
def data():
    df = fetch_csv_data(config.CSV_URL)
    if df is None:
        return "Error fetching data", 500
    return df.to_html()

def _build_cors_preflight_response():
    response = make_response()
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "POST")
    return response

# MockContext와 MockBot 클래스 정의
class MockContext:
    async def send(self, message):
        print(f"MockContext.send: {message}")
        # Discord로 메시지 전송
        requests.post(os.getenv('DISCORD_WEBHOOK_URL'), json={'content': message})

class MockBot:
    async def change_presence(self, status=None, activity=None):
        print(f"MockBot.change_presence: status={status}, activity={activity}")

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)


if __name__ == '__main__':
    from bot import run_bot
    threading.Thread(target=run_flask).start()
    asyncio.run(run_bot())

# source .venv/bin/activate
# #  .\.venv\Scripts\activate
# #  python app.py 
# pip install huggingface_hub
# huggingface-cli login
# EEVE-Korean-Instruct-10.8B-v1.0-GGUF
# ollama create EEVE-Korean-Instruct-10.8B -f Modelfile-V02
# ollama create EEVE-Korean-10.8B -f EEVE-Korean-Instruct-10.8B-v1.0-GGUF/Modelfile
# pip install ollama
# pip install chromadb
# pip install langchain
# ollama create EEVE-Korean-10.8B -f Modelfile
# git push heroku main
# heroku logs --tail -a he-flutter-app

# source .venv/bin/activate
# #  .\.venv\Scripts\activate
# #  python app.py 
# pip install huggingface_hub
# huggingface-cli login
# EEVE-Korean-Instruct-10.8B-v1.0-GGUF
# ollama create EEVE-Korean-Instruct-10.8B -f Modelfile-V02
# ollama create EEVE-Korean-10.8B -f EEVE-Korean-Instruct-10.8B-v1.0-GGUF/Modelfile
# pip install ollama
# pip install chromadb
# pip install langchain
# ollama create EEVE-Korean-10.8B -f Modelfile
# git push heroku main
# heroku logs --tail -a he-flutter-app

@app.route('/api/discord/messages', methods=['GET'])
def get_latest_discord_message():
    try:
        channelId = os.getenv('DISCORD_CHANNEL_ID')
        botToken = os.getenv('DISCORD_BOT_TOKEN')
        
        headers = {
            'Authorization': f'Bot {botToken}',
            'Content-Type': 'application/json',
        }
        
        response = requests.get(
            f'https://discord.com/api/v10/channels/{channelId}/messages?limit=1',
            headers=headers
        )
        
        if response.status_code == 200:
            messages = response.json()
            if messages:
                return jsonify(messages[0])
        
        return jsonify({'error': 'No messages found'}), 404
        
    except Exception as e:
        print(f"Error fetching Discord messages: {e}")
        return jsonify({'error': str(e)}), 500