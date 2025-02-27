# my-flask-app/export_report.py

import os
import json
import pandas as pd
from glob import glob
from datetime import datetime
import argparse
from config import (
    STATIC_DATA_PATH, 
    DOCUMENT_TYPES, 
    PROJECT_LIST_CSV, 
    DEPART_LIST_PATH
)

def load_audit_files(department_code, verbose=False):
    """부서별 감사 JSON 파일 로드"""
    audit_path = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results')
    pattern = f"{audit_path}/audit_{department_code}_*.json"
    audit_files = glob(pattern)
    
    if not audit_files and verbose:
        print(f"[WARNING] No audit files found for {department_code}")
    
    results = []
    for file_path in audit_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'error' not in data:  # 오류 결과 제외
                    results.append(data)
                elif verbose:
                    print(f"[SKIP] {file_path}: Audit contains error")
        except Exception as e:
            print(f"[ERROR] Failed to load {file_path}: {str(e)}")
    
    return results

def create_department_report(department_code, verbose=False):
    """부서별 보고서 CSV 생성"""
    audit_data = load_audit_files(department_code, verbose)
    if not audit_data:
        print(f"No valid audit data found for department {department_code}")
        return None
    
    # 데이터 준비
    rows = []
    for audit in audit_data:
        row = {
            'project_id': audit['project_id'],
            'project_name': audit['project_name'],
            'project_path': audit['project_path'],
            'last_updated': audit.get('last_updated', ''),
            'department': audit.get('department', department_code)
        }
        
        # 모든 문서 유형을 기본값으로 초기화
        for doc_type in DOCUMENT_TYPES:
            row[f'{doc_type}_exists'] = False
            row[f'{doc_type}_count'] = 0
        
        # 감사 결과로 문서 상태 업데이트
        for doc_type, doc_info in audit['documents'].items():
            row[f'{doc_type}_exists'] = doc_info['exists']
            row[f'{doc_type}_count'] = len(doc_info['details']) if doc_info['exists'] else 0
        
        rows.append(row)
    
    # DataFrame 생성 및 정렬
    df = pd.DataFrame(rows)
    df = df.sort_values(['project_id', 'last_updated'], ascending=[True, False])
    
    # 중복 프로젝트 제거 (가장 최근 감사 결과만 유지)
    df = df.drop_duplicates(subset=['project_id'], keep='first')
    
    # 보고서 저장
    report_dir = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'report')
    os.makedirs(report_dir, exist_ok=True)
    output_path = os.path.join(report_dir, f"report_{department_code}.csv")
    df.to_csv(output_path, index=False, encoding='utf-8')
    
    if verbose:
        print(f"[DEBUG] Generated columns: {df.columns.tolist()}")
        print(f"[DEBUG] Total projects: {len(df)}")
        print(f"[DEBUG] Documents found: {df.filter(like='_exists').sum().to_dict()}")
    
    print(f"Report generated: {output_path} ({len(df)} projects)")
    
    return df

def get_department_codes():
    """부서 코드 목록 가져오기"""
    try:
        if os.path.exists(DEPART_LIST_PATH):
            df = pd.read_csv(DEPART_LIST_PATH)
            return [str(code).zfill(5) for code in df['department_code'].unique()]
        elif os.path.exists(PROJECT_LIST_CSV):
            df = pd.read_csv(PROJECT_LIST_CSV)
            return [str(code).zfill(5) for code in df['department_code'].unique()]
        else:
            raise FileNotFoundError("Neither depart_list.csv nor project_list.csv found")
    except Exception as e:
        print(f"[ERROR] Failed to load department codes: {str(e)}")
        return []

def main(dept_code=None, verbose=False):
    """보고서 생성 메인 함수"""
    start_time = datetime.now()
    print("=== Starting Report Generation ===")
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    department_codes = [dept_code] if dept_code else get_department_codes()
    
    if not department_codes:
        print("[ERROR] No departments to process")
        return
    
    total_projects = 0
    for dept_code in department_codes:
        print(f"\nProcessing department: {dept_code}")
        df = create_department_report(dept_code, verbose)
        if df is not None:
            total_projects += len(df)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n=== Report Generation Summary ===")
    print(f"Departments processed: {len(department_codes)}")
    print(f"Total projects: {total_projects}")
    print(f"Duration: {duration:.2f} seconds")
    print("================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export department-wise project audit reports")
    parser.add_argument('--dept', type=str, help="Specific department code (e.g., 01020)")
    parser.add_argument('--verbose', action='store_true', help="Enable detailed debug output")
    args = parser.parse_args()
    
    main(dept_code=args.dept, verbose=args.verbose)

# python export_report.py