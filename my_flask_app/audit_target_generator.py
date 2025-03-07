# my_flask_app/audit_target_generator.py
import pandas as pd
import argparse
import os
import re
from config_assets import AUDIT_FILTERS, DEPARTMENT_MAPPING, AUDIT_FILTERS_depart, get_department_code, get_department_name
import logging
from config import STATIC_DATA_PATH, PROJECT_LIST_CSV

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def filter_by_pm_department(df):
    """
    중복된 ProjectID를 PM부서와 매핑하여 필터링하고, 준공 폴더를 우선 처리
    """
    pm_dept_map = df_contract.set_index('사업코드')['PM부서'].to_dict()
    
    def simplify_dept_name(dept):
        return dept.replace('부', '') if isinstance(dept, str) else dept
    
    def get_folder_info(folder):
        if pd.isna(folder) or folder == 'No folder':
            return None, None
        match = re.match(r'(\d{5})_(.+?)\\', folder)
        if match:
            return match.group(1), simplify_dept_name(match.group(2))
        return None, simplify_dept_name(folder.split('\\')[0])

    filtered_rows = []
    for pid in df['ProjectID'].unique():
        pid_rows = df[df['ProjectID'] == pid].copy()
        logger.debug(f"Processing ProjectID {pid} with {len(pid_rows)} rows")
        
        if len(pid_rows) > 1:
            pm_dept = pm_dept_map.get(pid)
            simplified_pm_dept = simplify_dept_name(pm_dept) if pm_dept else None
            logger.debug(f"PM Department for {pid}: {pm_dept} (simplified: {simplified_pm_dept})")
            
            completed_rows = pid_rows[pid_rows['Status'] == '준공']
            if not completed_rows.empty:
                junggong_rows = completed_rows[completed_rows['search_folder'].str.startswith('99999_준공')]
                if not junggong_rows.empty:
                    filtered_rows.append(junggong_rows.iloc[0])
                    logger.info(f"ProjectID {pid}: Selected 99999_준공 folder for completed project")
                    continue
            
            matching_rows = pid_rows[pid_rows['Depart'].apply(
                lambda x: simplify_dept_name(x) == simplified_pm_dept if simplified_pm_dept else True
            )]
            logger.debug(f"Matching rows for {pid}: {len(matching_rows)} found")
            
            if not matching_rows.empty:
                for _, row in matching_rows.iterrows():
                    folder_code, folder_dept = get_folder_info(row['search_folder'])
                    simplified_dept = simplify_dept_name(row['Depart'])
                    dept_code = get_department_code(row['Depart'])
                    logger.debug(f"Checking row: Depart={row['Depart']} (code={dept_code}), Folder={row['search_folder']} (code={folder_code}, dept={folder_dept})")
                    
                    if folder_code == dept_code and (folder_dept == simplified_dept or folder_dept is None):
                        filtered_rows.append(row)
                        logger.info(f"ProjectID {pid}: Matched folder {row['search_folder']} with Depart {row['Depart']}")
                        break
                else:
                    filtered_rows.append(matching_rows.iloc[0])
                    logger.warning(f"ProjectID {pid}: No exact folder match, using first matching row")
            else:
                filtered_rows.append(pid_rows.iloc[0])
                logger.warning(f"ProjectID {pid}: No PM department match, using first row")
        else:
            row = pid_rows.iloc[0]
            folder_code, folder_dept = get_folder_info(row['search_folder'])
            simplified_dept = simplify_dept_name(row['Depart'])
            dept_code = get_department_code(row['Depart'])
            if folder_code and folder_code != dept_code and folder_dept != simplified_dept and row['search_folder'] != 'No folder':
                logger.warning(f"ProjectID {pid}: Depart {row['Depart']} (code {dept_code}) and folder {row['search_folder']} mismatch")
            filtered_rows.append(row)
            logger.debug(f"ProjectID {pid}: Single row retained")
    
    return pd.DataFrame(filtered_rows)

def select_audit_targets(filters=None, output_csv=None):
    global df_contract
    
    if filters is None:
        filters = AUDIT_FILTERS.copy()
        if not filters.get('status'):
            filters['status'] = ['진행', '준공']
        if not filters.get('department'):
            filters['department'] = {'include': AUDIT_FILTERS_depart, 'exclude': []}
    
    logger.info("Using audit filters from config_assets.py:")
    logger.info(f"- Status: {filters.get('status', 'Not specified')}")
    logger.info(f"- Year: {filters.get('year', 'Not specified')}")
    logger.info(f"- Department: Include {', '.join(filters['department']['include'] or ['All'])} / Exclude {', '.join(filters['department']['exclude'] or ['None'])}")

    if output_csv is None:
        output_csv = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')

    input_file = os.path.join(STATIC_DATA_PATH, 'contract_status.csv')
    try:
        df_contract = pd.read_csv(input_file, encoding='utf-8', on_bad_lines='warn')
        logger.debug(f"Loaded contract_status.csv with {len(df_contract)} rows. Sample 사업코드: {df_contract['사업코드'].head().tolist()}")
    except FileNotFoundError:
        logger.error(f"파일을 찾을 수 없습니다: {input_file}")
        raise
    except Exception as e:
        logger.error(f"CSV 파일 읽기 오류: {str(e)}")
        raise

    logger.debug(f"Columns in contract_status.csv: {df_contract.columns.tolist()}")

    def is_valid_project_code(code):
        if pd.isna(code) or not isinstance(code, str):
            return False
        if code.startswith('B'):
            return False
        match = re.match(r'^[A-Z]?(\d{8})([A-Z])?$', code)
        if match and match.group(2):
            return False
        return True

    def extract_year(completion_date):
        if pd.isna(completion_date) or not isinstance(completion_date, str):
            return None
        match = re.search(r'(\d{4})', completion_date)
        return match.group(1) if match else None

    mask = pd.Series(False, index=df_contract.index)
    for status in filters['status']:
        if status == '준공':
            completion_year = [str(year) for year in filters['year']]
            mask |= (df_contract['진행상태'] == '준공') & \
                    df_contract['변경준공일(차수)'].apply(lambda x: extract_year(x) in completion_year)
        else:
            mask |= (df_contract['진행상태'] == status)

    mask &= df_contract['사업코드'].apply(is_valid_project_code)

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

    logger.debug(f"Filtered projects (mask): {df_contract[mask]['사업코드'].tolist()}")

    df_contract_selected = df_contract[mask][['사업코드', '사업명', 'PM부서', '진행상태', '주관사']]
    df_contract_selected.columns = ['ProjectID', 'ProjectName', 'Depart', 'Status', 'Contractor']
    df_contract_selected['ProjectID'] = df_contract_selected['ProjectID']
    df_contract_selected['ProjectID_numeric'] = df_contract_selected['ProjectID'].apply(
        lambda x: re.search(r'\d{8}', str(x)).group(0) if pd.notna(x) and re.search(r'\d{8}', str(x)) else ''
    )
    df_contract_selected['Depart_ProjectID'] = df_contract_selected.apply(
        lambda row: f"{get_department_code(row['Depart'])}_{row['ProjectID']}", axis=1
    )

    # 원래 프로젝트 리스트에서 search_folder 가져오기 로직 유지
    try:
        if os.path.exists(PROJECT_LIST_CSV):
            df_projects = pd.read_csv(PROJECT_LIST_CSV, encoding='utf-8', on_bad_lines='warn')
            df_projects['numeric_project_id'] = df_projects['project_id'].apply(
                lambda x: re.search(r'\d{8}', str(x)).group(0) if pd.notna(x) and re.search(r'\d{8}', str(x)) else ''
            )
            df_contract_selected = df_contract_selected.merge(
                df_projects[['numeric_project_id', 'original_folder']],
                left_on='ProjectID_numeric',
                right_on='numeric_project_id',
                how='left'
            )
            df_contract_selected['search_folder'] = df_contract_selected['original_folder'].apply(
                lambda x: re.sub(r'^[A-Z]:\\', '', str(x)) if pd.notna(x) else 'No folder'
            )
            df_contract_selected.drop(columns=['numeric_project_id', 'original_folder'], inplace=True)
        else:
            logger.warning(f"Project list file not found: {PROJECT_LIST_CSV}, setting search_folder to 'No folder'")
            df_contract_selected['search_folder'] = 'No folder'
    except Exception as e:
        logger.error(f"Error processing project_list.csv: {str(e)}")
        df_contract_selected['search_folder'] = 'No folder'

    # 필터링 적용
    audit_targets = filter_by_pm_department(df_contract_selected)

    audit_targets.to_csv(output_csv, index=False, encoding='utf-8')
    logger.info(f"새로운 감사 대상이 {output_csv}에 저장되었습니다. 총 프로젝트 수: {len(audit_targets)}")

    audit_results_csv = os.path.join(STATIC_DATA_PATH, 'audit_results.csv')
    results_df = audit_targets[audit_targets['search_folder'] == 'No folder']
    if not results_df.empty:
        os.makedirs(os.path.dirname(audit_results_csv), exist_ok=True)
        results_df.to_csv(audit_results_csv, index=False, encoding='utf-8')
        logger.info(f"Audit results (no folder projects) saved to {audit_results_csv}. Total projects: {len(results_df)}")
    else:
        logger.info("No projects without folders found, audit_results.csv not created")

    project_ids = audit_targets['ProjectID'].tolist()
    project_ids_numeric = audit_targets['ProjectID_numeric'].tolist()
    search_folders = audit_targets['search_folder'].tolist()

    return audit_targets, project_ids, project_ids_numeric, search_folders

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="새로운 감사 대상 프로젝트 필터링")
    parser.add_argument('--year', type=int, nargs='+', default=AUDIT_FILTERS['year'])
    parser.add_argument('--status', type=str, nargs='+', default=AUDIT_FILTERS['status'])
    parser.add_argument('--output-csv', type=str, default=os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv'))
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--include-department', type=str, nargs='+')
    parser.add_argument('--exclude-department', type=str, nargs='+')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    filters = {
        'year': args.year or AUDIT_FILTERS['year'],
        'status': args.status or AUDIT_FILTERS['status'],
        'department': {
            'include': args.include_department or AUDIT_FILTERS_depart,
            'exclude': args.exclude_department or []
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