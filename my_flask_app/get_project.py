# my_flask_app/get_project.py : 프로젝트 정보 검색

import os
import re
import pandas as pd
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH, CONTRACT_STATUS_CSV, STATIC_DATA_PATH
from config_assets import DEPARTMENT_MAPPING
import logging
import sys

logger = logging.getLogger(__name__)

def get_project_info(project_id, department_code=None):
    """프로젝트 정보 조회 (PROJECT_LIST_CSV에서 original_folder만, 나머지는 contract_status.csv에서 가져옴)"""
    numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
    if not numeric_project_id:
        return None

    # contract_status.csv에서 데이터 로드 (기본 데이터 소스)
    contract_status_path = os.path.join(STATIC_DATA_PATH, 'data', CONTRACT_STATUS_CSV)
    if os.path.exists(contract_status_path):
        try:
            df_contract = pd.read_csv(contract_status_path, encoding='utf-8-sig')
            # 사업코드에서 숫자만 추출 (예: 'A20120095' -> '20120095', 숫자만 있는 경우 유지)
            df_contract['ProjectID'] = df_contract['사업코드'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
            contract_match = df_contract[df_contract['ProjectID'] == numeric_project_id]
            
            if len(contract_match) > 0:
                row = contract_match.iloc[0]
                dept_name = row['PM부서']
                dept_code = DEPARTMENT_MAPPING.get(dept_name, '99999')
                logger.debug(f"Found project in contract_status.csv: project_id={numeric_project_id}, dept_name={dept_name}, dept_code={dept_code}")
                
                # PROJECT_LIST_CSV에서 original_folder만 가져옴
                project_list_path = PROJECT_LIST_CSV
                original_folder = None
                if os.path.exists(project_list_path):
                    try:
                        df_project = pd.read_csv(project_list_path, dtype={'department_code': str, 'project_id': str})
                        project = df_project[df_project['project_id'] == numeric_project_id]
                        if len(project) > 0 and department_code:
                            department_code = str(department_code).zfill(5)
                            project = project[project['department_code'].str.zfill(5) == department_code]
                        if len(project) > 0:
                            folder_row = project.iloc[0]
                            original_folder = os.path.join(NETWORK_BASE_PATH, str(folder_row['original_folder']))
                            logger.debug(f"Found original_folder in PROJECT_LIST_CSV: {original_folder}")
                    except Exception as e:
                        logger.error(f"Error loading PROJECT_LIST_CSV: {str(e)}")
                else:
                    logger.error(f"PROJECT_LIST_CSV not found: {project_list_path}")

                # original_folder가 없으면 기본 경로 생성
                if not original_folder or not os.path.exists(original_folder):
                    original_folder = os.path.join(NETWORK_BASE_PATH, f"{dept_code}_{dept_name}", f"{numeric_project_id}_{row['사업명']}")
                    logger.debug(f"Generated default project folder: {original_folder}")

                # 경로 존재 여부 확인
                if os.path.exists(original_folder):
                    return {
                        'project_id': numeric_project_id,
                        'department_code': dept_code,
                        'department_name': dept_name,
                        'project_name': str(row['사업명']),
                        'status': str(row['진행상태']) if pd.notna(row['진행상태']) else 'Unknown',
                        'contractor': str(row['주관사']) if pd.notna(row['주관사']) else 'Unknown',
                        'original_folder': original_folder
                    }
                else:
                    logger.error(f"Project folder does not exist: {original_folder}")
                    return None
            else:
                logger.warning(f"Project ID {numeric_project_id} not found in contract_status.csv, checking audit_targets_new.csv")
        except Exception as e:
            logger.error(f"Error loading contract_status.csv: {str(e)}")
    else:
        logger.error(f"contract_status.csv not found: {contract_status_path}")

    # contract_status.csv에서도 찾지 못한 경우, audit_targets_new.csv 참조 (백업)
    audit_targets_path = os.path.join(STATIC_DATA_PATH, 'data', 'audit_targets_new.csv')
    if os.path.exists(audit_targets_path):
        try:
            df_targets = pd.read_csv(audit_targets_path, encoding='utf-8-sig')
            # Depart_ProjectID에서 사업코드 추출
            df_targets['ProjectID'] = df_targets['Depart_ProjectID'].apply(lambda x: re.sub(r'[^0-9]', '', str(x).split('_C')[-1]) if '_C' in str(x) else re.sub(r'[^0-9]', '', str(x)))
            target_match = df_targets[df_targets['ProjectID'] == numeric_project_id]
            
            if len(target_match) > 0:
                row = target_match.iloc[0]
                dept_code = re.sub(r'[^0-9]', '', str(row['Depart_ProjectID']).split('_')[0]).zfill(5)
                dept_name = row.get('Depart', 'Unknown')
                logger.debug(f"Found project in audit_targets_new.csv: project_id={numeric_project_id}, dept_code={dept_code}, dept_name={dept_name}")
                
                # PROJECT_LIST_CSV에서 original_folder만 가져옴
                original_folder = None
                if os.path.exists(project_list_path):
                    try:
                        df_project = pd.read_csv(project_list_path, dtype={'department_code': str, 'project_id': str})
                        project = df_project[df_project['project_id'] == numeric_project_id]
                        if len(project) > 0 and department_code:
                            department_code = str(department_code).zfill(5)
                            project = project[project['department_code'].str.zfill(5) == department_code]
                        if len(project) > 0:
                            folder_row = project.iloc[0]
                            original_folder = os.path.join(NETWORK_BASE_PATH, str(folder_row['original_folder']))
                            logger.debug(f"Found original_folder in PROJECT_LIST_CSV: {original_folder}")
                    except Exception as e:
                        logger.error(f"Error loading PROJECT_LIST_CSV: {str(e)}")
                else:
                    logger.error(f"PROJECT_LIST_CSV not found: {project_list_path}")

                # original_folder가 없으면 기본 경로 생성
                if not original_folder or not os.path.exists(original_folder):
                    original_folder = os.path.join(NETWORK_BASE_PATH, f"{dept_code}_{dept_name}", f"{numeric_project_id}_{row.get('ProjectName', f'Project {numeric_project_id}')}")
                    logger.debug(f"Generated default project folder: {original_folder}")

                # 경로 존재 여부 확인
                if os.path.exists(original_folder):
                    return {
                        'project_id': numeric_project_id,
                        'department_code': dept_code,
                        'department_name': dept_name,
                        'project_name': row.get('ProjectName', f'Project {numeric_project_id}'),
                        'status': row.get('Status', 'Unknown'),
                        'contractor': row.get('Contractor', 'Unknown'),
                        'original_folder': original_folder
                    }
                else:
                    logger.error(f"Project folder does not exist: {original_folder}")
                    return None
            else:
                logger.warning(f"Project ID {numeric_project_id} not found in audit_targets_new.csv")
        except Exception as e:
            logger.error(f"Error loading audit_targets_new.csv: {str(e)}")
    else:
        logger.error(f"audit_targets_new.csv not found: {audit_targets_path}")

    # 기본값 반환 (정보가 없는 경우)
    default_path = os.path.join(NETWORK_BASE_PATH, f"{department_code or '01010'}_Unknown", f"{numeric_project_id}_Project {numeric_project_id}")
    logger.warning(f"Using default project info for {numeric_project_id}: {default_path}")
    return {
        'project_id': numeric_project_id,
        'department_code': (department_code or '01010').zfill(5),
        'department_name': 'Unknown',
        'project_name': f'Project {numeric_project_id}',
        'status': 'Unknown',
        'contractor': 'Unknown',
        'original_folder': default_path
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # 커맨드 라인 인자 처리
    if len(sys.argv) > 1:
        project_id = sys.argv[1]
    else:
        project_id = "20180076"  # 기본값
        print(f"프로젝트 ID가 입력되지 않아 기본값 {project_id}를 사용합니다.")
        print("사용법: python get_project.py [프로젝트ID]")
        print("예시: python get_project.py 20180076")
    
    print(f"\n프로젝트 ID {project_id} 검색 결과:")
    print("-" * 50)
    
    # 프로젝트 정보 조회
    result = get_project_info(project_id)
    if result:
        for key, value in result.items():
            print(f"{key}: {value}")
    else:
        print(f"프로젝트 ID {project_id}에 해당하는 정보를 찾을 수 없습니다.")
    
    print("-" * 50)

# python get_project.py 20180076