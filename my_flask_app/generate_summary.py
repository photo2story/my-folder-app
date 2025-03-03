# my_flask_app/generate_summary.py

import os
import json
import pandas as pd
import re
from glob import glob
from datetime import datetime
import logging  # logging 모듈 추가

from config import STATIC_DATA_PATH, CONTRACT_STATUS_CSV, PROJECT_LIST_CSV, NETWORK_BASE_PATH
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

def get_status_contractor_from_targets(project_id, dept_code, df_targets=None):
    """audit_targets_new.csv에서 Status와 Contractor 가져오기"""
    if df_targets is None:
        audit_targets_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
        if os.path.exists(audit_targets_path):
            try:
                df_targets = pd.read_csv(audit_targets_path, encoding='utf-8-sig')
                # Depart_ProjectID에서 ProjectID 추출 (숫자만)
                df_targets['ProjectID'] = df_targets['Depart_ProjectID'].apply(lambda x: re.sub(r'[^0-9]', '', str(x).split('_')[-1]))
            except Exception as e:
                logger.error(f"Failed to load audit_targets_new.csv: {str(e)}")
                return None, None
    
    if df_targets is not None:
        numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
        target_match = df_targets[df_targets['ProjectID'] == numeric_project_id]
        if len(target_match) > 0:
            row = target_match.iloc[0]
            status = row.get('Status', 'Unknown')
            contractor = row.get('Contractor', 'Unknown')
            logger.debug(f"ProjectID {numeric_project_id} 매칭 성공 - Status: {status}, Contractor: {contractor}")
            return status, contractor
        else:
            logger.debug(f"ProjectID {numeric_project_id} 매칭 실패")
    return None, None

def get_status_contractor_from_contract(project_id, contract_df):
    """contract_status.csv에서 Status와 Contractor 가져오기 (백업)"""
    try:
        if 'ProjectID' in contract_df.columns:
            numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
            match = contract_df['ProjectID'] == numeric_project_id
            if match.any():
                row = contract_df.loc[match].iloc[0]
                status = str(row['Status']) if pd.notna(row['Status']) else 'Unknown'
                contractor = str(row['Contractor']) if pd.notna(row['Contractor']) else 'Unknown'
                return status, contractor
    except Exception as e:
        logger.error(f"Failed to load status and contractor from contract_status.csv for project_id {project_id}: {str(e)}")
    return 'Unknown', 'Unknown'

def load_audit_results(results_dir, verbose=False):
    """감사 결과 JSON 파일 로드"""
    # 먼저 audit_targets_new.csv 파일의 데이터 수 확인
    audit_targets_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
    df_targets = pd.read_csv(audit_targets_path, encoding='utf-8-sig')
    
    # Depart_ProjectID에서 ProjectID 추출 (숫자만)
    df_targets['ProjectID'] = df_targets['Depart_ProjectID'].apply(lambda x: re.sub(r'[^0-9]', '', str(x).split('_')[-1]))
    
    # 감사 대상 데이터 현황 로깅
    logger.info(f"\n=== audit_targets_new.csv 현황 ===")
    logger.info(f"전체 라인 수: {len(df_targets)}개")
    logger.info(f"감사 대상 프로젝트: {df_targets['ProjectID'].nunique()}개")
    
    # Status 값 분포 확인
    status_counts = df_targets['Status'].value_counts()
    logger.info("\nStatus 분포:")
    for status, count in status_counts.items():
        logger.info(f"- {status}: {count}개")
    logger.info("="*50)
    
    pattern = os.path.join(results_dir, 'audit_*.json')
    audit_files = glob(pattern)
    
    if not audit_files and verbose:
        logger.warning(f"No audit files found in {results_dir}")
    
    results = {}
    audit_map = {}  # audit_*.json 파일과 project_id 매핑
    for file_path in audit_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'error' not in data:
                    project_id = re.sub(r'[^0-9]', '', str(data['project_id']))
                    dept_code = data['department'].split('_')[0] if '_' in data['department'] else '99999'
                    
                    # audit_targets_new.csv에서 Status와 Contractor 가져오기 (기본 소스)
                    status, contractor = get_status_contractor_from_targets(project_id, dept_code, df_targets)
                    if status is None or contractor is None:
                        # contract_status.csv에서 백업으로 가져오기
                        status, contractor = get_status_contractor_from_contract(project_id, contract_df)
                    
                    depart_project_id = f"{project_id}_{dept_code}"
                    results[project_id] = {
                        'documents': data['documents'],
                        'depart_project_id': depart_project_id,
                        'status': status,
                        'contractor': contractor
                    }
                    audit_map[project_id] = file_path  # 매핑 저장
                elif verbose:
                    logger.debug(f"SKIP {file_path}: Audit contains error")
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {str(e)}")
    return results, audit_map

def check_project_path(project_id, department_code, verbose=False):
    """프로젝트 경로 존재 여부 확인"""
    project_list_path = PROJECT_LIST_CSV
    if not os.path.exists(project_list_path):
        logger.error(f"Project list file not found: {project_list_path}")
        return False, "No directory (Project list file missing)", None

    try:
        df_project = pd.read_csv(project_list_path, dtype={'department_code': str, 'project_id': str})
        numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
        project = df_project[df_project['project_id'] == numeric_project_id]
        if len(project) == 0:
            return False, f"No directory (Project ID {numeric_project_id} not found in project list for any department)", None
        
        if department_code:
            department_code = str(department_code).zfill(5)
            project = project[project['department_code'].str.zfill(5) == department_code]
            if len(project) == 0:
                return False, f"No directory (Project ID {numeric_project_id} not found for department {department_code})", None
        
        folder_path = os.path.join(NETWORK_BASE_PATH, str(project.iloc[0]['original_folder']))
        if not os.path.exists(folder_path):
            return False, f"No directory (Project folder not found: {folder_path})", None
        
        return True, folder_path, folder_path
    except Exception as e:
        logger.error(f"Error checking project path for Project ID {project_id}: {str(e)}")
        return False, f"No directory (Error checking path: {str(e)})", None

def merge_contract_audit(contract_df, audit_results, audit_map, verbose=False):
    """계약현황과 감사 결과를 결합"""
    doc_types = list(DOCUMENT_TYPES.keys())
    
    # 처리 현황 로깅 추가
    logger.info("\n=== 데이터 결합 처리 현황 ===")
    logger.info(f"감사 결과 건수: {len(audit_results)}개")
    logger.info(f"계약 데이터 건수: {len(contract_df) if not contract_df.empty else 0}개")
    
    # audit_targets_new.csv에서 모든 프로젝트 로드
    audit_targets_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
    df_targets = pd.read_csv(audit_targets_path, encoding='utf-8-sig')
    # Depart_ProjectID에서 ProjectID 추출 (숫자만)
    df_targets['ProjectID'] = df_targets['Depart_ProjectID'].apply(lambda x: re.sub(r'[^0-9]', '', str(x).split('_')[-1]))
    all_projects = df_targets[['ProjectID', 'Depart', 'Status', 'ProjectName']].drop_duplicates()

    merged_data = []
    for _, row in all_projects.iterrows():
        project_id = row['ProjectID']
        dept_code = next((k for k, v in DEPARTMENT_NAMES.items() if v == row['Depart']), '99999')
        status = row['Status']
        project_name = row['ProjectName']
        
        # audit_results에서 프로젝트 확인
        numeric_project_id = re.sub(r'[^0-9]', '', str(project_id))
        audit_data = audit_results.get(numeric_project_id)
        exists, remark, folder_path = check_project_path(project_id, dept_code, verbose)
        
        merged_row = {
            'project_id': numeric_project_id,
            'department_code': dept_code,
            'department': f"{dept_code}_{row['Depart']}",
            'project_name': project_name,
            'Status': audit_data['status'] if audit_data else (status if pd.notna(status) else 'Unknown'),
            'Contractor': audit_data['contractor'] if audit_data else 'Unknown',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'remark': folder_path if exists else remark
        }
        
        for doc_type in doc_types:
            if audit_data and audit_data['documents'].get(doc_type, {}).get('exists', False):
                merged_row[f'{doc_type}_exists'] = 1
                merged_row[f'{doc_type}_count'] = len(audit_data['documents'].get(doc_type, {}).get('details', []))
            else:
                merged_row[f'{doc_type}_exists'] = 0
                merged_row[f'{doc_type}_count'] = 0
        
        merged_data.append(merged_row)

    # DataFrame 생성 및 정렬
    merged_df = pd.DataFrame(merged_data)
    merged_df = merged_df.sort_values(['department', 'project_id'], ascending=[True, True])
    
    # 처리 현황 로깅
    processed_count = len(merged_df[merged_df['remark'].str.startswith('Z:')])  # 폴더가 있는 프로젝트
    unprocessed_count = len(merged_df[~merged_df['remark'].str.startswith('Z:')])  # 폴더가 없는 프로젝트
    logger.info(f"\n처리된 프로젝트: {processed_count}개 (폴더 존재)")
    logger.info(f"처리되지 않은 프로젝트: {unprocessed_count}개 (폴더 없음)")
    
    if verbose:
        logger.info(f"최종 결합된 데이터: {len(merged_df)}개 (처리된 프로젝트: {processed_count}, 처리되지 않은 프로젝트: {unprocessed_count})")

    return merged_df

def generate_combined_report(results_dir, output_path, verbose=False):
    """계약현황과 감사 결과를 결합한 보고서 생성"""
    global contract_df  # contract_df를 전역 변수로 설정
    logger.info("\n=== 통합 보고서 생성 시작 ===")
    logger.info(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 계약현황 데이터 로드 (백업으로 사용)
    contract_df = load_contract_data(verbose)
    if contract_df.empty and verbose:
        logger.warning("계약 데이터를 찾을 수 없습니다. audit_targets_new.csv를 기본 소스로 사용합니다.")
    
    # 감사 결과 로드
    audit_results, audit_map = load_audit_results(results_dir, verbose)
    if not audit_results and verbose:
        logger.warning("감사 결과를 찾을 수 없습니다.")
    else:
        logger.info(f"로드된 감사 결과 수: {len(audit_results)}개")
    
    # 데이터 결합
    merged_df = merge_contract_audit(contract_df, audit_results, audit_map, verbose)
    
    if merged_df.empty:
        logger.error("결합할 데이터가 없습니다.")
        return
    
    # CSV로 저장
    columns_order = ['project_id', 'department_code', 'department', 'project_name', 'Status', 'Contractor', 'timestamp', 'remark']
    doc_columns = [f'{doc_type}_exists' for doc_type in DOCUMENT_TYPES.keys()] + [f'{doc_type}_count' for doc_type in DOCUMENT_TYPES.keys()]
    merged_df = merged_df[columns_order + doc_columns]
    
    output_date = datetime.now().strftime("%Y%m%d")
    output_filename = f'combined_report_{output_date}.csv'
    final_output_path = os.path.join(os.path.dirname(output_path), output_filename)
    
    os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
    merged_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
    
    logger.info(f"\n=== 통합 보고서 생성 완료 ===")
    logger.info(f"생성된 보고서: {final_output_path}")
    logger.info(f"처리된 총 프로젝트 수: {len(merged_df)}개 (처리된 프로젝트: {merged_df['remark'].str.startswith('Z:').sum()}, 처리되지 않은 프로젝트: {len(merged_df) - merged_df['remark'].str.startswith('Z:').sum()})")
    logger.info("\n문서 통계 (처리된 프로젝트 기준):")
    doc_types = list(DOCUMENT_TYPES.keys())
    for doc_type in doc_types:
        exists_count = merged_df[merged_df['remark'].str.startswith('Z:')][f'{doc_type}_exists'].sum()
        total_count = merged_df[merged_df['remark'].str.startswith('Z:')][f'{doc_type}_count'].sum()
        logger.info(f"- {doc_type}: {exists_count}개 프로젝트에서 발견 (총 {total_count}개 파일)")
    
    # 성공률 계산 및 출력
    total_projects = len(pd.read_csv(os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv'), encoding='utf-8-sig'))
    success_rate = (merged_df['remark'].str.startswith('Z:').sum() / total_projects) * 100 if total_projects > 0 else 0
    logger.info(f"\n처리 성공률: {success_rate:.1f}% ({merged_df['remark'].str.startswith('Z:').sum()}/{total_projects})")
    logger.info(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate combined report of contract status and audit results")
    parser.add_argument('--results-dir', type=str, default=os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results'), help="Directory of audit results JSON files")
    parser.add_argument('--output', type=str, default=os.path.join(os.path.dirname(STATIC_DATA_PATH), 'report', 'combined_report'), help="Output CSV file path prefix (date will be appended)")
    parser.add_argument('--verbose', action='store_true', help="Enable detailed debug output")
    args = parser.parse_args()
    
    generate_combined_report(args.results_dir, args.output, args.verbose)
    
# python generate_summary.py