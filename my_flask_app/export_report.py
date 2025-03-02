# my_flask_app/export_report.py

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
import asyncio

async def load_audit_files(department_code, verbose=False):
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

async def create_department_report(department_code, output_path, verbose=False):
    """부서별 보고서 CSV 생성"""
    audit_data = await load_audit_files(department_code, verbose)
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
    
    # 보고서 저장 (지정된 출력 경로로 저장)
    report_dir = os.path.dirname(output_path)
    os.makedirs(report_dir, exist_ok=True)
    df.to_csv(output_path, index=False, encoding='utf-8')

    # GitHub에 파일 업로드 (존재하는 경우)
    try:
        from git_operations import move_files_to_images_folder
        await move_files_to_images_folder(output_path)
    except Exception as e:
        print(f"[WARNING] Failed to upload report to GitHub: {str(e)}")

    if verbose:
        print(f"[DEBUG] Report saved at: {output_path}")
        print(f"[DEBUG] Total projects: {len(df)}")
        print(f"[DEBUG] Documents found: {df.filter(like='_exists').sum().to_dict()}")
    
    print(f"Report generated: {output_path} ({len(df)} projects)")
    
    return df

async def get_department_codes():
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

async def main(dept_code=None, output_path=None, verbose=False):
    """보고서 생성 메인 함수"""
    start_time = datetime.now()
    print("=== Starting Report Generation ===")
    print(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if not dept_code or not output_path:
        print("[ERROR] Department code and output path are required")
        return
    
    print(f"\nProcessing department: {dept_code}")
    df = await create_department_report(dept_code, output_path, verbose)
    
    if df is not None:
        total_projects = len(df)
    else:
        total_projects = 0
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n=== Report Generation Summary ===")
    print(f"Departments processed: 1")
    print(f"Total projects: {total_projects}")
    print(f"Duration: {duration:.2f} seconds")
    print("================================")

async def generate_summary_report(results, verbose=False):
    """전체 감사 결과에 대한 종합 보고서 생성"""
    try:
        print("\n[DEBUG] === Generating Summary Report ===")
        
        # 결과 파일명 생성
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        summary_filename = f"summary_report_{timestamp}.json"
        report_dir = os.path.join(os.path.dirname(STATIC_DATA_PATH), 'report')
        os.makedirs(report_dir, exist_ok=True)
        summary_path = os.path.join(report_dir, summary_filename)
        
        # 통계 데이터 수집
        summary = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_projects': len(results),
            'successful_audits': sum(1 for r in results if 'error' not in r),
            'failed_audits': sum(1 for r in results if 'error' in r),
            'document_statistics': {
                doc_type: {
                    'found': 0,
                    'missing': 0,
                    'total_files': 0
                } for doc_type in DOCUMENT_TYPES.keys()
            },
            'department_statistics': {},
            'risk_levels': {
                'high': 0,    # 0-40점
                'medium': 0,  # 41-70점
                'low': 0      # 71-100점
            }
        }
        
        # 부서별, 문서별 통계 수집
        for result in results:
            if 'error' not in result:
                dept = result['department']
                if dept not in summary['department_statistics']:
                    summary['department_statistics'][dept] = {
                        'total': 0,
                        'documents_found': 0,
                        'documents_missing': 0,
                        'risk_score': 0
                    }
                
                dept_stats = summary['department_statistics'][dept]
                dept_stats['total'] += 1
                
                # 문서 통계
                missing_docs = []
                for doc_type, info in result['documents'].items():
                    if info['exists']:
                        summary['document_statistics'][doc_type]['found'] += 1
                        summary['document_statistics'][doc_type]['total_files'] += len(info['details'])
                        dept_stats['documents_found'] += 1
                    else:
                        summary['document_statistics'][doc_type]['missing'] += 1
                        dept_stats['documents_missing'] += 1
                        missing_docs.append(doc_type)
                
                # 위험도 점수 계산
                risk_score = calculate_risk_score(missing_docs)
                dept_stats['risk_score'] = (dept_stats['risk_score'] * (dept_stats['total'] - 1) + risk_score) / dept_stats['total']
                
                # 위험도 레벨 분류
                if risk_score <= 40:
                    summary['risk_levels']['high'] += 1
                elif risk_score <= 70:
                    summary['risk_levels']['medium'] += 1
                else:
                    summary['risk_levels']['low'] += 1
        
        # CSV 보고서 생성
        csv_rows = []
        for result in results:
            if 'error' not in result:
                row = {
                    'project_id': result['project_id'],
                    'department': result['department'],
                    'project_name': result['project_name'],
                    'timestamp': result['timestamp']
                }
                
                # 문서 상태 추가
                for doc_type in DOCUMENT_TYPES.keys():
                    info = result['documents'][doc_type]
                    row[f'{doc_type}_exists'] = info['exists']
                    row[f'{doc_type}_count'] = len(info['details']) if info['exists'] else 0
                
                csv_rows.append(row)
        
        if csv_rows:
            df = pd.DataFrame(csv_rows)
            csv_path = os.path.join(report_dir, f'audit_summary_{timestamp}.csv')
            df.to_csv(csv_path, index=False, encoding='utf-8')
            summary['csv_report'] = csv_path
        
        # JSON 저장
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        if verbose:
            print(f"[DEBUG] Generated summary report at: {summary_path}")
            if 'csv_report' in summary:
                print(f"[DEBUG] Generated CSV report at: {summary['csv_report']}")
            print(f"[DEBUG] Total projects processed: {summary['total_projects']}")
            print(f"[DEBUG] Success rate: {(summary['successful_audits']/summary['total_projects']*100):.1f}%")
        
        return summary_path, summary
        
    except Exception as e:
        print(f"[ERROR] Failed to generate summary report: {str(e)}")
        return None, None

def calculate_risk_score(missing_docs):
    """문서 누락에 따른 위험도 점수 계산"""
    base_score = 100
    risk_weights = {
        'contract': 30,    # 계약서
        'specification': 25,  # 과업지시서
        'budget': 20,      # 실행예산
        'completion': 15,   # 준공계
        'evaluation': 10    # 용역수행평가
    }
    
    for doc in missing_docs:
        if doc in risk_weights:
            base_score -= risk_weights[doc]
    
    return max(0, base_score)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export department-wise project audit reports")
    parser.add_argument('--dept', type=str, required=True, help="Specific department code (e.g., 01010)")
    parser.add_argument('--output', type=str, required=True, help="Output CSV file path (e.g., ./report/report_01010.csv)")
    parser.add_argument('--verbose', action='store_true', help="Enable detailed debug output")
    args = parser.parse_args()
    
    print("\n=== Starting Report Generation Test ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 비동기 테스트 실행
    async def run_test():
        try:
            print(f"\nTesting report generation for department: {args.dept}")
            df = await create_department_report(args.dept, args.output, verbose=args.verbose)
            
            if df is not None:
                print(f"\nReport generation successful!")
                print(f"Total projects processed: {len(df)}")
                print("\nDocument statistics:")
                for col in df.columns:
                    if col.endswith('_exists'):
                        doc_type = col.replace('_exists', '')
                        exists_count = df[col].sum()
                        total_count = df[f'{doc_type}_count'].sum()
                        print(f"- {doc_type}: {exists_count} projects have documents (total {total_count} files)")
            else:
                print(f"\nNo data found for department {args.dept}")
                
        except Exception as e:
            print(f"\n[ERROR] Test failed: {str(e)}")
    
    asyncio.run(run_test())
    
    print("\n=== Test Completed ===")

# python export_report.py --dept 01010 --output ./report/report_01010.csv --verbose