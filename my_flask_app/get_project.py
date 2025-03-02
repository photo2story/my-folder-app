# my_flask_app/get_project.py : 프로젝트 정보 검색

import pandas as pd
import re
from config import CONTRACT_STATUS_CSV
from config_assets import DEPARTMENT_MAPPING
import logging

logger = logging.getLogger(__name__)

def get_project_info(project_id, department_code):
    """
    project_id와 department_code를 기준으로 contract_status.csv에서 프로젝트 정보를 검색.
    
    Args:
        project_id (str): 프로젝트 ID (예: 'C20240178', 영문 접두사 포함 가능)
        department_code (str): 부서 코드 또는 이름 (예: '06010' 또는 '환경사업부')
    
    Returns:
        dict: 프로젝트 정보, 또는 None (찾지 못할 경우)
    """
    try:
        # contract_status.csv를 UTF-8로 명시적으로 로드
        df = pd.read_csv(CONTRACT_STATUS_CSV, dtype={'사업코드': str, 'PM부서': str, '진행상태': str, '주관사': str}, encoding='utf-8')
        
        # 디버깅: 입력된 project_id와 department_code 출력
        logger.debug(f"Searching for project_id: {project_id}, department_code: {department_code}")
        
        # project_id에서 영문 접두사만 제거 (숫자와 접미사 유지)
        clean_project_id = re.sub(r'^[A-Za-z]', '', str(project_id))
        
        # department_code를 부서 이름 또는 코드로 처리
        dept_name = department_code  # 기본적으로 department_code를 부서 이름으로 간주
        dept_code = None
        
        # department_code가 부서 이름인지 확인 (예: '환경사업부')
        if dept_name in DEPARTMENT_MAPPING:
            dept_code = DEPARTMENT_MAPPING[dept_name]
            logger.debug(f"Department name {dept_name} maps to department code: {dept_code}")
        else:
            # department_code가 부서 코드인지 확인 (예: '06010')
            dept_code = str(department_code).zfill(5)
            # 부서 코드를 부서 이름으로 역매핑
            for name, code in DEPARTMENT_MAPPING.items():
                if str(code).zfill(5) == dept_code:
                    dept_name = name
                    break
            if not dept_name:
                logger.error(f"Department code {department_code} not found in DEPARTMENT_MAPPING")
                return None
        
        # 디버깅: 매핑된 부서 이름과 코드 출력 (한글 확인)
        logger.debug(f"Department code {department_code} maps to department name: {dept_name}, department code: {dept_code}")
        
        # PM부서 열의 데이터 타입과 인코딩 확인 (한글 문제 디버깅)
        logger.debug(f"PM부서 column sample: {df['PM부서'].head().tolist()}")
        
        # 사업코드에서 영문 접두사 제거 (숫자와 접미사 유지)
        df['사업코드_clean'] = df['사업코드'].apply(lambda x: re.sub(r'^[A-Za-z]', '', str(x)))
        
        # project_id (영문 접두사 제거)와 PM부서 이름으로 필터링 (Boolean Series 문제 해결)
        # str로 명시적 변환하여 한글 비교 문제 방지
        project = df.loc[
            (df['사업코드_clean'].astype(str) == str(clean_project_id)) & 
            (df['PM부서'].astype(str) == str(dept_name))
        ].reset_index(drop=True)  # 인덱스 재설정으로 문제 해결
        
        # 디버깅: 필터링된 프로젝트 출력 (한글 확인)
        logger.debug(f"Filtered projects: {project['사업코드'].tolist() if not project.empty else 'None'}")
        logger.debug(f"Filtered PM부서: {project['PM부서'].tolist() if not project.empty else 'None'}")
        
        if project.empty:
            logger.error(f"Project ID {project_id} not found for department {dept_name} in contract_status.csv")
            return None
        
        # 접미사 없는 프로젝트만 필터링 (사업코드_clean이 8자리 숫자만 포함, 접미사 허용 제거)
        final_project = None
        for _, row in project.iterrows():
            project_code_clean = row['사업코드_clean']
            # 접미사 없는 경우와 접미사(A, B 등) 있는 경우 모두 허용 (8자리 숫자 또는 8자리 숫자+알파벳)
            if re.match(r'^[0-9]{8}([A-Za-z])?$', project_code_clean):  # 8자리 숫자 또는 8자리 숫자+1자 알파벳
                final_project = row
                break
        
        if not final_project:
            logger.error(f"No match found for Project ID {project_id} for department {dept_name}")
            return None
        
        row = final_project
        dept_code = DEPARTMENT_MAPPING.get(row['PM부서'], '99999')
        dept_name = row['PM부서']
        status = row['진행상태']
        contractor = row['주관사']
        project_name = row['사업명']
        
        # 디버깅: 찾은 프로젝트와 부서 정보 출력 (한글 확인)
        logger.debug(f"Found Project ID: {row['사업코드']}, Department Code: {dept_code}, Department Name: {dept_name}")
        
        result = {
            'Depart_ProjectID': row['사업코드'],
            'Depart': dept_name,
            'Status': status,
            'Contractor': contractor,
            'ProjectName': project_name,
            'project_id': row['사업코드'],  # 영문 접두사 포함 (예: C20240178)
            'department_code': dept_code,
            'department_name': dept_name,
            'original_folder': f"{dept_code}{re.sub(r'[^0-9]', '', project_code_clean)}"  # 숫자 부분만 경로에 사용
        }
        
        logger.debug(f"Found project info - ID: {result['project_id']}, Dept: {result['department_code']}, Dept Name: {result['department_name']}, Name: {project_name}, Contractor: {contractor}")
        return result
    
    except Exception as e:
        logger.error(f"Error in get_project_info for {project_id}, {department_code}: {str(e)}")
        logger.debug(f"Exception details - project_id: {project_id}, department_code: {department_code}, df shape: {df.shape if 'df' in locals() else 'None'}, df sample: {df.head().to_string() if 'df' in locals() else 'None'}")
        return None

if __name__ == "__main__":
    # 테스트용: PM부서가 "환경사업부"인 모든 데이터 출력, 그리고 project_id 필터링
    logging.basicConfig(level=logging.DEBUG)
    
    # contract_status.csv를 UTF-8로 로드
    df = pd.read_csv(CONTRACT_STATUS_CSV, dtype={'사업코드': str, 'PM부서': str, '진행상태': str, '주관사': str}, encoding='utf-8')
    
    # 사업코드에서 영문 접두사 제거 (숫자와 접미사 유지)
    df['사업코드_clean'] = df['사업코드'].apply(lambda x: re.sub(r'^[A-Za-z]', '', str(x)))
    
    # 1단계: PM부서가 "환경사업부"인 모든 행 필터링
    env_projects = df[df['PM부서'] == '환경사업부'].reset_index(drop=True)
    
    # 디버깅: 필터링된 데이터 출력
    logger.debug(f"Projects with PM부서 '환경사업부': {env_projects.shape[0]} rows found")
    logger.debug(f"PM부서 '환경사업부' 데이터:\n{env_projects}")
    
    # 콘솔에 출력
    if not env_projects.empty:
        print("\nProjects with PM부서 '환경사업부':")
        print(env_projects.to_string(index=False))
    else:
        print("No projects found with PM부서 '환경사업부'")
    
    # 2단계: PM부서가 "환경사업부"이고, project_id와 일치하는 프로젝트 필터링
    # project_id에서 영문 접두사만 제거 (숫자와 접미사 유지)
    project_id = "20240178"  # 예시로 영문 접두사 포함 project_id 사용
    clean_project_id = re.sub(r'^[A-Za-z]', '', str(project_id))
    
    # PM부서가 "환경사업부"이고, 사업코드_clean이 clean_project_id와 정확히 일치하는 행 필터링
    matched_projects = env_projects.loc[
        env_projects['사업코드_clean'].astype(str) == str(clean_project_id)
    ].reset_index(drop=True)
    
    # 디버깅: 필터링된 데이터 출력
    logger.debug(f"Projects with PM부서 '환경사업부' and project_id '{project_id}': {matched_projects.shape[0]} rows found")
    logger.debug(f"Matched projects data:\n{matched_projects}")
    
    # 콘솔에 출력
    if not matched_projects.empty:
        print(f"\nProjects with PM부서 '환경사업부' and project_id '{project_id}':")
        print(matched_projects.to_string(index=False))
    else:
        print(f"No projects found with PM부서 '환경사업부' and project_id '{project_id}'")
    
    # 기존 테스트 코드 유지 (선택적)
    department_code = "환경사업부"
    result = get_project_info(project_id, department_code)
    if result:
        print(f"\nFound project: {result}")
    else:
        print(f"No project found for project_id {project_id} and department_code {department_code}")
# python get_project.py 
# python get_project.py --verbose