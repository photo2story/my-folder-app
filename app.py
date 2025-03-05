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
import pandas as pd
import csv
from functools import lru_cache

# my-flask-app 모듈 임포트 경로 조정
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_flask_app'))
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

# CSV 파일 경로
CSV_PATH = 'static/report/combined_report_20250305.csv'

@lru_cache(maxsize=128)
def load_csv_data():
    """CSV 데이터를 로드하고 캐시"""
    projects = []
    try:
        with open(CSV_PATH, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                projects.append(row)
        return projects
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return []

def convert_project_to_json(project):
    """프로젝트 데이터를 JSON 형식으로 변환"""
    documents = {
        'contract': {'exists': bool(int(project['contract_exists'])), 'details': []},
        'specification': {'exists': bool(int(project['specification_exists'])), 'details': []},
        'initiation': {'exists': bool(int(project['initiation_exists'])), 'details': []},
        'agreement': {'exists': bool(int(project['agreement_exists'])), 'details': []},
        'budget': {'exists': bool(int(project['budget_exists'])), 'details': []},
        'deliverable1': {'exists': bool(int(project['deliverable1_exists'])), 'details': []},
        'deliverable2': {'exists': bool(int(project['deliverable2_exists'])), 'details': []},
        'completion': {'exists': bool(int(project['completion_exists'])), 'details': []},
        'certificate': {'exists': bool(int(project['certificate_exists'])), 'details': []},
        'evaluation': {'exists': bool(int(project['evaluation_exists'])), 'details': []}
    }
    
    return {
        'project_id': project['project_id'],
        'project_name': project['project_name'],
        'department': project['department'],
        'status': project['Status'],
        'contractor': project['Contractor'],
        'documents': documents,
        'timestamp': project['timestamp']
    }

@app.route('/')
def index():
    """메인 페이지"""
    return jsonify({
        'status': 'ok',
        'message': 'Project Audit API Server is running',
        'endpoints': {
            'audit_project': '/audit_project/<project_id>',
            'audit_all': '/audit_all'
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
def audit_project(project_id):
    """특정 프로젝트의 감사 데이터를 반환"""
    try:
        use_ai = request.args.get('use_ai', 'false').lower() == 'true'
        projects = load_csv_data()
        
        for project in projects:
            if project['project_id'] == project_id:
                result = convert_project_to_json(project)
                if use_ai:
                    result['ai_analysis'] = 'AI analysis not implemented'
                return jsonify(result), 200
                
        return jsonify({'error': f'Project {project_id} not found'}), 404
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

@app.route('/audit_all', methods=['GET'])
def audit_all():
    """모든 프로젝트의 감사 데이터를 반환"""
    try:
        projects = load_csv_data()
        result = [convert_project_to_json(project) for project in projects]
        return jsonify({'projects': result}), 200
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 500

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

if __name__ == '__main__':
    from bot import run_bot
    threading.Thread(target=run_flask).start()
    asyncio.run(run_bot())