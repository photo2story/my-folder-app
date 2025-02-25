# git_operations.py

import git
import os
import base64
import requests
from dotenv import load_dotenv
import hashlib
import pandas as pd
import asyncio
import config

# .env 파일 로드
load_dotenv()

GITHUB_API_URL = "https://api.github.com"
GITHUB_FLASK_REPO = "photo2story/my-folder-app"  # 플라스크 앱 레포지토리
GITHUB_BRANCH = "main"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    GITHUB_TOKEN = os.getenv("PERSONAL_ACCESS_TOKEN")
    
print(f"Using GitHub token: {GITHUB_TOKEN[:10]}...")  # 토큰의 처음 10자만 출력

repo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
try:
    repo = git.Repo(repo_path)
except git.exc.InvalidGitRepositoryError:
    print(f'Invalid Git repository at path: {repo_path}')
    repo = None

# SHA 해시 계산 함수
def calculate_file_sha(file_path):
    sha_hash = hashlib.sha1()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha_hash.update(chunk)
    return sha_hash.hexdigest()

# 비동기 파일 이동 및 업로드 함수
async def move_files_to_images_folder(file_path):
    print(f"move_files_to_images_folder called for {file_path}")
    filename = os.path.basename(file_path)
    
    # 경로 결정: result_alpha 파일과 combined_close_prices.csv, data_ 로 시작하는 파일은 static/data, 나머지는 static/images
    if (filename.startswith("result_") or 
        filename.startswith("data_")):
        github_path = f"static/data/{filename}"
    else:
        github_path = f"static/images/{filename}"
        
            
    # GitHub 플라스크 레포에서 해당 파일의 정보 가져오기
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
        
        # 로컬 파일의 SHA 해시 계산
        local_sha = calculate_file_sha(file_path)
        
        # SHA 값이 동일하면 업로드를 생략
        if remote_sha == local_sha:
            print(f"{filename} is up-to-date in GitHub, skipping upload.")
            upload_needed = False
        else:
            await upload_file_to_github(file_path, github_path, remote_sha)
    elif response.status_code == 404:
        print(f"{filename} does not exist in GitHub, proceeding to upload.")
        await upload_file_to_github(file_path, github_path)
    else:
        print(f"Error fetching file details from GitHub: {response.status_code}, {response.text}")
        return
    
    # GitHub에 업로드되었거나 변경된 경우에만 로컬 Git 커밋 및 푸시 수행
    try:
        # 모든 변경 사항을 추가
        repo.git.add(file_path)  
        print(f'Successfully staged changes for {file_path}')
        
        # 항상 커밋을 수행
        repo.index.commit(f'Auto-commit moved files')
        print(f'Successfully committed changes including {file_path}')

        # 항상 푸시를 수행
        origin = repo.remote(name='origin')
        push_result = origin.push()
        
        if push_result[0].flags & push_result[0].ERROR:
            print(f"Error pushing changes to GitHub: {push_result[0].summary}")
        else:
            print(f'Changes pushed to GitHub, including {file_path}')
            print()  # 빈 줄 출력
    except Exception as e:
        print(f'Error during Git operation: {e}')

# GitHub에 파일 업로드 함수
async def upload_file_to_github(file_path, github_path, sha=None):
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

    url = f"https://api.github.com/repos/{GITHUB_FLASK_REPO}/contents/{github_path}"
    response = requests.put(url, json=data, headers=headers)

    if response.status_code in [200, 201]:
        print(f'Successfully uploaded {file_path} to GitHub')
    else:
        print(f'Error uploading {file_path} to GitHub: {response.status_code}, {response.text}')

# CSV 파일 URL
csv_path = config.STATIC_IMAGES_PATH
file_path = os.path.join(csv_path, f'result_20220127.csv')


# 테스트 코드
if __name__ == "__main__":
    # CSV 데이터를 가져와서 확인
    try:
        df = pd.read_csv(file_path)
        if df is not None and not df.empty:
            print("Successfully loaded CSV data:")
            print(df.head())
        else:
            print("Failed to fetch CSV data or data is empty.")
    except Exception as e:
        print(f"Error loading CSV data: {e}")
    
    # move_files_to_images_folder() 호출
    try:
        print("Attempting to move files to image folder and upload...")
        # 실행 중인 이벤트 루프 가져오기
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            print('Running in existing event loop')
            task = loop.create_task(move_files_to_images_folder())
            loop.run_until_complete(task)
        else:
            print('Creating a new event loop')
            asyncio.run(move_files_to_images_folder(file_path)) 

        print("move_files_to_images_folder completed successfully.")
    except Exception as e:
        print(f"Error during move_files_to_images_folder execution: {e}")


# python git_operations.py

