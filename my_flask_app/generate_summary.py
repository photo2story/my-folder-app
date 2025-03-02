# my_flask_app/generate_summary.py

import os
import json
import pandas as pd
import re
from glob import glob
from datetime import datetime
import logging  # logging 모듈 추가

from config import STATIC_DATA_PATH, CONTRACT_STATUS_CSV
from config_assets import DOCUMENT_TYPES, DEPARTMENT_MAPPING, DEPARTMENT_NAMES
import argparse

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)  # logger 객체 전역으로 초기화

def load_contract_data(verbose=False):
    """계약현황 CSV 로드 및 ProjectID 기반으로 검색 가능하도록 변환 (백업으로 사용)"""
    try:
        df = pd.read_csv(CONTRACT_STATUS_CSV, encoding='utf-8')
        # PM부서와 주관사 열 추가 확인
        if 'PM부서' not in df.columns or '주관사' not in df.columns:
            raise ValueError("CSV must contain 'PM부서' and '주관사' columns")

        # PM부서에서 부서 코드로 매핑
        def map_department(pm_dept):
            dept_name = pm_dept.strip()
            dept_code = DEPARTMENT_MAPPING.get(dept_name, None)
            if dept_code is None:
                for code, name in DEPARTMENT_NAMES.items():
                    if name == dept_name or dept_name in name:
                        return code
            return dept_code or '99999'

        # 요청된 데이터로 변환 및 ProjectID 추가 (숫자 부분)
        result_df = df[['사업코드', 'PM부서', '진행상태', '사업명', '주관사']].copy()
        result_df.columns = ['BusinessCode', 'Depart_Name', 'Status', 'ProjectName', 'Contractor_Role']
        
        # ProjectID 생성 (사업코드에서 알파벳 제거)
        result_df['ProjectID'] = result_df['BusinessCode'].apply(lambda x: re.sub(r'[^0-9]', '', str(x)))
        
        # 부서 코드 매핑
        result_df['Depart'] = result_df['Depart_Name'].apply(map_department)
        
        # Depart_ProjectID 생성 (부서코드_사업코드)
        result_df['Depart_ProjectID'] = result_df.apply(lambda row: f"{row['Depart']}_{row['BusinessCode']}", axis=1)
        
        # Depart를 부서명으로 변환
        result_df['Depart'] = result_df['Depart'].map(DEPARTMENT_NAMES).fillna(result_df['Depart'])
        
        # Contractor를 주관사/비주관사로 변환
        result_df['Contractor'] = result_df['Contractor_Role'].apply(lambda x: '주관사' if x == '주관사' else '비주관사')
        
        # 최종 열 순서 조정 (요청된 순서 유지)
        result_df = result_df[['Depart_ProjectID', 'ProjectID', 'Depart', 'Status', 'Contractor', 'ProjectName']]
        
        if verbose:
            logger.debug(f"Loaded contract data with {len(result_df)} records")
        return result_df
    except Exception as e:
        logger.error(f"Failed to load contract data from {CONTRACT_STATUS_CSV}: {str(e)}")
        return pd.DataFrame()

def load_audit_results(results_dir, verbose=False):
    """감사 결과 JSON 파일 로드"""
    pattern = os.path.join(results_dir, 'audit_*.json')
    audit_files = glob(pattern)
    
    if not audit_files and verbose:
        logger.warning(f"No audit files found in {results_dir}")
    
    results = {}
    for file_path in audit_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'error' not in data:
                    project_id = re.sub(r'[^0-9]', '', str(data['project_id']))
                    dept_code = data['department'].split('_')[0] if '_' in data['department'] else '99999'
                    
                    # audit_targets_new.csv에서 Status와 Contractor 가져오기 (기본 소스)
                    status, contractor = get_status_contractor_from_targets(project_id, dept_code)
                    if status is None or contractor is None:
                        # contract_status.csv에서 백업으로 가져오기
                        status, contractor = get_status_contractor_from_contract(project_id, contract_df)
                    
                    depart_project_id = f"{dept_code}_{project_id}"
                    results[project_id] = {
                        'documents': data['documents'],
                        'depart_project_id': depart_project_id,
                        'status': status,
                        'contractor': contractor
                    }
                elif verbose:
                    logger.debug(f"SKIP {file_path}: Audit contains error")
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {str(e)}")
    return results

def get_status_contractor_from_targets(project_id, dept_code):
    """audit_targets_new.csv에서 Status와 Contractor 가져오기"""
    audit_targets_path = os.path.join(STATIC_DATA_PATH, 'data', 'audit_targets_new.csv')
    if os.path.exists(audit_targets_path):
        try:
            df_targets = pd.read_csv(audit_targets_path, encoding='utf-8-sig')
            # Depart_ProjectID에서 사업코드 추출
            df_targets['ProjectID'] = df_targets['Depart_ProjectID'].apply(lambda x: re.sub(r'[^0-9]', '', str(x).split('_C')[-1]) if '_C' in str(x) else re.sub(r'[^0-9]', '', str(x)))
            target_match = df_targets[df_targets['ProjectID'] == str(project_id)]
            
            if len(target_match) > 0:
                row = target_match.iloc[0]
                status = row.get('Status', 'Unknown')
                contractor = row.get('Contractor', 'Unknown')
                return status, contractor
        except Exception as e:
            logger.error(f"Failed to load status and contractor from audit_targets_new.csv for project_id {project_id}: {str(e)}")
    return None, None

def get_status_contractor_from_contract(project_id, contract_df):
    """contract_status.csv에서 Status와 Contractor 가져오기 (백업)"""
    try:
        if 'ProjectID' in contract_df.columns:
            match = contract_df['ProjectID'] == str(project_id)
            if match.any():
                row = contract_df.loc[match].iloc[0]
                status = str(row['Status']) if pd.notna(row['Status']) else 'Unknown'
                contractor = str(row['Contractor']) if pd.notna(row['Contractor']) else 'Unknown'
                return status, contractor
    except Exception as e:
        logger.error(f"Failed to load status and contractor from contract_status.csv for project_id {project_id}: {str(e)}")
    return 'Unknown', 'Unknown'

def merge_contract_audit(contract_df, audit_results, verbose=False):
    """계약현황과 감사 결과를 결합"""
    doc_types = list(DOCUMENT_TYPES.keys())  # DOCUMENT_TYPES 순서 유지
    
    # 계약현황 데이터에 감사 결과 추가
    merged_data = []
    for project_id, audit_data in audit_results.items():
        # audit_targets_new.csv 또는 contract_status.csv에서 데이터 가져오기
        target_match = pd.DataFrame()
        if 'ProjectID' in contract_df.columns:
            target_match = contract_df[contract_df['ProjectID'] == str(project_id)]
        
        if len(target_match) > 0:
            row = target_match.iloc[0]
            audit_docs = audit_data['documents']
            depart_project_id = audit_data['depart_project_id']
            status = audit_data['status']
            contractor = audit_data['contractor']
            
            merged_row = {
                'project_id': project_id,
                'department': row['Depart'],
                'project_name': row['ProjectName'],
                'Status': status,
                'Contractor': contractor,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # timestamp 추가
            }
            
            for doc_type in doc_types:
                merged_row[f'{doc_type}_exists'] = 1 if audit_docs.get(doc_type, {}).get('exists', False) else 0
                merged_row[f'{doc_type}_count'] = len(audit_docs.get(doc_type, {}).get('details', [])) if merged_row[f'{doc_type}_exists'] else 0
            
            merged_data.append(merged_row)
        else:
            # contract_status.csv에 없으면 audit_targets_new.csv에서 직접 가져오기
            audit_targets_path = os.path.join(STATIC_DATA_PATH, 'data', 'audit_targets_new.csv')
            if os.path.exists(audit_targets_path):
                try:
                    df_targets = pd.read_csv(audit_targets_path, encoding='utf-8-sig')
                    df_targets['ProjectID'] = df_targets['Depart_ProjectID'].apply(lambda x: re.sub(r'[^0-9]', '', str(x).split('_C')[-1]) if '_C' in str(x) else re.sub(r'[^0-9]', '', str(x)))
                    target_match = df_targets[df_targets['ProjectID'] == str(project_id)]
                    
                    if len(target_match) > 0:
                        row = target_match.iloc[0]
                        dept_code = re.sub(r'[^0-9]', '', str(row['Depart_ProjectID']).split('_')[0]).zfill(5)
                        dept_name = row.get('Depart', 'Unknown')
                        audit_docs = audit_data['documents']
                        
                        # PROJECT_LIST_CSV에서 original_folder 가져오기
                        project_list_path = PROJECT_LIST_CSV
                        original_folder = None
                        if os.path.exists(project_list_path):
                            try:
                                df_project = pd.read_csv(project_list_path, dtype={'department_code': str, 'project_id': str})
                                project = df_project[df_project['project_id'] == project_id]
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
                            original_folder = os.path.join(NETWORK_BASE_PATH, f"{dept_code}_{dept_name}", f"{project_id}_{row.get('ProjectName', f'Project {project_id}')}")
                            logger.debug(f"Generated default project folder: {original_folder}")

                        if os.path.exists(original_folder):
                            merged_row = {
                                'project_id': project_id,
                                'department': f"{dept_code}_{dept_name}",
                                'project_name': row.get('ProjectName', f'Project {project_id}'),
                                'Status': row.get('Status', 'Unknown'),
                                'Contractor': row.get('Contractor', 'Unknown'),
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # timestamp 추가
                            }
                            
                            for doc_type in doc_types:
                                merged_row[f'{doc_type}_exists'] = 1 if audit_docs.get(doc_type, {}).get('exists', False) else 0
                                merged_row[f'{doc_type}_count'] = len(audit_docs.get(doc_type, {}).get('details', [])) if merged_row[f'{doc_type}_exists'] else 0
                            
                            merged_data.append(merged_row)
                        else:
                            logger.error(f"Project folder does not exist: {original_folder}")
                    else:
                        logger.warning(f"Project ID {project_id} not found in audit_targets_new.csv")
                except Exception as e:
                    logger.error(f"Error loading audit_targets_new.csv: {str(e)}")
            else:
                logger.error(f"audit_targets_new.csv not found: {audit_targets_path}")

    if not merged_data:
        logger.warning("No audit results found to merge with contract data.")
        return pd.DataFrame()
    
    # DataFrame 생성 및 정렬
    merged_df = pd.DataFrame(merged_data)
    merged_df = merged_df.sort_values(['department', 'project_id'], ascending=[True, True])
    
    if verbose:
        logger.debug(f"Merged data with {len(merged_df)} records")
    return merged_df

def generate_combined_report(results_dir, output_path, verbose=False):
    """계약현황과 감사 결과를 결합한 보고서 생성"""
    global contract_df  # contract_df를 전역 변수로 설정
    logger.info("=== Starting Combined Report Generation ===")
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 계약현황 데이터 로드 (백업으로 사용)
    contract_df = load_contract_data(verbose)
    if contract_df.empty and verbose:
        logger.warning("No contract data found, using audit_targets_new.csv as primary source")
    
    # 감사 결과 로드
    audit_results = load_audit_results(results_dir, verbose)
    if not audit_results and verbose:
        logger.warning("No audit results found")
    
    # 데이터 결합
    merged_df = merge_contract_audit(contract_df, audit_results, verbose)
    
    if merged_df.empty:
        logger.error("No combined data to generate report.")
        return
    
    # CSV로 저장 (요청된 열 순서: project_id,department,project_name,Status,Contractor,timestamp,...)
    columns_order = ['project_id', 'department', 'project_name', 'Status', 'Contractor', 'timestamp']
    doc_columns = [f'{doc_type}_exists' for doc_type in DOCUMENT_TYPES.keys()] + [f'{doc_type}_count' for doc_type in DOCUMENT_TYPES.keys()]
    merged_df = merged_df[columns_order + doc_columns]
    
    # 출력 파일 이름에서 시간 제거, 날짜만 사용
    output_date = datetime.now().strftime("%Y%m%d")
    output_filename = f'combined_report_{output_date}.csv'
    final_output_path = os.path.join(os.path.dirname(output_path), output_filename)
    
    os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
    merged_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
    
    logger.info(f"Combined report generated: {final_output_path} ({len(merged_df)} projects)")
    logger.info("\nDocument statistics:")
    doc_types = list(DOCUMENT_TYPES.keys())
    for doc_type in doc_types:
        exists_count = merged_df[f'{doc_type}_exists'].sum()
        total_count = merged_df[f'{doc_type}_count'].sum()
        logger.info(f"- {doc_type}: {exists_count} projects have documents (total {total_count} files)")
    
    logger.info("\n=== Combined Report Generation Completed ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate combined report of contract status and audit results")
    parser.add_argument('--results-dir', type=str, default=os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results'), help="Directory of audit results JSON files")
    parser.add_argument('--output', type=str, default=os.path.join(os.path.dirname(STATIC_DATA_PATH), 'report', 'combined_report'), help="Output CSV file path prefix (date will be appended)")
    parser.add_argument('--verbose', action='store_true', help="Enable detailed debug output")
    args = parser.parse_args()
    
    generate_combined_report(args.results_dir, args.output, args.verbose)
    
# python generate_summary.py