# my_flask_app/generate_summary.py

import os
import json
import pandas as pd
import re
from glob import glob
from datetime import datetime
import logging
import ast

from config import STATIC_DATA_PATH, PROJECT_LIST_CSV, NETWORK_BASE_PATH
from config_assets import DOCUMENT_TYPES
import argparse

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def load_audit_results(results_dir, verbose=False):
    """감사 결과 JSON 파일 로드"""
    audit_targets_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
    df_targets = pd.read_csv(audit_targets_path, encoding='utf-8-sig')
    
    logger.info(f"\n=== audit_targets_new.csv 현황 ===")
    logger.info(f"전체 라인 수: {len(df_targets)}개")
    logger.info(f"감사 대상 프로젝트: {df_targets['ProjectID'].nunique()}개")
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
    for file_path in audit_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    data = data[0]
                
                if 'error' not in data:
                    project_id = str(data['project_id'])  # JSON의 project_id를 그대로 사용
                    # ProjectID가 audit_targets_new.csv에 있는지 확인
                    if project_id in df_targets['ProjectID'].values:
                        processed_documents = {}
                        for doc_type, doc_info in data['documents'].items():
                            processed_details = []
                            if doc_info.get('exists', False) and 'details' in doc_info:
                                for detail in doc_info['details']:
                                    try:
                                        if isinstance(detail.get('name'), str) and detail.get('name').startswith('{'):
                                            name_dict = ast.literal_eval(detail['name'])
                                            path_dict = ast.literal_eval(detail['path'])
                                            processed_details.append({
                                                'name': name_dict.get('name', ''),
                                                'path': path_dict.get('full_path', path_dict.get('path', ''))
                                            })
                                        else:
                                            processed_details.append(detail)
                                    except Exception as e:
                                        logger.warning(f"Failed to parse detail in {doc_type}: {str(e)}")
                                        processed_details.append(detail)
                            
                            processed_documents[doc_type] = {
                                'exists': doc_info.get('exists', False),
                                'details': processed_details
                            }
                        results[project_id] = processed_documents
                    else:
                        logger.debug(f"ProjectID {project_id} not found in audit_targets_new.csv, skipping")
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {str(e)}")
    return results

def merge_audit_targets_with_results(audit_results, verbose=False):
    """audit_targets_new.csv에 감사 결과를 결합"""
    doc_types = list(DOCUMENT_TYPES.keys())
    
    audit_targets_path = os.path.join(STATIC_DATA_PATH, 'audit_targets_new.csv')
    df_targets = pd.read_csv(audit_targets_path, encoding='utf-8-sig')
    
    logger.info(f"\n=== 데이터 결합 처리 현황 ===")
    logger.info(f"감사 결과 건수: {len(audit_results)}개")
    logger.info(f"감사 대상 프로젝트 수: {len(df_targets)}개")
    
    # 감사 결과 필드 초기화
    for doc_type in doc_types:
        df_targets[f'{doc_type}_exists'] = 0
        df_targets[f'{doc_type}_count'] = 0
    
    audited_count = 0
    not_audited_count = 0
    
    # 감사 결과 매핑
    for project_id, documents in audit_results.items():
        mask = df_targets['ProjectID'] == project_id
        if mask.any():
            audited_count += 1
            for doc_type, doc_info in documents.items():
                df_targets.loc[mask, f'{doc_type}_exists'] = 1 if doc_info['exists'] else 0
                df_targets.loc[mask, f'{doc_type}_count'] = len(doc_info['details']) if doc_info['exists'] else 0
        else:
            logger.debug(f"ProjectID {project_id} not in audit targets, skipping")
    
    not_audited_count = len(df_targets) - audited_count
    
    logger.info(f"\n감사 시행: {audited_count}개")
    logger.info(f"감사 미시행: {not_audited_count}개")
    logger.info(f"전체 프로젝트: {len(df_targets)}개")
    
    if verbose:
        logger.info(f"최종 결합된 데이터: {len(df_targets)}개")
    
    return df_targets

async def generate_combined_report(results_dir, output_path, verbose=False):
    """감사 대상과 결과를 결합한 보고서 생성"""
    try:
        logger.info("\n=== 통합 보고서 생성 시작 ===")
        logger.info(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        audit_results = load_audit_results(results_dir, verbose)
        if not audit_results:
            logger.error("감사 결과를 찾을 수 없습니다.")
            return None
        else:
            logger.info(f"로드된 감사 결과 수: {len(audit_results)}개")
        
        merged_df = merge_audit_targets_with_results(audit_results, verbose)
        
        if merged_df.empty:
            logger.error("결합할 데이터가 없습니다.")
            return None
        
        # 열 순서 조정
        base_columns = ['ProjectID', 'ProjectName', 'Depart', 'Status', 'Contractor', 
                        'ProjectID_numeric', 'Depart_ProjectID', 'search_folder']
        doc_columns = [f'{doc_type}_exists' for doc_type in DOCUMENT_TYPES.keys()] + \
                      [f'{doc_type}_count' for doc_type in DOCUMENT_TYPES.keys()]
        merged_df = merged_df[base_columns + doc_columns]
        
        output_date = datetime.now().strftime("%Y%m%d")
        # output_filename = f'combined_report_{output_date}.csv'
        output_filename = f'combined_report.csv'

        final_output_path = os.path.join(os.path.dirname(output_path), output_filename)
        
        os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
        merged_df.to_csv(final_output_path, index=False, encoding='utf-8-sig')
        
        logger.info(f"\n=== 통합 보고서 생성 완료 ===")
        logger.info(f"생성된 보고서: {final_output_path}")
        logger.info(f"처리된 총 프로젝트 수: {len(merged_df)}개")
        
        total_projects = len(merged_df)
        success_rate = (len(audit_results) / total_projects) * 100 if total_projects > 0 else 0
        logger.info(f"\n처리 성공률: {success_rate:.1f}% ({len(audit_results)}/{total_projects})")
        logger.info(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*50)
        
        return final_output_path
    except Exception as e:
        logger.error(f"통합 보고서 생성 중 오류 발생: {str(e)}")
        return None

async def main(results_dir, output_path, verbose=False):
    return await generate_combined_report(results_dir, output_path, verbose)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate combined report of audit targets and results")
    parser.add_argument('--results-dir', type=str, default=os.path.join(os.path.dirname(STATIC_DATA_PATH), 'results'), help="Directory of audit results JSON files")
    parser.add_argument('--output', type=str, default=os.path.join(os.path.dirname(STATIC_DATA_PATH), 'report', 'combined_report'), help="Output CSV file path prefix (date will be appended)")
    parser.add_argument('--verbose', action='store_true', help="Enable detailed debug output")
    args = parser.parse_args()
    
    import asyncio
    asyncio.run(main(args.results_dir, args.output, args.verbose))
    
# python generate_summary.py