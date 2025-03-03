import os
import json
import re
import shutil
from pathlib import Path
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 설정
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'results')
NEW_FORMAT = "dept_first"  # "dept_first" 또는 "proj_first"

def extract_info_from_json(filepath):
    """JSON 파일에서 project_id와 department 정보 추출"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            project_id = data.get('project_id', '')
            department = data.get('department', '')
            
            # department에서 부서 코드 추출 (예: "06010_환경사업부" -> "06010")
            if department:
                dept_match = re.match(r'^(\d{5}).*', department)
                if dept_match:
                    department = dept_match.group(1)
                else:
                    department = '99999'  # 기본값
            else:
                department = '99999'
            
            return str(project_id), department
    except Exception as e:
        logger.error(f"Error reading {filepath}: {str(e)}")
        return None, None

def rename_files():
    """results 폴더의 audit_*.json 파일 이름을 변경"""
    if not os.path.exists(RESULTS_DIR):
        logger.error(f"Results directory not found: {RESULTS_DIR}")
        return

    # 백업 폴더 생성
    backup_dir = os.path.join(RESULTS_DIR, 'backup')
    os.makedirs(backup_dir, exist_ok=True)

    # 감사 파일 목록 가져오기
    audit_files = [f for f in os.listdir(RESULTS_DIR) if f.startswith('audit_') and f.endswith('.json')]
    
    if not audit_files:
        logger.warning(f"No audit files found in {RESULTS_DIR}")
        return

    logger.info(f"Found {len(audit_files)} audit files to process")
    renamed_count = 0
    error_count = 0

    for old_filename in audit_files:
        old_filepath = os.path.join(RESULTS_DIR, old_filename)
        
        try:
            # JSON 파일에서 정보 추출
            project_id, dept_code = extract_info_from_json(old_filepath)
            
            if not project_id or not dept_code:
                logger.warning(f"Could not extract project_id or department from {old_filename}")
                continue

            # 새 파일 이름 생성
            if NEW_FORMAT == "dept_first":
                new_filename = f"audit_{dept_code}_{project_id}.json"
            else:  # proj_first
                new_filename = f"audit_{project_id}_{dept_code}.json"

            new_filepath = os.path.join(RESULTS_DIR, new_filename)

            # 파일이 이미 올바른 형식이면 건너뛰기
            if old_filename == new_filename:
                logger.debug(f"File {old_filename} already in correct format")
                continue

            # 기존 파일 백업
            backup_path = os.path.join(backup_dir, old_filename)
            shutil.copy2(old_filepath, backup_path)

            # 파일 이름 변경
            os.rename(old_filepath, new_filepath)
            renamed_count += 1
            logger.info(f"Renamed {old_filename} to {new_filename}")

        except Exception as e:
            error_count += 1
            logger.error(f"Error processing {old_filename}: {str(e)}")
            continue

    logger.info(f"Renaming completed: {renamed_count} files renamed, {error_count} errors")
    logger.info(f"Backup files saved in: {backup_dir}")

if __name__ == "__main__":
    logger.info(f"Starting file renaming in {RESULTS_DIR}")
    logger.info(f"Using format: {NEW_FORMAT} (dept_first: audit_dept_proj.json, proj_first: audit_proj_dept.json)")
    rename_files()
    logger.info("Process completed")