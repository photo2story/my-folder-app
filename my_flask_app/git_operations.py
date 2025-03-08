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

# GitHub에 파일 업로드 함수
async def upload_file_to_github(file_path, github_path, sha=None):
    try:
        with open(file_path, 'rb') as file:
            content = file.read()

        base64_content = base64.b64encode(content).decode('utf-8')

        data = {
            "message": f"Add or update {os.path.basename(file_path)}",
            "content": base64_content,
            "branch": GITHUB_BRANCH
        }
        
        if sha:
            data["sha"] = sha

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        url = f"{GITHUB_API_URL}/repos/{GITHUB_FLASK_REPO}/contents/{github_path}"
        response = requests.put(url, json=data, headers=headers)

        if response.status_code in [200, 201]:
            logger.info(f'Successfully uploaded {file_path} to GitHub at {github_path}')
        else:
            logger.error(f'Error uploading {file_path} to GitHub: {response.status_code}, {response.text}')
    except Exception as e:
        logger.error(f'Error uploading {file_path} to GitHub: {str(e)}')

# 비동기 파일 업로드 함수
async def sync_files_to_github(file_path=None):
    """특정 파일 또는 results 디렉토리의 모든 JSON 및 CSV 파일을 GitHub에 업로드"""
    try:
        if file_path and os.path.exists(file_path):
            # 특정 파일 업로드
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
                return

            if upload_needed:
                await upload_file_to_github(file_path, github_path, sha=remote_sha if response.status_code == 200 else None)
        else:
            # results 디렉토리 및 report 디렉토리 전체 동기화
            results_dir = os.path.join(config.STATIC_PATH, 'results')
            if not os.path.exists(results_dir):
                logger.warning(f"Results directory does not exist: {results_dir}")
                return

            for root, dirs, files in os.walk(results_dir):
                for filename in files:
                    if filename.endswith('.json') or filename.endswith('.csv'):
                        file_path = os.path.join(root, filename)
                        relative_path = os.path.relpath(root, config.STATIC_PATH).replace(os.sep, '/')
                        github_path = f"static/{relative_path}/{filename}"

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
                                logger.info(f"{filename} is up-to-date in GitHub, skipping upload.")
                                upload_needed = False
                        elif response.status_code == 404:
                            logger.info(f"{filename} does not exist in GitHub, proceeding to upload.")
                        else:
                            logger.error(f"Error fetching file details from GitHub for {filename}: {response.status_code}, {response.text}")
                            continue

                        if upload_needed:
                            await upload_file_to_github(file_path, github_path, sha=remote_sha if response.status_code == 200 else None)

            # report 디렉토리의 combined_report.csv 처리
            report_dir = os.path.join(config.STATIC_PATH, 'report')
            if os.path.exists(report_dir):
                for filename in os.listdir(report_dir):
                    if filename.startswith("combined_report") and filename.endswith('.csv'):
                        file_path = os.path.join(report_dir, filename)
                        github_path = f"static/report/{filename}"
                        response = requests.get(f"{GITHUB_API_URL}/repos/{GITHUB_FLASK_REPO}/contents/{github_path}", headers=headers, params={"ref": GITHUB_BRANCH})
                        
                        upload_needed = True
                        if response.status_code == 200:
                            file_data = response.json()
                            remote_sha = file_data['sha']
                            local_sha = calculate_file_sha(file_path)
                            if remote_sha == local_sha:
                                logger.info(f"{filename} is up-to-date in GitHub, skipping upload.")
                                upload_needed = False
                        elif response.status_code == 404:
                            logger.info(f"{filename} does not exist in GitHub, proceeding to upload.")
                        else:
                            logger.error(f"Error fetching file details from GitHub for {filename}: {response.status_code}, {response.text}")
                            continue

                        if upload_needed:
                            await upload_file_to_github(file_path, github_path, sha=remote_sha if response.status_code == 200 else None)

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