# my_flask_app/get_project.py : 프로젝트 정보 검색

import os
import re
import pandas as pd
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH, CONTRACT_STATUS_CSV
from config_assets import DEPARTMENT_MAPPING
import logging
import sys

logger = logging.getLogger(__name__)

def get_project_info(project_id, department_code=None):
    """프로젝트 정보 조회 (간소화 및 유연화, 디버깅 추가)"""
    numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
    df = pd.read_csv(PROJECT_LIST_CSV, dtype={'department_code': str, 'project_id': str})
    
    # department_code가 None이면 PROJECT_LIST_CSV에서 모든 부서에서 검색
    if department_code:
        department_code = str(department_code).zfill(5)
        project = df[(df['project_id'] == numeric_project_id) & (df['department_code'].str.zfill(5) == department_code)]
    else:
        project = df[df['project_id'] == numeric_project_id]

    if len(project) == 0:
        # PROJECT_LIST_CSV에서 찾지 못한 경우, contract_status.csv 참조
        contract_df = pd.read_csv(CONTRACT_STATUS_CSV, encoding='utf-8')
        contract_df['ProjectID'] = contract_df['사업코드'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
        contract_match = contract_df[contract_df['ProjectID'] == numeric_project_id]
        
        if len(contract_match) > 0:
            row = contract_match.iloc[0]
            dept_name = row['PM부서']
            dept_code = DEPARTMENT_MAPPING.get(dept_name, '99999')
            logger.debug(f"Found project in contract_status.csv: project_id={numeric_project_id}, dept_name={dept_name}, dept_code={dept_code}")
            
            # PROJECT_LIST_CSV에서 부서와 project_id로 경로 확인
            dept_project = df[(df['project_id'] == numeric_project_id) & (df['department_code'].str.zfill(5) == dept_code)]
            if len(dept_project) > 0:
                folder_row = dept_project.iloc[0]
                full_path = os.path.join(NETWORK_BASE_PATH, str(folder_row['original_folder']))
                logger.debug(f"Found project folder in PROJECT_LIST_CSV: {full_path}")
            else:
                # 기본 경로 생성 (부서별 폴더 구조)
                full_path = os.path.join(NETWORK_BASE_PATH, f"{dept_code}_{dept_name}", str(numeric_project_id))
                logger.debug(f"Generated default project folder: {full_path}")
            
            # 경로 존재 여부 확인
            if os.path.exists(full_path):
                return {
                    'project_id': numeric_project_id,
                    'department_code': dept_code,
                    'department_name': dept_name,
                    'project_name': str(row['사업명']),
                    'original_folder': full_path
                }
            else:
                logger.error(f"Project folder does not exist: {full_path}")
                return None
        else:
            logger.error(f"Project ID {numeric_project_id} not found in contract_status.csv or project list")
            return None

    row = project.iloc[0]
    full_path = os.path.join(NETWORK_BASE_PATH, str(row['original_folder']))
    logger.debug(f"Found project in PROJECT_LIST_CSV: project_id={numeric_project_id}, department_code={row['department_code']}, folder={full_path}")
    
    # 경로 존재 여부 확인
    if os.path.exists(full_path):
        return {
            'project_id': str(row['project_id']),
            'department_code': str(row['department_code']).zfill(5),
            'department_name': str(row['department_name']),
            'project_name': str(row['project_name']),
            'original_folder': full_path
        }
    else:
        logger.error(f"Project folder does not exist: {full_path}")
        return None

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