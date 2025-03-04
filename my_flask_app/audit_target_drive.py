# my_flask_app/audit_target_drive.py
import pandas as pd
import os
import re
import logging
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH

# 로깅 설정 (디버깅 로그 레벨로 변경)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def find_project_folder(project_id):
    """
    project_id로 프로젝트 폴더를 검색하여 경로 반환, 없으면 'No folder' 반환
    project_list.csv에서 project_id를 검색하고 original_folder 값을 그대로 사용하며, 네트워크 드라이브 접두사 제거
    project_list.csv가 없거나 매핑되지 않으면 'No folder' 반환
    """
    # project_id에서 영문 접두사/접미사 제거 (숫자만 추출, 8자리 제한 없음)
    numeric_project_id = re.sub(r'^[A-Za-z]|[A-Za-z]$', '', str(project_id))
    numeric_project_id = re.sub(r'[^0-9]', '', numeric_project_id)  # 숫자만 유지

    if not numeric_project_id:
        logger.warning(f"No numeric project_id extracted from {project_id}")
        return "No folder"

    # 프로젝트 리스트에서 경로 확인 (audit_targets_new.csv 제외, 없으면 'No folder')
    logger.debug(f"Searching project folder for project_id: {project_id} (numeric: {numeric_project_id}) in project_list.csv")
    try:
        if os.path.exists(PROJECT_LIST_CSV):
            df_projects = pd.read_csv(PROJECT_LIST_CSV, encoding='utf-8')  # BOM 없이 순수 UTF-8로 읽기
            # project_list.csv의 project_id에서 숫자만 추출
            df_projects['numeric_project_id'] = df_projects['project_id'].apply(lambda x: re.sub(r'^[A-Za-z]|[A-Za-z]$', '', str(x)))
            df_projects['numeric_project_id'] = df_projects['numeric_project_id'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
            project_row = df_projects[df_projects['numeric_project_id'] == numeric_project_id]
            
            if not project_row.empty:
                original_folder = project_row['original_folder'].iloc[0]
                # 네트워크 드라이브 접두사 제거 (예: Z:\, Y:\, X:\) 및 전체 경로 생성
                folder_without_drive = re.sub(r'^[A-Z]:\\', '', original_folder)
                full_path = os.path.join(NETWORK_BASE_PATH, folder_without_drive)
                
                if os.path.exists(full_path):
                    logger.debug(f"Found project folder for ID {project_id} (numeric: {numeric_project_id}): {full_path}")
                    return folder_without_drive  # 드라이브 접두사 제거된 경로 반환
                else:
                    logger.warning(f"Project folder not found for ID {project_id} (numeric: {numeric_project_id}) in original path: {full_path}")
                    return "No folder"
            else:
                logger.warning(f"No project found in project_list.csv for numeric ID {numeric_project_id} (original: {project_id})")
                return "No folder"
        else:
            logger.warning(f"Project list file not found: {PROJECT_LIST_CSV}, returning 'No folder'")
            return "No folder"
    except Exception as e:
        logger.error(f"Error reading project_list.csv: {str(e)}")
        return "No folder"

    logger.warning(f"Project folder not found for ID {project_id} (numeric: {numeric_project_id}) after search")
    return "No folder"