## /my_flask_app/Get_data.py
# 네트워크 드라이브에서 프로젝트 목록 생성

import os
import argparse
import re
import csv
import pandas as pd
from config_assets import SCAN_CONFIG, FORCE_SCAN_CONFIG
from config import PROJECT_LIST_CSV, STATIC_DATA_PATH, NETWORK_BASE_PATH, DEPART_LIST_PATH

# 경로 설정
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
STATIC_DATA_PATH = os.path.join(ROOT_DIR, 'static', 'data')

# 정규 표현식 미리 컴파일 - 1990~2029년 패턴만 허용
YEAR_PATTERN = re.compile(r'(?:199|20[0-2])\d')
PROJECT_ID_PATTERN = re.compile(r'(?:^|[^\d])((?:199|20[0-2])\d\d{4})(?:[^\d]|$)')
PROJECT_YEAR_SEQ = re.compile(r'((?:199|20[0-2])\d)[^0-9]*(\d{2,3})(?:[^\d]|$)')

def check_network_drive(drive_path):
    try:
        if not os.path.exists(drive_path):
            print(f"Network drive not found: {drive_path}")
            return False
        os.listdir(drive_path)
        return True
    except Exception as e:
        print(f"Network drive check failed: {str(e)}")
        return False

def should_scan_deeper(folder_name, verbose=False):
    # 프로젝트 폴더의 하위 폴더는 항상 스캔
    parent_folder = os.path.basename(os.path.dirname(folder_name))
    if is_project_folder(parent_folder):
        return True
        
    # 키워드 기반 스캔
    for keyword in FORCE_SCAN_CONFIG['deep_scan_keywords']:
        if keyword.lower() in folder_name.lower():
            if verbose:
                print(f"[SCAN] Found keyword '{keyword}' in: {folder_name}")
            return True
    return False

def is_project_folder(folder_name, verbose=False):
    # 연도 패턴이 있는 폴더만 프로젝트로 인식
    if YEAR_PATTERN.search(folder_name):
        if verbose:
            print(f"[PROJECT] Found project folder: {folder_name}")
        return True
    return False

def extract_project_id(folder_name, verbose=False):
    # 날짜 형식 제외 (YYYY.MM.DD 또는 YYYY-MM-DD)
    if re.match(r'\d{4}[-.]\d{2}[-.]\d{2}', folder_name):
        if verbose:
            print(f"[SKIP] Date format folder: {folder_name}")
        return None
    
    # 8자리 또는 7자리 숫자 패턴
    if match := PROJECT_ID_PATTERN.search(folder_name):
        project_id = match.group(1)
        if len(project_id) == 7:  # 7자리인 경우 8자리로 변환
            project_id = f"{project_id[:4]}0{project_id[4:]}"
        if verbose:
            print(f"[ID] Project ID: {project_id}")
        return project_id
    
    # 연도+일련번호 패턴
    if match := PROJECT_YEAR_SEQ.search(folder_name):
        year, seq = match.groups()
        project_id = f"{year}0{seq.zfill(3)}"
        if verbose:
            print(f"[ID] Project ID: {project_id}")
        return project_id
    
    # 연도만 있는 경우
    if match := YEAR_PATTERN.search(folder_name):
        year = match.group(0)
        project_id = f"{year}0000"
        if verbose:
            print(f"[ID] Project ID (year only): {project_id}")
        return project_id
    
    return None

def scan_directory(path, current_depth=0, verbose=False, scanned_folders=None):
    if current_depth > SCAN_CONFIG['max_category_depth']:
        return []
    
    if scanned_folders is None:
        scanned_folders = set()
    
    if path in scanned_folders:
        return []
    
    scanned_folders.add(path)
    projects = []
    
    try:
        items = os.listdir(path)
        for item in items:
            item_path = os.path.join(path, item)
            if not os.path.isdir(item_path):
                continue
            
            # 연도 기반 프로젝트 폴더 확인
            if is_project_folder(item, verbose):
                if project_id := extract_project_id(item, verbose):
                    projects.append({
                        'name': item,
                        'path': item_path,
                        'depth': current_depth,
                        'project_id': project_id
                    })
            
            # 키워드 기반 깊이 탐색 또는 프로젝트 하위 폴더 스캔
            if should_scan_deeper(item, verbose):
                sub_projects = scan_directory(item_path, current_depth + 1, verbose, scanned_folders)
                projects.extend(sub_projects)
                
    except Exception as e:
        if verbose:
            print(f"[ERROR] Scanning directory {path}: {str(e)}")
    
    return projects

def create_project_list(root_path, target_departments=None, force_scan=False, verbose=False):
    print("=== Starting project list creation ===")
    
    if not check_network_drive(root_path):
        raise Exception(f"Cannot access network drive: {root_path}")
    
    os.makedirs(STATIC_DATA_PATH, exist_ok=True)
    
    if not os.path.exists(DEPART_LIST_PATH):
        print(f"Department list not found: {DEPART_LIST_PATH}")
        return
    
    df_dept = pd.read_csv(DEPART_LIST_PATH, dtype={'department_code': str})  # department_code를 문자열로 읽기
    print(f"\nLoaded {len(df_dept)} departments")
    
    all_projects = []
    for _, dept in df_dept.iterrows():
        dept_code = str(dept['department_code']).zfill(5)  # 5자리로 패딩
        dept_name = dept['department_name']
        dept_folder = f"{dept_code}_{dept_name}"
        dept_path = os.path.join(root_path, dept_folder)
        
        if target_departments and dept_code not in target_departments:
            if verbose:
                print(f"\n[SKIP] {dept_folder}")
            continue
        
        print(f"\n[SCAN] {dept_folder}")
        if not os.path.exists(dept_path):
            print(f"- Folder not found: {dept_path}")
            continue
        
        projects = scan_directory(dept_path, verbose=verbose)
        if projects:
            for project in projects:
                relative_path = project['path'].split(':', 1)[1] if ':' in project['path'] else project['path']
                project['path'] = relative_path.lstrip('\\/')
                project['department_code'] = dept_code  # 패딩 적용된 dept_code 사용
                project['department_name'] = dept_name
            all_projects.extend(projects)
            print(f"- Found {len(projects)} projects")
    
    if all_projects:
        structured_data = [
            {
                'project_id': p['project_id'],
                'department_code': p['department_code'],
                'department_name': p['department_name'],
                'project_name': p['name'],
                'original_folder': p['path']
            } for p in all_projects
        ]
        
        df = pd.DataFrame(structured_data)
        df = df.sort_values(['project_id', 'department_code'])
        df.to_csv(PROJECT_LIST_CSV, index=False, encoding='utf-8')
        print(f"\nSaved {len(df)} projects to {PROJECT_LIST_CSV}")
    else:
        print("\nNo projects collected.")
    
    print("\n=== Project list creation completed ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate project list from network drive")
    parser.add_argument('--force', action='store_true', help="Force full scan (currently placeholder)")
    parser.add_argument('--verbose', action='store_true', help="Enable detailed debug output")
    args = parser.parse_args()
    
    TARGET_DEPARTMENTS = [
        "01010",  # 도로
        "01020",  # 공항인프라
        "01030",  # 구조
        "01040",  # 지반
        "01050",  # 교통
        "01060",  # 안전진단
        "02010",  # 도시철도
        "03010",  # 철도
        "03020",  # 철도건설관리
        "04010",  # 도시계획
        "04020",  # 도시설계
        "04030",  # 조경
        "05010",  # 수자원
        "06010",  # 환경
        "07010",  # 상하수도
        "08010",  # 건설사업관리
        "09010",  # 해외영업
        "10010",  # 플랫폼사업실
        "11010",  # 기술지원실
        "99999",  # 준공
    ]
    
    root_path = NETWORK_BASE_PATH
    print(f"\nNetwork drive path: {root_path}")
    create_project_list(root_path, TARGET_DEPARTMENTS, force_scan=args.force, verbose=args.verbose)

# python get_data.py
# python get_data.py --verbose