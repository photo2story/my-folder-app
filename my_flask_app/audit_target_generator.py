# my_flask_app/audit_target_generator.py
import pandas as pd
import argparse
import os
from config_assets import AUDIT_FILTERS, AUDIT_FILTERS_depart, DEPARTMENT_MAPPING, DEPARTMENT_NAMES
import logging
from config import STATIC_DATA_PATH

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def generate_unique_id(department_code, project_id):
    """부서 코드와 프로젝트 ID를 결합하여 유니크 ID 생성"""
    return f"{department_code}_{project_id}"

# my-flask-app/audit_target_generator.py
# ... (기존 코드 유지)

def select_audit_targets(filters=None, output_csv=None):
    """
    필터 조건으로 새로운 감사 대상을 선정하고 CSV로 저장하며, DataFrame 반환
    Args:
        filters (dict): 필터 조건 (status, is_main_contractor, year, department)
        output_csv (str): 출력 CSV 파일 경로 (기본값: static/data/audit_targets_new.csv)
    Returns:
        tuple: (audit_targets_df, project_ids, department_codes) DataFrame와 리스트
    """
    # CLI 인수 또는 config에서 필터 읽기
    if filters is None:
        filters = AUDIT_FILTERS
        # status 필터를 모든 가능한 값으로 설정 (사용자 조정 가능)
        if not filters.get('status'):
            filters['status'] = ['준공', '진행', '중지', '탈락']
    
    logger.info("Using audit filters from config_assets.py. Modify AUDIT_FILTERS in config_assets.py to adjust filtering conditions:")
    logger.info(f"- Status: {filters.get('status', 'Not specified')}")
    logger.info(f"- Is Main Contractor: {filters.get('is_main_contractor', 'Not specified')}")
    logger.info(f"- Year: {filters.get('year', 'Not specified')}")
    logger.info(f"- Department: {filters.get('department', 'Not specified')}")

    # 출력 CSV 경로 설정 (기본값 사용)
    if output_csv is None:
        output_csv = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')

    # CSV 파일 읽기 (UTF-8 with BOM 인코딩)
    input_file = os.path.join(STATIC_DATA_PATH, 'contract_status.csv')
    try:
        df = pd.read_csv(input_file, encoding='utf-8-sig')
    except FileNotFoundError:
        logger.error(f"파일을 찾을 수 없습니다: {input_file}")
        raise
    except Exception as e:
        logger.error(f"CSV 파일 읽기 오류: {str(e)}")
        raise

    # 부서 목록에서 department 필터 기본값 설정 (AUDIT_FILTERS_depart 사용)
    if filters.get('department') is None:
        filters['department'] = AUDIT_FILTERS_depart

    # 날짜 변환 (공백 또는 잘못된 형식은 NaT로 처리)
    df['변경준공일(차수)'] = pd.to_datetime(df['변경준공일(차수)'], errors='coerce')

    # 필터링 조건 적용
    mask = True
    if 'status' in filters and filters['status']:
        mask &= df['진행상태'].isin(filters['status'])
    if 'year' in filters and filters['year']:
        mask &= df['변경준공일(차수)'].dt.year.isin(filters['year'])
    if 'department' in filters and filters['department']:
        # department_code로 변환 후 필터링
        dept_codes = pd.Series([DEPARTMENT_MAPPING.get(dept, '99999') for dept in df['PM부서']])
        mask &= dept_codes.isin(filters['department'])

    # 필터링된 데이터
    filtered_df = df[mask][['사업코드', 'PM부서', '사업명', '진행상태', '주관사']]
    filtered_df.columns = ['project_id', 'department_name', 'project_name', 'status', 'is_main_contractor']

    # 부서, 진행여부, 주관사여부, 프로젝트명 생성
    filtered_df['Depart'] = filtered_df['department_name'].map(
        lambda dept: DEPARTMENT_NAMES.get(DEPARTMENT_MAPPING.get(dept, '99999'), 'UnknownDepartment')
    )
    filtered_df['Status'] = filtered_df['status'].apply(lambda x: x if x in ['진행', '중지', '준공', '탈락'] else None)
    filtered_df['Contractor'] = filtered_df['is_main_contractor']
    filtered_df['ProjectName'] = filtered_df['project_name']

    # 진행여부가 None인 행 제거
    filtered_df = filtered_df.dropna(subset=['Status'])

    # Depart_ProjectID 생성 (유니크 ID)
    filtered_df['Depart_ProjectID'] = filtered_df.apply(
        lambda row: generate_unique_id(DEPARTMENT_MAPPING.get(row['department_name'], '99999'), row['project_id']), axis=1
    )

    # 매핑되지 않은 부서 로그 출력
    missing_depts = filtered_df[filtered_df['Depart'] == 'UnknownDepartment']['department_name'].unique()
    if len(missing_depts) > 0:
        logger.warning(f"매핑되지 않은 부서 이름: {missing_depts}")

    # 결과 저장 (새로운 열 포함)
    audit_targets = filtered_df[['Depart_ProjectID', 'Depart', 'Status', 'Contractor', 'ProjectName']]
    audit_targets.to_csv(output_csv, index=False, encoding='utf-8-sig')

    logger.info(f"새로운 감사 대상이 {output_csv}에 저장되었습니다. 총 프로젝트 수: {len(audit_targets)}")

    # DataFrame 반환 (후속 처리용)
    return audit_targets, filtered_df['project_id'].tolist(), filtered_df['Depart'].map(
        lambda dept: next((k for k, v in DEPARTMENT_NAMES.items() if v == dept), '99999')
    ).tolist()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="새로운 감사 대상 프로젝트 필터링")
    parser.add_argument('--year', type=int, nargs='+', default=AUDIT_FILTERS['year'], help="필터링할 준공 연도 (여러 개 가능)")
    parser.add_argument('--status', type=str, nargs='+', default=AUDIT_FILTERS['status'], help="필터링할 진행 상태 (여러 개 가능: '준공', '진행', '중지', '탈락')")
    parser.add_argument('--department', type=str, nargs='+', default=None, help="필터링할 부서 코드 (기본값: AUDIT_FILTERS_depart)")
    parser.add_argument('--output-csv', type=str, default=os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv'), help="출력 CSV 파일 경로")
    parser.add_argument('--verbose', action='store_true', help="상세 로그 출력")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    filters = {
        'year': args.year,
        'status': args.status,
        'department': args.department or AUDIT_FILTERS_depart
    }
    audit_targets_df, project_ids, department_codes = select_audit_targets(filters, args.output_csv)

    logger.info(f"감사 대상 수: {len(project_ids)}")
    for pid, dc in zip(project_ids, department_codes):
        logger.info(f"Project ID: {pid}, Department Code: {dc}")        


# python audit_target_generator.py --verbose