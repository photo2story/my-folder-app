## /my-flask-app/get_data.py

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

# 정규 표현식 미리 컴파일
YEAR_PATTERN = re.compile(r'(?:19[9]|20[0-2])\d')
EIGHT_DIGIT_PATTERN = re.compile(r'(?:^|[^\d])(\d{8})(?:[^\d]|$)')
SEVEN_DIGIT_PATTERN = re.compile(r'(?:^|[^\d])(\d{7})(?:[^\d]|$)')
SPLIT_PATTERN = re.compile(r'((?:19[9]|20[0-2])\d)[^0-9]*(\d{2,3})(?:[^\d]|$)')

def check_network_drive(drive_path):
    try:
        if not os.path.exists(drive_path):
            print(f"[ERROR] Network drive not found: {drive_path}")
            return False
        os.listdir(drive_path)
        print(f"[DEBUG] Network drive accessible: {drive_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Network drive check failed: {str(e)}")
        return False

def should_scan_deeper(folder_name):
    for keyword in FORCE_SCAN_CONFIG['deep_scan_keywords']:
        if keyword in folder_name:
            return True
    return False

def is_project_folder(folder_name):
    return bool(YEAR_PATTERN.search(folder_name))

def extract_project_id(folder_name):
    if match := EIGHT_DIGIT_PATTERN.search(folder_name):
        return match.group(1)
    if match := SEVEN_DIGIT_PATTERN.search(folder_name):
        number = match.group(1)
        return f"{number[:4]}0{number[4:].zfill(3)}"
    if match := SPLIT_PATTERN.search(folder_name):
        year, seq = match.groups()
        return f"{year}0{seq.zfill(3)}"
    if match := YEAR_PATTERN.search(folder_name):
        return f"{match.group(0)}nnnn"
    return None

def scan_directory(path, current_depth=0, verbose=False):
    if current_depth > SCAN_CONFIG['max_category_depth']:
        return []
    
    projects = []
    try:
        items = os.listdir(path)
        for item in items:
            item_path = os.path.join(path, item)
            if not os.path.isdir(item_path):
                continue
            
            if verbose:
                print(f"[DEBUG] Checking folder: {item}")
            
            if is_project_folder(item):
                project_id = extract_project_id(item)
                if project_id:
                    if verbose:
                        print(f"[DEBUG] Found project: {item} (ID: {project_id})")
                    projects.append({
                        'name': item,
                        'path': item_path,
                        'depth': current_depth,
                        'project_id': project_id
                    })
                continue
            
            if should_scan_deeper(item):
                if verbose:
                    print(f"[DEBUG] Scanning deeper into: {item}")
                sub_projects = scan_directory(item_path, current_depth + 1, verbose)
                projects.extend(sub_projects)
                
    except Exception as e:
        print(f"[ERROR] Error scanning directory {path}: {str(e)}")
    
    return projects

def create_project_list(root_path, target_departments=None, force_scan=False, verbose=False):
    print("=== Starting project list creation ===")
    
    if not check_network_drive(root_path):
        raise Exception(f"Cannot access network drive: {root_path}")
    
    os.makedirs(STATIC_DATA_PATH, exist_ok=True)
    
    if not os.path.exists(DEPART_LIST_PATH):
        print(f"[ERROR] Department list not found: {DEPART_LIST_PATH}")
        return
    
    df_dept = pd.read_csv(DEPART_LIST_PATH)
    print(f"\nLoaded {len(df_dept)} departments")
    
    all_projects = []
    for _, dept in df_dept.iterrows():
        dept_code = str(dept['department_code']).zfill(5)
        dept_name = dept['department_name']
        dept_folder = f"{dept_code}_{dept_name}"
        dept_path = os.path.join(root_path, dept_folder)
        
        if target_departments and dept_code not in target_departments:
            if verbose:
                print(f"\n[SKIP] {dept_folder}")
            continue
        
        print(f"\n[SCAN] Scanning {dept_folder}...")
        if not os.path.exists(dept_path):
            print(f"- Department folder not found: {dept_path}")
            continue
        
        projects = scan_directory(dept_path, verbose=verbose)
        if projects:
            for project in projects:
                project['department_code'] = dept_code
                project['department_name'] = dept_name
            all_projects.extend(projects)
            print(f"- Found {len(projects)} projects")
        else:
            print("- No projects found")
    
    if all_projects:
        structured_data = [
            {
                'department_code': p['department_code'],
                'department_name': p['department_name'],
                'project_id': p['project_id'],
                'project_name': p['name'],
                'original_folder': p['path']
            } for p in all_projects
        ]
        
        df = pd.DataFrame(structured_data)
        df = df.sort_values(['department_code', 'project_id'])
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
        "07010",  # 항만 - 중복된 코드
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
