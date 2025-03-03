# my_flask_app/audit_target_generator.py
import pandas as pd
import argparse
import os
import re
from config_assets import AUDIT_FILTERS, DEPARTMENT_MAPPING
import logging
from config import STATIC_DATA_PATH, PROJECT_LIST_CSV

# 로깅 설정 (디버깅 로그 레벨로 변경)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def find_project_folder(project_id):
    """
    project_id로 프로젝트 폴더를 검색하여 경로 반환, 없으면 'No folder' 반환
    project_list.csv에서 project_id를 검색하고 original_folder 값을 사용하며, Z: 드라이브를 기본으로 설정
    """
    # project_id에서 접두사(C, R 등) 제거하고 숫자만 추출
    numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
    
    # Z: 드라이브를 기본 네트워크 드라이브로 설정
    NETWORK_BASE_PATH = "Z:\\"
    
    # 프로젝트 리스트에서 경로 확인
    try:
        df_projects = pd.read_csv(PROJECT_LIST_CSV, encoding='utf-8-sig')
        df_projects['project_id'] = df_projects['project_id'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
        project_row = df_projects[df_projects['project_id'] == numeric_project_id]
        
        if not project_row.empty:
            original_folder = project_row['original_folder'].iloc[0]
            # original_folder에서 특수 문자 및 공백 정리 (유연하게 처리)
            clean_path = original_folder.replace('ㅣ', '_').replace(' ', '_').replace('(', '').replace(')', '').replace(',', '_').replace('-', '_')
            # 경로에서 불필요한 접두사 제거 (부서 코드 등)
            clean_path = re.sub(r'^99999_준공|07010_상하수도|01010_도로부|.*_.*\\', '', clean_path)
            
            full_path = os.path.join(NETWORK_BASE_PATH, clean_path)
            
            if os.path.exists(full_path):
                logger.debug(f"Found project folder for ID {project_id} (numeric: {numeric_project_id}): {full_path}")
                return full_path
            else:
                logger.warning(f"Project folder not found for ID {project_id} (numeric: {numeric_project_id}) in cleaned path: {full_path}")
                return os.path.join(NETWORK_BASE_PATH, original_folder)  # 원본 경로 반환
        else:
            logger.warning(f"No project found in project_list.csv for numeric ID {numeric_project_id} (original: {project_id})")
    except FileNotFoundError:
        logger.error(f"Project list file not found: {PROJECT_LIST_CSV}")
    except Exception as e:
        logger.error(f"Error reading project_list.csv: {str(e)}")

    # Z: 드라이브 연결 상태 확인
    if not os.path.exists(NETWORK_BASE_PATH):
        logger.error(f"Network drive Z: not accessible: {NETWORK_BASE_PATH}")
        return "No folder"

    # 기본 경로 검색 (숫자 기반)
    base_paths = [
        os.path.join(NETWORK_BASE_PATH, numeric_project_id),  # 기본 project_id
        os.path.join(NETWORK_BASE_PATH, f"Y{numeric_project_id}"),  # Y 접두사 포함
        os.path.join(NETWORK_BASE_PATH, f"{numeric_project_id}_"),  # project_id_ 접미사
    ]

    for path in base_paths:
        if os.path.exists(path):
            logger.debug(f"Found project folder via default search for ID {project_id} (numeric: {numeric_project_id}): {path}")
            return path
    
    logger.warning(f"Project folder not found for ID {project_id} (numeric: {numeric_project_id}) after extensive search on Z:")
    return "No folder"

def select_audit_targets(filters=None, output_csv=None):
    """
    필터 조건으로 새로운 감사 대상을 선정하고 CSV로 저장하며, DataFrame 반환
    Args:
        filters (dict): 필터 조건 (status, year)
        output_csv (str): 출력 CSV 파일 경로 (기본값: static/data/audit_targets_new.csv)
    Returns:
        tuple: (audit_targets_df, project_ids, search_folders) DataFrame와 리스트
    """
    # CLI 인수 또는 config에서 필터 읽기
    if filters is None:
        filters = AUDIT_FILTERS
        # status 필터를 config에서 지정된 값으로 설정 (기본값: '준공', '진행')
        if not filters.get('status'):
            filters['status'] = ['준공', '진행']
    
    logger.info("Using audit filters from config_assets.py. Modify AUDIT_FILTERS in config_assets.py to adjust filtering conditions:")
    logger.info(f"- Status: {filters.get('status', 'Not specified')} (준공: 성과품 완벽히 포함해야 함, 100% 문서 필요 / 진행: 성과품 미완성 가능, 부분 문서 허용)")
    logger.info(f"- Year: {filters.get('year', 'Not specified')} (2024년 준공 프로젝트만 감사)")

    # 출력 CSV 경로 설정 (기본값 사용)
    if output_csv is None:
        output_csv = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')

    # CSV 파일 읽기 (UTF-8 with BOM 인코딩)
    input_file = os.path.join(STATIC_DATA_PATH, 'contract_status.csv')
    try:
        df_contract = pd.read_csv(input_file, encoding='utf-8-sig')
        # 사업코드에서 숫자만 추출하여 새로운 컬럼 생성
        df_contract['numeric_project_id'] = df_contract['사업코드'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
    except FileNotFoundError:
        logger.error(f"파일을 찾을 수 없습니다: {input_file}")
        raise
    except Exception as e:
        logger.error(f"CSV 파일 읽기 오류: {str(e)}")
        raise

    # project_id에서 접두사(C, R 등) 유지 (필터링에 영향 주지 않음)
    df_contract['project_id'] = df_contract['사업코드'].apply(lambda x: str(x).strip())

    # 필터링 조건 적용
    mask = True
    if 'status' in filters and filters['status']:
        mask &= df_contract['진행상태'].isin(filters['status'])
        # 상태별 로깅 추가
        for status in filters['status']:
            if status == '준공':
                logger.info(f"Filtering for '준공' status: Projects must have complete deliverables (100% document requirement)")
            elif status == '진행':
                logger.info(f"Filtering for '진행' status: Projects may have incomplete deliverables (partial document allowance)")

    if 'year' in filters and filters['year']:
        mask &= pd.to_datetime(df_contract['변경준공일(차수)'], errors='coerce').dt.year.isin(filters['year'])
        logger.info(f"Filtering for year {filters['year']}: Only 2024 completed projects will be audited")

    # 필터링된 데이터 (contract_status.csv에서 모든 필드 가져오기)
    filtered_df = df_contract[mask][['사업코드', 'PM부서', '사업명', '진행상태', '주관사', 'numeric_project_id']]
    filtered_df.columns = ['ProjectID', 'Depart', 'ProjectName', 'Status', 'Contractor', 'numeric_project_id']

    # 주관사(Contractor) 필드 업데이트 (contract_status.csv에서 가져옴)
    def get_contractor(row):
        # 현재 행의 numeric_project_id와 일치하는 모든 계약 데이터 찾기
        matches = df_contract[df_contract['numeric_project_id'] == row['numeric_project_id']]
        if not matches.empty:
            # 주관사 값이 있는 경우 반환
            contractors = matches['주관사'].dropna()
            if not contractors.empty:
                return contractors.iloc[0]
        return 'Unknown'

    filtered_df['Contractor'] = filtered_df.apply(get_contractor, axis=1)

    # ProjectID를 숫자만 남기도록 수정
    filtered_df['ProjectID'] = filtered_df['numeric_project_id']

    # Depart_ProjectID 생성 (부서코드_ProjectID)
    def get_department_code(depart_name):
        # config_assets의 DEPARTMENT_MAPPING에서 부서 코드 가져오기
        return DEPARTMENT_MAPPING.get(depart_name, '99999')

    filtered_df['Depart_ProjectID'] = filtered_df.apply(
        lambda row: f"{get_department_code(row['Depart'])}_{row['ProjectID']}", 
        axis=1
    )

    # 프로젝트 폴더 미리 확인 및 search_folder 추가 (필터링에 영향 없음)
    filtered_df['search_folder'] = filtered_df['ProjectID'].apply(find_project_folder)

    # numeric_project_id 컬럼 제거
    filtered_df = filtered_df.drop('numeric_project_id', axis=1)

    # 결과 저장 (project_id와 search_folder를 핵심으로, 나머지는 contract_status.csv에서 가져옴)
    audit_targets = filtered_df[['Depart_ProjectID', 'ProjectID', 'Depart', 'Status', 'ProjectName', 'Contractor', 'search_folder']]
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)  # 상위 디렉토리 생성
    audit_targets.to_csv(output_csv, index=False, encoding='utf-8-sig')

    logger.info(f"새로운 감사 대상이 {output_csv}에 저장되었습니다. 총 프로젝트 수: {len(audit_targets)}")
    logger.info(f"Audit targets filtered by status: {filters['status']} with document requirements applied (준공: 100% 문서 필요, 진행: 부분 문서 허용)")

    # DataFrame 반환 (project_id와 search_folder 사용)
    numeric_project_ids = filtered_df['ProjectID'].tolist()
    search_folders = filtered_df['search_folder'].tolist()

    return audit_targets, numeric_project_ids, search_folders

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="새로운 감사 대상 프로젝트 필터링")
    parser.add_argument('--year', type=int, nargs='+', default=AUDIT_FILTERS['year'], help="필터링할 준공 연도 (여러 개 가능)")
    parser.add_argument('--status', type=str, nargs='+', default=AUDIT_FILTERS['status'], help="필터링할 진행 상태 (여러 개 가능: '준공', '진행', '중지', '탈락')")
    parser.add_argument('--output-csv', type=str, default=os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv'), help="출력 CSV 파일 경로")
    parser.add_argument('--verbose', action='store_true', help="상세 로그 출력")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    filters = {
        'year': args.year,
        'status': args.status
    }
    audit_targets_df, project_ids, search_folders = select_audit_targets(filters, args.output_csv)

    logger.info(f"감사 대상 수: {len(project_ids)}")
    for pid, folder in zip(project_ids, search_folders):
        logger.info(f"Project ID: {pid}, Search Folder: {folder}")
        
# python audit_target_generator.py 