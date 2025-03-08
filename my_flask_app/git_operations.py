# /my_flask_app/git_operations.py

import os
import base64
import requests
from dotenv import load_dotenv
import hashlib
import pandas as pd
import asyncio
import logging
import config
import subprocess
from datetime import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# .env 파일 로드
load_dotenv()

GITHUB_API_URL = "https://api.github.com"
GITHUB_FLASK_REPO = "photo2story/my-folder-app"
GITHUB_BRANCH = "main"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    GITHUB_TOKEN = os.getenv("PERSONAL_ACCESS_TOKEN")

logger.info(f"Using GitHub token: {GITHUB_TOKEN[:10]}...")

# SHA 해시 계산 함수
def calculate_file_sha(file_path):
    sha_hash = hashlib.sha1()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha_hash.update(chunk)
    return sha_hash.hexdigest()

# Git 명령어 실행 함수
def run_git_command(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Git command failed: {command}\n{result.stderr}")
            raise Exception(f"Git command failed: {result.stderr}")
        logger.info(f"Git command succeeded: {command}\n{result.stdout}")
        return result.stdout
    except Exception as e:
        logger.error(f"Error running git command {command}: {str(e)}")
        raise

async def sync_files_to_github(file_path=None):
    """특정 파일 또는 results 디렉토리의 모든 JSON 및 CSV 파일을 GitHub에 업로드"""
    try:
        # 변경된 파일 목록 수집
        files_to_commit = []
        if file_path and os.path.exists(file_path):
            # 단일 파일 처리
            files_to_commit.append(file_path)
        else:
            # results 디렉토리 및 report 디렉토리 전체 처리
            results_dir = os.path.join(config.STATIC_PATH, 'results')
            if not os.path.exists(results_dir):
                logger.warning(f"Results directory does not exist: {results_dir}")
                return

            for root, dirs, files in os.walk(results_dir):
                for filename in files:
                    if filename.endswith('.json') or filename.endswith('.csv'):
                        file_path = os.path.join(root, filename)
                        files_to_commit.append(file_path)

            # report 디렉토리의 combined_report.csv 처리
            report_dir = os.path.join(config.STATIC_PATH, 'report')
            if os.path.exists(report_dir):
                for filename in os.listdir(report_dir):
                    if filename.startswith("combined_report") and filename.endswith('.csv'):
                        file_path = os.path.join(report_dir, filename)
                        files_to_commit.append(file_path)

        if not files_to_commit:
            logger.info("No files to commit to GitHub")
            return

        # 파일 상태 확인 및 커밋 준비
        added_files = []
        for file_path in files_to_commit:
            relative_path = os.path.relpath(os.path.dirname(file_path), config.STATIC_PATH).replace(os.sep, '/')
            github_path = f"static/{relative_path}/{os.path.basename(file_path)}"

            url = f"{GITHUB_API_URL}/repos/{GITHUB_FLASK_REPO}/contents/{github_path}"
            headers = {
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            response = requests.get(url, headers=headers, params={"ref": GITHUB_BRANCH})
            
            upload_needed = True
            if response.status_code == 200:
                file_data = response.json()
                remote_sha = file_data['sha']
                local_sha = calculate_file_sha(file_path)
                if remote_sha == local_sha:
                    logger.info(f"{os.path.basename(file_path)} is up-to-date in GitHub, skipping upload.")
                    upload_needed = False
            elif response.status_code == 404:
                logger.info(f"{os.path.basename(file_path)} does not exist in GitHub, proceeding to upload.")
            else:
                logger.error(f"Error fetching file details from GitHub for {os.path.basename(file_path)}: {response.status_code}, {response.text}")
                continue

            if upload_needed:
                added_files.append(file_path)

        # 변경된 파일이 없으면 종료
        if not added_files:
            logger.info("No changes to commit to GitHub")
            return

        # 로컬 Git 리포지토리에 추가 및 커밋
        for file_path in added_files:
            run_git_command(f"git add {file_path}")
        
        commit_message = f"Update audit results for {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        run_git_command(f'git commit -m "{commit_message}"')

        # 원격으로 푸시
        run_git_command("git push origin main")
        logger.info("Successfully pushed changes to GitHub")

    except Exception as e:
        logger.error(f"Error during sync_files_to_github: {str(e)}")

# 테스트 코드
if __name__ == "__main__":
    # 테스트용 파일 경로
    test_files = [
        os.path.join(config.STATIC_PATH, 'results', '01010_도로부', 'audit_20180076.json'),
        os.path.join(config.STATIC_PATH, 'report', 'combined_report.csv')
    ]

    # 테스트 파일이 존재하는지 확인 후 업로드 시뮬레이션
    for file_path in test_files:
        if os.path.exists(file_path):
            logger.info(f"Test file found: {file_path}")
        else:
            logger.warning(f"Test file not found: {file_path}")

    # 비동기 실행
    try:
        asyncio.run(sync_files_to_github())
        logger.info("sync_files_to_github completed successfully.")
    except Exception as e:
        logger.error(f"Error during sync_files_to_github execution: {str(e)}")
        
        
# python git_operations.py