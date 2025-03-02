# my_flask_app/generate_summary.py


import os
import json
import pandas as pd
import re
from glob import glob
from datetime import datetime
from config import STATIC_DATA_PATH, CONTRACT_STATUS_CSV
from config_assets import DOCUMENT_TYPES, DEPARTMENT_MAPPING, DEPARTMENT_NAMES
import argparse

def load_contract_data(verbose=False):
    """계약현황 CSV 로드 및 ProjectID 기반으로 검색 가능하도록 변환"""
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
        result_df = result_df[['Depart_ProjectID', 'Depart', 'Status', 'Contractor', 'ProjectName', 'ProjectID']]  # ProjectID 열 유지
        
        if verbose:
            print(f"[DEBUG] Loaded contract data with {len(result_df)} records")
        return result_df  # ProjectID를 열로 유지
    except Exception as e:
        print(f"[ERROR] Failed to load contract data from {CONTRACT_STATUS_CSV}: {str(e)}")
        return pd.DataFrame()

def load_audit_results(results_dir, verbose=False):
    """감사 결과 JSON 파일 로드"""
    pattern = os.path.join(results_dir, 'audit_*.json')
    audit_files = glob(pattern)
    
    if not audit_files and verbose:
        print(f"[WARNING] No audit files found in {results_dir}")
    
    results = {}
    for file_path in audit_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'error' not in data:
                    project_id = re.sub(r'[^0-9]', '', str(data['project_id']))
                    dept_code = data['department'].split('_')[0] if '_' in data['department'] else '99999'
                    business_code = None
                    # JSON 파일 이름에서 부서 코드와 사업코드를 추출 (예: audit_06010_20240178.json)
                    file_name = os.path.basename(file_path).replace('audit_', '').replace('.json', '')
                    if '_' in file_name:
                        dept_code_from_file, proj_id = file_name.split('_', 1)
                        if dept_code_from_file in DEPARTMENT_NAMES or dept_code_from_file in DEPARTMENT_MAPPING.values():
                            dept_code = dept_code_from_file
                            # 계약현황 데이터에서 BusinessCode를 찾기 위해 ProjectID 사용
                            business_code = find_business_code_from_project_id(proj_id, contract_df)  # contract_df를 글로벌로 전달 필요
                    if business_code:
                        depart_project_id = f"{dept_code}_{business_code}"
                    else:
                        depart_project_id = f"{dept_code}_{project_id}"
                    results[project_id] = {
                        'documents': data['documents'],
                        'depart_project_id': depart_project_id
                    }
                elif verbose:
                    print(f"[SKIP] {file_path}: Audit contains error")
        except Exception as e:
            print(f"[ERROR] Failed to load {file_path}: {str(e)}")
    return results

def find_business_code_from_project_id(project_id, contract_df):
    """ProjectID(숫자)로 계약현황 데이터에서 BusinessCode(알파벳 포함) 검색"""
    try:
        # contract_df에서 ProjectID 열로 검색
        if 'ProjectID' in contract_df.columns:  # ProjectID 열 존재 확인
            match = contract_df['ProjectID'] == str(project_id)
            if match.any():
                return contract_df.loc[match, 'BusinessCode'].iloc[0]  # BusinessCode 반환
        return None
    except Exception as e:
        print(f"[ERROR] Failed to find BusinessCode for ProjectID {project_id}: {str(e)}")
        return None

def merge_contract_audit(contract_df, audit_results, verbose=False):
    """계약현황과 감사 결과를 결합"""
    doc_types = list(DOCUMENT_TYPES.keys())  # DOCUMENT_TYPES 순서 유지
    
    # 계약현황 데이터에 감사 결과 추가
    merged_data = []
    for project_id, audit_data in audit_results.items():
        # 계약현황 데이터에서 ProjectID로 검색
        if str(project_id) in contract_df['ProjectID'].astype(str).values:  # ProjectID를 문자열로 변환하여 검색
            row = contract_df[contract_df['ProjectID'] == str(project_id)].iloc[0]
            audit_docs = audit_data['documents']
            depart_project_id = audit_data['depart_project_id']
            
            merged_row = {
                'Depart_ProjectID': depart_project_id,
                'Depart': row['Depart'],
                'Status': row['Status'],
                'Contractor': row['Contractor'],
                'ProjectName': row['ProjectName']
            }
            
            for doc_type in doc_types:
                merged_row[f'{doc_type}_exists'] = 1 if audit_docs.get(doc_type, []) else 0
                merged_row[f'{doc_type}_count'] = len(audit_docs.get(doc_type, [])) if merged_row[f'{doc_type}_exists'] else 0
            
            merged_data.append(merged_row)
    
    if not merged_data:
        print("No audit results found to merge with contract data.")
        return pd.DataFrame()
    
    # DataFrame 생성 및 정렬
    merged_df = pd.DataFrame(merged_data)
    merged_df = merged_df.sort_values(['Depart', 'Depart_ProjectID'], ascending=[True, True])
    
    if verbose:
        print(f"[DEBUG] Merged data with {len(merged_df)} records")
    return merged_df

def generate_combined_report(results_dir, output_path, verbose=False):
    """계약현황과 감사 결과를 결합한 보고서 생성"""
    global contract_df  # contract_df를 전역 변수로 설정해 find_business_code_from_project_id에서 사용
    print("=== Starting Combined Report Generation ===")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 계약현황 데이터 로드
    contract_df = load_contract_data(verbose)
    if contract_df.empty:
        print("No contract data found. Exiting.")
        return
    
    # 감사 결과 로드
    audit_results = load_audit_results(results_dir, verbose)
    if not audit_results and verbose:
        print("[WARNING] No audit results found")
    
    # 데이터 결합
    merged_df = merge_contract_audit(contract_df, audit_results, verbose)
    
    if merged_df.empty:
        print("No combined data to generate report.")
        return
    
    # CSV로 저장
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    merged_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    print(f"Combined report generated: {output_path} ({len(merged_df)} projects)")
    print("\nDocument statistics:")
    doc_types = list(DOCUMENT_TYPES.keys())
    for doc_type in doc_types:
        exists_count = merged_df[f'{doc_type}_exists'].sum()
        total_count = merged_df[f'{doc_type}_count'].sum()
        print(f"- {doc_type}: {exists_count} projects have documents (total {total_count} files)")
    
    print("\n=== Combined Report Generation Completed ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate combined report of contract status and audit results")
    parser.add_argument('--results-dir', type=str, default=os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results'), help="Directory of audit results JSON files")
    parser.add_argument('--output', type=str, default=os.path.join(os.path.dirname(STATIC_DATA_PATH), 'report', f'combined_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'), help="Output CSV file path")
    parser.add_argument('--verbose', action='store_true', help="Enable detailed debug output")
    args = parser.parse_args()
    
    generate_combined_report(args.results_dir, args.output, args.verbose)
    
# python generate_summary.py
    

    
# python generate_summary.py