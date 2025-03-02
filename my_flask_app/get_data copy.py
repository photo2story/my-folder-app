## /my_flask_app/get_data.py

import os
import sys
import asyncio
import win32api
from pathlib import Path
import re
import csv
import pandas as pd
import traceback
from config_assets import SCAN_CONFIG
from config import PROJECT_LIST_CSV, STATIC_DATA_PATH, NETWORK_BASE_PATH
from datetime import datetime
from config_assets import FORCE_SCAN_CONFIG

# 현재 스크립트의 절대 경로
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 프로젝트 루트 디렉토리 (my-folder-app)
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# static/data 디렉토리의 절대 경로
STATIC_DATA_PATH = os.path.join(ROOT_DIR, 'static', 'data')

# depart_list.csv 파일의 절대 경로
DEPART_LIST_PATH = os.path.join(STATIC_DATA_PATH, 'depart_list.csv')

def check_network_drive(drive_path):
    """네트워크 드라이브 접근 가능 여부 확인"""
    try:
        print(f"\n[DEBUG] 네트워크 드라이브 확인 중: {drive_path}")
        
        # 1. 드라이브 존재 여부 확인
        if not os.path.exists(drive_path):
            print(f"[ERROR] 네트워크 드라이브가 존재하지 않습니다: {drive_path}")
            return False
            
        # 2. 드라이브 내용 읽기 권한 확인
        try:
            os.listdir(drive_path)
            print(f"[DEBUG] 네트워크 드라이브 접근 가능: {drive_path}")
            return True
        except PermissionError:
            print(f"[ERROR] 네트워크 드라이브 접근 권한이 없습니다: {drive_path}")
            return False
        except Exception as e:
            print(f"[ERROR] 네트워크 드라이브 접근 실패: {str(e)}")
            return False
            
    except Exception as e:
        print(f"[ERROR] 네트워크 드라이브 확인 중 오류 발생: {str(e)}")
        return False

def should_scan_deeper(folder_name):
    """폴더를 더 깊이 탐색할지 결정하는 함수"""
    for keyword in FORCE_SCAN_CONFIG['deep_scan_keywords']:
        if keyword in folder_name:
            print(f"[DEBUG] Found keyword '{keyword}' in folder: {folder_name}")
            return True
    return False

def is_project_folder(folder_name):
    """프로젝트 폴더인지 판단하는 함수"""
    # 연도 패턴 (1990-2029) 체크
    year_pattern = r'(?:19[9]|20[0-2])\d'
    if re.search(year_pattern, folder_name):
        print(f"[DEBUG] Found year pattern in folder: {folder_name}")
        return True
    return False

def extract_project_id(folder_name):
    """프로젝트 ID를 추출하고 조정하는 함수"""
    print(f"\n[DEBUG] 프로젝트 ID 추출 시도: {folder_name}")
    
    # 1. 이미 8자리인 경우 (예: 20060167)
    eight_digit_match = re.search(r'(?:^|[^\d])(\d{8})(?:[^\d]|$)', folder_name)
    if eight_digit_match:
        project_id = eight_digit_match.group(1)
        print(f"[DEBUG] 8자리 숫자 발견: {project_id}")
        return project_id
    
    # 2. 7자리 연속 숫자인 경우 (예: 2006167)
    seven_digit_match = re.search(r'(?:^|[^\d])(\d{7})(?:[^\d]|$)', folder_name)
    if seven_digit_match:
        number = seven_digit_match.group(1)
        year = number[:4]
        seq = number[4:]
        project_id = f"{year}0{seq.zfill(3)}"
        print(f"[DEBUG] 7자리 숫자를 8자리로 변환: {number} -> {project_id}")
        return project_id
    
    # 3. 연도와 일련번호가 분리된 경우 (예: 2006-167, 2018_167)
    split_match = re.search(r'((?:19[9]|20[0-2])\d)[^0-9]*(\d{2,3})(?:[^\d]|$)', folder_name)
    if split_match:
        year = split_match.group(1)
        seq = split_match.group(2)
        project_id = f"{year}0{seq.zfill(3)}"
        print(f"[DEBUG] 분리된 연도({year})와 일련번호({seq})를 결합: {project_id}")
        return project_id
    
    # 4. 연도만 있는 경우 (예: 2006)
    year_match = re.search(r'((?:19[9]|20[0-2])\d)', folder_name)
    if year_match:
        year = year_match.group(1)
        project_id = f"{year}nnnn"  # 일련번호가 없는 경우 'nnnn' 사용
        print(f"[DEBUG] 연도만 발견. 임시 일련번호 추가: {project_id}")
        return project_id
    
    print(f"[DEBUG] 프로젝트 ID를 추출할 수 없음: {folder_name}")
    return None

def scan_directory(path, current_depth=0):
    """폴더 스캔 함수 - 프로젝트 폴더 탐색"""
    print(f"\n[DEBUG] Scanning directory: {path} (depth: {current_depth})")
    
    if current_depth > SCAN_CONFIG['max_category_depth']:
        print(f"[DEBUG] Max depth reached: {current_depth}")
        return []
        
    projects = []
    try:
        items = os.listdir(path)
        
        for item in items:
            item_path = os.path.join(path, item)
            if not os.path.isdir(item_path):
                continue
                
            print(f"[DEBUG] Checking folder: {item}")
            
            # 1. 프로젝트 폴더 체크
            if is_project_folder(item):
                project_id = extract_project_id(item)
                if project_id:
                    print(f"[DEBUG] Found project: {item} (ID: {project_id})")
                    projects.append({
                        'name': item,
                        'path': item_path,
                        'depth': current_depth,
                        'project_id': project_id
                    })
                continue
            
            # 2. 더 깊은 탐색 여부 결정
            if should_scan_deeper(item):
                print(f"[DEBUG] Scanning deeper into: {item}")
                sub_projects = scan_directory(item_path, current_depth + 1)
                projects.extend(sub_projects)
            
    except Exception as e:
        print(f"[DEBUG] Error scanning directory {path}: {str(e)}")
        print(traceback.format_exc())
        
    return projects

def create_project_list(root_path, target_departments=None):
    """프로젝트 목록 생성 메인 함수"""
    print("=== 프로젝트 목록 생성 시작 ===")
    
    try:
        # 1. 네트워크 드라이브 확인
        if not check_network_drive(root_path):
            raise Exception(f"네트워크 드라이브에 접근할 수 없습니다: {root_path}")
        
        # 2. 초기 설정
        os.makedirs(STATIC_DATA_PATH, exist_ok=True)
        
        # 2. 부서 목록 로드
        if not os.path.exists(DEPART_LIST_PATH):
            print(f"부서 목록 파일을 찾을 수 없습니다: {DEPART_LIST_PATH}")
            return
            
        df_dept = pd.read_csv(DEPART_LIST_PATH)
        print(f"\n부서 목록 로드 완료: {len(df_dept)}개 부서")
        
        all_projects = []
        processed_depts = []
        skipped_depts = []
        
        # 3. 부서별 프로젝트 스캔
        for _, dept in df_dept.iterrows():
            dept_code = str(dept['department_code']).zfill(5)
            dept_name = dept['department_name']
            dept_folder = f"{dept_code}_{dept_name}"
            dept_path = os.path.join(root_path, dept_folder)
            
            # 처리할 부서 필터링
            if target_departments and dept_code not in target_departments:
                print(f"\n[SKIP] {dept_folder}")
                skipped_depts.append(dept_folder)
                continue
                
            print(f"\n[SCAN] {dept_folder} 처리 중...")
            
            if not os.path.exists(dept_path):
                print(f"- 부서 폴더 없음: {dept_path}")
                skipped_depts.append(dept_folder)
                continue
            
            # 부서 폴더 스캔
            projects = scan_directory(dept_path)
            if projects:
                # 현재 부서 정보로 프로젝트 데이터 확장
                for project in projects:
                    project['department_code'] = dept_code
                    project['department_name'] = dept_name
                all_projects.extend(projects)
                processed_depts.append(dept_folder)
                print(f"- {len(projects)}개 프로젝트 발견")
            else:
                print("- 프로젝트 없음")
                skipped_depts.append(dept_folder)
        
        # 4. 결과 처리
        if all_projects:
            # 새로운 구조의 데이터 생성
            structured_data = [
                {
                    'department_code': project['department_code'],
                    'department_name': project['department_name'],
                    'project_id': project['project_id'],
                    'project_name': project['name'],
                    'original_folder': project['path']
                }
                for project in all_projects
            ]
            
            print(f"\n[DEBUG] 최종 처리된 데이터 수: {len(structured_data)}")
            
            # DataFrame 생성 및 정렬
            if structured_data:
                df = pd.DataFrame(structured_data)
                print("\n[DEBUG] DataFrame 생성됨")
                print(f"[DEBUG] 컬럼 목록: {df.columns.tolist()}")
                
                if 'department_code' in df.columns and 'project_id' in df.columns:
                    df = df.sort_values(['department_code', 'project_id'])
                    print("[DEBUG] 정렬 완료")
                else:
                    print("[DEBUG] 경고: 필요한 컬럼이 없어 정렬을 건너뜀")
            
            # 통계 출력
            print(f"\n=== 수집 결과 ===")
            print(f"총 프로젝트 수: {len(df)}개")
            
            # 부서별 프로젝트 수 출력
            dept_stats = df.groupby(['department_code', 'department_name']).size()
            print("\n부서별 프로젝트 수:")
            for (dept_code, dept_name), count in dept_stats.items():
                print(f"- {dept_code}_{dept_name}: {count}개")
            
            # CSV 파일 저장
            df.to_csv(PROJECT_LIST_CSV, index=False, encoding='utf-8')
            print(f"\nCSV 파일 저장 완료: {PROJECT_LIST_CSV}")
            
        else:
            print("\n수집된 프로젝트가 없습니다.")
            
    except Exception as e:
        print(f"\n오류 발생: {str(e)}")
        print(f"상세 오류:\n{traceback.format_exc()}")
    
    print("\n=== 프로젝트 목록 생성 완료 ===")

if __name__ == "__main__":
    # 처리할 부서 코드 목록 (주석 처리된 부서는 건너뜀)
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
    
    # config.py에서 정의된 네트워크 드라이브 경로 사용
    root_path = NETWORK_BASE_PATH
    print(f"\n네트워크 드라이브 경로: {root_path}")
    
    create_project_list(root_path, TARGET_DEPARTMENTS)

# python get_data.py
# python get_data.py --verbose
