# my_flask_app/audit_target_generator.py
import pandas as pd
import argparse
import os
import re
from config_assets import AUDIT_FILTERS, DEPARTMENT_MAPPING, AUDIT_FILTERS_depart, get_department_code, get_department_name
import logging
from config import STATIC_DATA_PATH, PROJECT_LIST_CSV  # NETWORK_BASE_PATH 제거

# 로깅 설정 (디버깅 로그 레벨로 변경)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def select_audit_targets(filters=None, output_csv=None):
    """
    필터 조건으로 새로운 감사 대상을 선정하고 CSV로 저장하며, DataFrame 반환
    Args:
        filters (dict): 필터 조건 (status, year, department)
        output_csv (str): 출력 CSV 파일 경로 (기본값: static/data/audit_targets_new.csv)
    Returns:
        tuple: (audit_targets_df, project_ids, search_folders) DataFrame와 리스트
    """
    # CLI 인수 또는 config에서 필터 읽기
    if filters is None:
        filters = AUDIT_FILTERS.copy()  # AUDIT_FILTERS의 복사본 사용
        # status 필터가 없으면 기본값 설정
        if not filters.get('status'):
            filters['status'] = ['진행', '준공']
        # year 필터가 없으면 AUDIT_FILTERS의 기본값 사용->전체가져옴
        # if not filters.get('year'):
        #     filters['year'] = AUDIT_FILTERS.get('year', [2024])  # AUDIT_FILTERS에서 가져오되, 없으면 2024를 기본값으로
        # department 필터를 AUDIT_FILTERS_depart로 설정
        if not filters.get('department'):
            filters['department'] = {'include': AUDIT_FILTERS_depart, 'exclude': []}
    
    logger.info("Using audit filters from config_assets.py. Modify AUDIT_FILTERS in config_assets.py to adjust filtering conditions:")
    logger.info(f"- Status: {filters.get('status', 'Not specified')} (진행: 성과품 미완성 가능, 부분 문서 허용 / 준공: 성과품 완벽히 포함해야 함, 100% 문서 필요)")
    logger.info(f"- Year: {filters.get('year', 'Not specified')} (2024년 준공 프로젝트만 감사)")
    logger.info(f"- Department: Include {', '.join(filters['department']['include'] or ['All'])} / Exclude {', '.join(filters['department']['exclude'] or ['None'])} (부서 필터링)")

    # 출력 CSV 경로 설정 (기본값 사용)
    if output_csv is None:
        output_csv = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')

    # CSV 파일 읽기 (순수 UTF-8 인코딩, 에러 처리 강화)
    input_file = os.path.join(STATIC_DATA_PATH, 'contract_status.csv')
    try:
        df_contract = pd.read_csv(input_file, encoding='utf-8', on_bad_lines='warn')  # BOM 없이 순수 UTF-8로 읽기, 형식 오류 경고
        # 데이터 유효성 검증 로그 추가
        logger.debug(f"Loaded contract_status.csv with {len(df_contract)} rows. Sample 사업코드: {df_contract['사업코드'].head().tolist()}")
    except FileNotFoundError:
        logger.error(f"파일을 찾을 수 없습니다: {input_file}")
        raise
    except Exception as e:
        logger.error(f"CSV 파일 읽기 오류: {str(e)}")
        raise

    # 열 목록 디버깅 로그로 출력
    logger.debug(f"Columns in contract_status.csv: {df_contract.columns.tolist()}")

    # 사업코드 필터링 (B로 시작하거나 8자리 숫자 뒤 영문자 포함 제외)
    def is_valid_project_code(code):
        if pd.isna(code) or not isinstance(code, str):
            return False
        # B로 시작하는 경우 제외
        if code.startswith('B'):
            return False
        # 8자리 숫자 뒤 영문자 포함 여부 체크
        match = re.match(r'^[A-Z]?(\d{8})([A-Z])?$', code)
        if match and match.group(2):  # 8자리 숫자 뒤 영문자 있음
            return False
        return True

    # 준공일에서 연도 추출 함수
    def extract_year(completion_date):
        if pd.isna(completion_date) or not isinstance(completion_date, str):
            return None
        # 연도 추출 (예: '2024-01-01', '2024', '2024년' 등)
        match = re.search(r'(\d{4})', completion_date)
        return match.group(1) if match else None

    # 필터링 조건 적용 (진행상태, 준공일, 부서 기준)
    # 기본 마스크 생성 (진행 상태)
    mask = pd.Series(False, index=df_contract.index)
    
    # 진행 상태별 필터링
    for status in filters['status']:
        if status == '준공':
            # 준공 상태는 연도 필터와 함께 적용
            completion_year = [str(year) for year in filters['year']]
            mask |= (df_contract['진행상태'] == '준공') & \
                    df_contract['변경준공일(차수)'].apply(lambda x: extract_year(x) in completion_year)
        else:
            # 진행 중인 프로젝트는 연도 필터 없이 적용
            mask |= (df_contract['진행상태'] == status)

    # 사업코드 필터링 추가
    mask &= df_contract['사업코드'].apply(is_valid_project_code)

    # 부서 필터링 추가 (포함/제외 로직)
    if filters['department']:
        include_depts = filters['department']['include']
        exclude_depts = filters['department']['exclude']
        
        def filter_department(dept):
            if not dept or pd.isna(dept):
                return False
            if include_depts and dept not in include_depts:
                return False
            if exclude_depts and dept in exclude_depts:
                return False
            return True
        
        mask &= df_contract['PM부서'].apply(filter_department)

    # 필터링된 프로젝트 디버깅 로그
    logger.debug(f"Filtered projects (mask): {df_contract[mask]['사업코드'].tolist()}")
    logger.debug(f"Filtered projects details: {df_contract[mask][['사업코드', '진행상태', 'PM부서', '변경준공일(차수)']].to_dict()}")

    # 필터링된 데이터 (지정된 필드만 가져오기)
    df_contract_selected = df_contract[mask][['사업코드', '사업명', 'PM부서', '진행상태', '주관사']]
    df_contract_selected.columns = ['ProjectID', 'ProjectName', 'Depart', 'Status', 'Contractor']

    # ProjectID 유지 (사업코드 그대로, 영문 접두사 포함)
    df_contract_selected['ProjectID'] = df_contract_selected['ProjectID']

    # ProjectID_numeric 추가 (사업코드에서 8자리 숫자만 추출)
    df_contract_selected['ProjectID_numeric'] = df_contract_selected['ProjectID'].apply(
        lambda x: re.search(r'\d{8}', str(x)).group(0) if pd.notna(x) and re.search(r'\d{8}', str(x)) else ''
    )

    # Depart_ProjectID 생성 ({부서코드}_{사업코드})
    df_contract_selected['Depart_ProjectID'] = df_contract_selected.apply(
        lambda row: f"{get_department_code(row['Depart'])}_{row['ProjectID']}", 
        axis=1
    )

    # 프로젝트 리스트에서 search_folder 직접 가져오기 (네트워크 드라이브 접두사 제거)
    try:
        if os.path.exists(PROJECT_LIST_CSV):
            df_projects = pd.read_csv(PROJECT_LIST_CSV, encoding='utf-8', on_bad_lines='warn')  # BOM 없이 순수 UTF-8로 읽기
            # project_list.csv의 project_id에서 숫자만 추출
            df_projects['numeric_project_id'] = df_projects['project_id'].apply(lambda x: re.search(r'\d{8}', str(x)).group(0) if pd.notna(x) and re.search(r'\d{8}', str(x)) else '')
            # df_contract_selected의 ProjectID_numeric과 매핑
            df_contract_selected = df_contract_selected.merge(
                df_projects[['numeric_project_id', 'original_folder']],
                left_on='ProjectID_numeric',
                right_on='numeric_project_id',
                how='left'
            )
            # original_folder에서 네트워크 드라이브 접두사 제거
            df_contract_selected['search_folder'] = df_contract_selected['original_folder'].apply(
                lambda x: re.sub(r'^[A-Z]:\\', '', str(x)) if pd.notna(x) else 'No folder'
            )
            # 원래 필요 없는 열 제거
            df_contract_selected.drop(columns=['numeric_project_id', 'original_folder'], inplace=True)
        else:
            logger.warning(f"Project list file not found: {PROJECT_LIST_CSV}, setting search_folder to 'No folder'")
            df_contract_selected['search_folder'] = 'No folder'
    except Exception as e:
        logger.error(f"Error processing project_list.csv: {str(e)}")
        df_contract_selected['search_folder'] = 'No folder'

    logger.debug(f"Search folders for projects: {df_contract_selected[['Depart_ProjectID', 'ProjectID', 'ProjectID_numeric', 'search_folder']].to_dict()}")

    # 결과 저장 (audit_targets_new.csv, 부서 정보 포함)
    audit_targets = df_contract_selected[['Depart_ProjectID', 'ProjectID', 'ProjectID_numeric', 'Depart', 'Status', 'ProjectName', 'Contractor', 'search_folder']]
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)  # 상위 디렉토리 생성
    audit_targets.to_csv(output_csv, index=False, encoding='utf-8')  # BOM 없이 순수 UTF-8로 저장

    logger.info(f"새로운 감사 대상이 {output_csv}에 저장되었습니다. 총 프로젝트 수: {len(audit_targets)}")
    logger.info(f"Audit targets filtered by status: {filters['status']} with document requirements applied (진행: 부분 문서 허용, 준공: 100% 문서 필요)")

    # audit_results.csv 생성 (search_folder가 'No folder'인 프로젝트 표시)
    audit_results_csv = os.path.join(STATIC_DATA_PATH, 'audit_results.csv')
    results_df = audit_targets[audit_targets['search_folder'] == 'No folder'][['Depart_ProjectID', 'ProjectID', 'ProjectID_numeric', 'Depart', 'Status', 'ProjectName', 'Contractor']]
    if not results_df.empty:
        os.makedirs(os.path.dirname(audit_results_csv), exist_ok=True)
        results_df.to_csv(audit_results_csv, index=False, encoding='utf-8')  # BOM 없이 순수 UTF-8로 저장
        logger.info(f"Audit results (no folder projects) saved to {audit_results_csv}. Total projects: {len(results_df)}")
    else:
        logger.info(f"No projects without folders found, audit_results.csv not created")

    # DataFrame 반환 (project_ids, project_ids_numeric, search_folders 사용)
    project_ids = df_contract_selected['ProjectID'].tolist()
    project_ids_numeric = df_contract_selected['ProjectID_numeric'].tolist()
    search_folders = df_contract_selected['search_folder'].tolist()

    return audit_targets, project_ids, project_ids_numeric, search_folders

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="새로운 감사 대상 프로젝트 필터링")
    parser.add_argument('--year', type=int, nargs='+', default=AUDIT_FILTERS['year'], help="필터링할 준공 연도 (여러 개 가능)")
    parser.add_argument('--status', type=str, nargs='+', default=AUDIT_FILTERS['status'], help="필터링할 진행 상태 (여러 개 가능: '진행', '준공', '중지', '탈락')")
    parser.add_argument('--output-csv', type=str, default=os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv'), help="출력 CSV 파일 경로")
    parser.add_argument('--verbose', action='store_true', help="상세 로그 출력")
    parser.add_argument('--include-department', type=str, nargs='+', help="포함할 부서 (한글 부서명, 다중 값 가능)")
    parser.add_argument('--exclude-department', type=str, nargs='+', help="제외할 부서 (한글 부서명, 다중 값 가능)")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    filters = {
        'year': args.year or AUDIT_FILTERS['year'],
        'status': args.status or AUDIT_FILTERS['status'],
        'department': {
            'include': args.include_department or AUDIT_FILTERS_depart,  # 기본값으로 AUDIT_FILTERS_depart 사용
            'exclude': args.exclude_department or []  # 기본값으로 제외 부서 없음
        }
    }
    try:
        audit_targets_df, project_ids, project_ids_numeric, search_folders = select_audit_targets(filters, args.output_csv)
    except Exception as e:
        logger.error(f"Error in select_audit_targets: {str(e)}")
        raise

    logger.info(f"감사 대상 수: {len(project_ids)}")
    for pid, pid_numeric, folder in zip(project_ids, project_ids_numeric, search_folders):
        logger.info(f"Project ID: {pid}, Numeric Project ID: {pid_numeric}, Search Folder: {folder}")
        
# python audit_target_generator.py 