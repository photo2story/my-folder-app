## /my-flask-app/get_data.py

import os
import sys
import asyncio
import win32api
from pathlib import Path
import re
import csv
import pandas as pd

# 현재 디렉토리의 config를 임포트
import config



# 루트 디렉토리를 sys.path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# static/data 디렉토리의 depart_list.csv 경로
DEPART_LIST_PATH = os.path.join(config.STATIC_DATA_PATH, 'depart_list.csv')

async def get_project_list(disk_path=None):
    """공용 디스크를 찾는 함수"""
    try:
        # 1. 모든 드라이브 검색
        drives = win32api.GetLogicalDriveStrings()
        drives = drives.split('\000')[:-1]
        
        print("검색된 드라이브:", drives)
        
        # 2. 각 드라이브에서 "공용 디스크" 찾기
        for drive in drives:
            try:
                if os.path.exists(drive):
                    print(f"\n드라이브 {drive} 확인 중...")
                    
                    # 부서 폴더(01010_도로)로 공용 디스크 식별
                    if os.path.exists(os.path.join(drive, "01010_도로")):
                        print(f">>> {drive}에서 '01010_도로' 폴더 발견!")
                        network_path = os.path.realpath(drive)
                        print(f">>> 실제 네트워크 경로: {network_path}")
                        return network_path
                    
            except Exception as e:
                print(f"드라이브 {drive} 확인 중 오류: {str(e)}")
                continue
                
        print("\n'공용 디스크'를 찾지 못했습니다.")
        return None
        
    except Exception as e:
        print(f"전체 검색 중 오류 발생: {str(e)}")
        return None

async def get_department_list(disk_path):
    """부서 폴더 목록을 찾아서 CSV로 저장하는 함수"""
    try:
        if not disk_path:
            print("공용 디스크 경로를 찾을 수 없습니다.")
            return False

        # 결과를 저장할 리스트
        departments = []
        
        # 디렉토리 내의 모든 폴더 검색
        for item in os.listdir(disk_path):
            if os.path.isdir(os.path.join(disk_path, item)):
                # *****_ 패턴 매칭 (숫자 5자리 + 언더스코어)
                if re.match(r'^\d{5}_', item):
                    # 폴더명에서 번호와 이름 분리
                    number = item[:5]
                    name = item[6:]  # 언더스코어 다음부터
                    departments.append([number, name])
        
        # 번호순으로 정렬
        departments.sort(key=lambda x: x[0])
        
        # static/data 디렉토리 확인 및 생성
        save_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'data')
        os.makedirs(save_dir, exist_ok=True)
        
        # CSV 파일로 저장
        csv_path = os.path.join(save_dir, 'depart_list.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # 헤더 추가
            writer.writerow(['department_code', 'department_name'])
            writer.writerows(departments)
        
        print(f"부서 목록이 {csv_path}에 저장되었습니다.")
        print(f"총 {len(departments)}개 부서가 발견되었습니다.")
        return True
        
    except Exception as e:
        print(f"부서 목록 생성 중 오류 발생: {str(e)}")
        return False

async def get_projects_from_department(department_code=None):
    """부서 코드에 해당하는 프로젝트 목록을 가져오는 함수"""
    try:
        # 1. depart_list.csv 파일 읽기
        df = pd.read_csv(config.DEPART_LIST_PATH)
        
        # 2. 공용 디스크 경로 가져오기
        disk_path = await get_project_list()
        if not disk_path:
            print("공용 디스크를 찾을 수 없습니다.")
            return None
            
        # 3. 부서 코드가 지정되지 않은 경우 전체 부서의 프로젝트 검색
        if department_code is None:
            departments = df['department_code'].tolist()
        else:
            if str(department_code) not in df['department_code'].astype(str).values:
                print(f"부서 코드 {department_code}를 찾을 수 없습니다.")
                return None
            departments = [str(department_code)]
            
        # 4. 프로젝트 정보 수집
        projects = []
        for dept_code in departments:
            dept_folder = df[df['department_code'].astype(str) == str(dept_code)].iloc[0]
            dept_path = os.path.join(disk_path, f"{dept_code}_{dept_folder['department_name']}")
            
            if os.path.exists(dept_path):
                # 부서 폴더 내의 모든 하위 폴더를 프로젝트로 간주
                for item in os.listdir(dept_path):
                    project_path = os.path.join(dept_path, item)
                    if os.path.isdir(project_path):
                        project_info = {
                            'department_code': dept_code,
                            'department_name': dept_folder['department_name'],
                            'project_name': item,
                            'project_path': project_path
                        }
                        projects.append(project_info)
        
        return projects
        
    except Exception as e:
        print(f"프로젝트 목록 조회 중 오류 발생: {str(e)}")
        return None

async def test_get_projects():
    """프로젝트 목록 조회 테스트"""
    print("\n=== 프로젝트 목록 조회 테스트 시작 ===")
    
    # 1. 특정 부서의 프로젝트 조회
    print("\n1. 도로부서(01010) 프로젝트 조회")
    road_projects = await get_projects_from_department('01010')
    if road_projects:
        print(f"도로부서 프로젝트 수: {len(road_projects)}")
        for proj in road_projects[:5]:  # 처음 5개만 출력
            print(f"- {proj['project_name']}")
    
    # 2. 전체 부서의 프로젝트 조회
    print("\n2. 전체 부서 프로젝트 조회")
    all_projects = await get_projects_from_department()
    if all_projects:
        print(f"전체 프로젝트 수: {len(all_projects)}")
        # 부서별 프로젝트 수 집계
        dept_counts = {}
        for proj in all_projects:
            dept = f"{proj['department_code']}_{proj['department_name']}"
            dept_counts[dept] = dept_counts.get(dept, 0) + 1
        
        print("\n부서별 프로젝트 수:")
        for dept, count in dept_counts.items():
            print(f"- {dept}: {count}개")
    
    print("\n=== 테스트 완료 ===")

async def create_project_list():
    """
    부서 목록을 읽어서 각 부서의 프로젝트 정보를 수집하고 CSV로 저장하는 함수
    컬럼: 부서코드, 부서명, 프로젝트ID, 프로젝트명
    """
    try:
        # 1. 부서 목록 읽기
        if not os.path.exists(config.DEPART_LIST_PATH):
            print(f"부서 목록 파일을 찾을 수 없습니다: {config.DEPART_LIST_PATH}")
            return None
            
        depart_df = pd.read_csv(config.DEPART_LIST_PATH)
        
        # 2. 공용 디스크 경로 가져오기
        disk_path = await get_project_list()
        if not disk_path:
            print("공용 디스크를 찾을 수 없습니다.")
            return None
            
        # 특수 폴더 목록 정의
        SPECIAL_FOLDERS = {
            '001.준공 프로젝트',
            '002.진행 프로젝트',
            '1팀',
            '2팀',
            '3팀',
            '4팀',
            '창원팀',
            '해외사업',
            '1. 진행사업',
            '2. 준공사업',
            # 환경 부서 특수 폴더
            '01.환경영향평가',
            '02.사후환경영향조사',
            '03.전략환경영향평가',
            '04.소규모환경영향평가',
            '05.기타',
            '06.계약서',
            '07.기타',
        }
            
        def process_directory(dir_path, dept_code, dept_name, project_data, depth=0):
            """디렉토리를 재귀적으로 처리하는 함수"""
            try:
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    if os.path.isdir(item_path):
                        # 현재 폴더가 특수 폴더인 경우 재귀적으로 처리
                        if any(special in item for special in SPECIAL_FOLDERS):
                            print(f"{'  ' * depth}특수 폴더 발견: {item}")
                            process_directory(item_path, dept_code, dept_name, project_data, depth + 1)
                        
                        # 프로젝트 폴더 처리 (특수 폴더이든 아니든 프로젝트 패턴이 있는지 확인)
                        if process_project_folder(item, dept_code, dept_name, project_data):
                            print(f"{'  ' * depth}- 프로젝트 발견: {item}")
            except Exception as e:
                print(f"{'  ' * depth}- 폴더 {dir_path} 처리 중 오류: {str(e)}")
            
        # 3. 프로젝트 정보 수집
        project_data = []
        
        for _, dept in depart_df.iterrows():
            dept_code = str(dept['department_code']).zfill(5)  # 5자리로 맞추기
            dept_name = dept['department_name']
            dept_folder = f"{dept_code}_{dept_name}"
            dept_path = os.path.join(disk_path, dept_folder)
            
            print(f"\n{dept_folder} 검색 중...")
            
            if os.path.exists(dept_path):
                # 부서 폴더 내의 모든 항목을 재귀적으로 처리
                process_directory(dept_path, dept_code, dept_name, project_data)
        
        # 4. DataFrame 생성 및 저장
        if project_data:
            project_df = pd.DataFrame(project_data)
            
            # 정렬: 부서코드 -> 프로젝트ID 순
            project_df = project_df.sort_values(['department_code', 'project_id'])
            
            # CSV 파일로 저장
            save_path = os.path.join(os.path.dirname(config.DEPART_LIST_PATH), 'project_list.csv')
            project_df.to_csv(save_path, index=False, encoding='utf-8')
            
            print(f"\n프로젝트 목록이 저장되었습니다: {save_path}")
            print(f"총 {len(project_df)}개 프로젝트가 발견되었습니다.")
            
            return project_df
        else:
            print("\n프로젝트를 찾을 수 없습니다.")
            return None
            
    except Exception as e:
        print(f"프로젝트 목록 생성 중 오류 발생: {str(e)}")
        return None

def process_project_folder(folder_name, dept_code, dept_name, project_data):
    """프로젝트 폴더를 처리하는 헬퍼 함수"""
    
    def format_project_id(year, number):
        """프로젝트 ID를 8자리로 포맷팅하는 헬퍼 함수"""
        # 연도(YYYY) 다음에 0을 추가하고 나머지 숫자를 뒤에 붙임
        return f"{year}0{number.zfill(3)}"
    
    # 구분선이나 메모 폴더 제외
    if '----' in folder_name or folder_name.endswith('(이하)'):
        return False
    
    # 1. 공항인프라 부서의 CYYYYNNNN 패턴 찾기
    match = re.search(r'^C((?:19|20)\d{2})(\d{4})(?:_|\s)', folder_name)
    if match:
        year = match.group(1)  # 연도 부분 (예: 2023)
        number = match.group(2)  # 번호 부분 (예: 0087)
        project_id = f"C{format_project_id(year, number)}"  # 예: C20230087
        
        # 프로젝트명은 프로젝트 ID 이후의 문자열
        full_id = f"C{match.group(1)}{match.group(2)}"
        start_pos = folder_name.find(full_id) + len(full_id)
        project_name = folder_name[start_pos:].strip('_ -')
        if not project_name:
            project_name = folder_name
        
        project_data.append({
            'department_code': dept_code,
            'department_name': dept_name,
            'project_id': project_id,
            'project_name': project_name.strip(),
            'original_folder': folder_name
        })
        return True
    
    # 2. 도시계획 부서의 YYYY-NNN 패턴 찾기
    match = re.search(r'(?:^|\s|_)((?:19|20)\d{2})-(\d{3})(?:\s|_|\.)', folder_name)
    if match:
        year = match.group(1)  # 연도 부분 (예: 2017)
        number = match.group(2)  # 번호 부분 (예: 091)
        project_id = format_project_id(year, number)  # 예: 20170091
        
        # 프로젝트명은 프로젝트 ID 이후의 문자열 (점 또는 공백 이후)
        full_id = f"{match.group(1)}-{match.group(2)}"
        start_pos = folder_name.find(full_id) + len(full_id)
        project_name = folder_name[start_pos:].strip('_ -.★')  # ★ 기호도 제거
        if not project_name:
            project_name = folder_name
        
        project_data.append({
            'department_code': dept_code,
            'department_name': dept_name,
            'project_id': project_id,
            'project_name': project_name.strip(),
            'original_folder': folder_name
        })
        return True
    
    # 3. 상하수도 부서의 패턴 찾기
    # 3-1. [준공] Y20220257 형식
    match = re.search(r'(?:\[.*?\]\s*)?Y((?:19|20)\d{2})(\d{4})\s', folder_name)
    if match:
        year = match.group(1)  # 연도 부분
        number = match.group(2)  # 번호 부분
        project_id = format_project_id(year, number)
        
        # 프로젝트명에서 대괄호 부분과 ID 제거
        name_start = folder_name.find(']')
        if name_start != -1:
            name_start += 1
            project_name = folder_name[name_start:].strip()
        else:
            project_name = folder_name
            
        # Y20220257 같은 패턴 제거
        project_name = re.sub(r'Y\d{8}\s*', '', project_name).strip()
        
        project_data.append({
            'department_code': dept_code,
            'department_name': dept_name,
            'project_id': project_id,
            'project_name': project_name.strip(),
            'original_folder': folder_name
        })
        return True
    
    # 3-2. Y2000001 형식 (대괄호 없는 경우)
    match = re.search(r'^Y((?:19|20)\d{2})(\d{4})', folder_name)
    if match:
        year = match.group(1)
        number = match.group(2)
        project_id = format_project_id(year, number)
        
        # Y2000001 이후의 문자열을 프로젝트명으로
        start_pos = 9  # Y + YYYYNNNN = 9글자
        project_name = folder_name[start_pos:].strip('_ -')
        if not project_name:
            project_name = folder_name
        
        project_data.append({
            'department_code': dept_code,
            'department_name': dept_name,
            'project_id': project_id,
            'project_name': project_name.strip(),
            'original_folder': folder_name
        })
        return True
    
    # 4. 일반적인 연도+숫자(YYYYNNNN) 패턴 찾기
    match = re.search(r'(?:^|\s|_|-)((?:19|20)\d{2})(\d{2,4})(?:\s|_|-|$)', folder_name)
    if match:
        year = match.group(1)  # 연도 부분 (예: 2017)
        number = match.group(2)  # 번호 부분 (예: 105)
        
        # 프로젝트 ID가 구분선이나 메모인 경우 제외
        if year + number == "2000000":
            return False
            
        project_id = format_project_id(year, number)
        
        # 프로젝트명은 프로젝트 ID 이후의 문자열
        full_id = match.group(1) + match.group(2)
        start_pos = folder_name.find(full_id) + len(full_id)
        project_name = folder_name[start_pos:].strip('_ -')
        if not project_name:
            project_name = folder_name
            
        # 특수문자 처리
        project_name = project_name.replace('․', '·')  # 중간점 통일
        
        project_data.append({
            'department_code': dept_code,
            'department_name': dept_name,
            'project_id': project_id,
            'project_name': project_name.strip(),
            'original_folder': folder_name
        })
        return True
        
    # 5. YYYYMMDD 형식 찾기
    match = re.search(r'(?:^|\s|_|-)(20\d{6})(?:\s|_|-|$)', folder_name)
    if match:
        project_id = match.group(1)
        start_pos = folder_name.find(project_id) + len(project_id)
        project_name = folder_name[start_pos:].strip('_ -')
        if not project_name:
            project_name = folder_name
            
        # 특수문자 처리
        project_name = project_name.replace('․', '·')  # 중간점 통일
        
        project_data.append({
            'department_code': dept_code,
            'department_name': dept_name,
            'project_id': project_id,
            'project_name': project_name.strip(),
            'original_folder': folder_name
        })
        return True
        
    return False  # 프로젝트 ID를 찾지 못한 경우

async def test_create_project_list():
    """프로젝트 목록 생성 테스트"""
    print("\n=== 프로젝트 목록 생성 테스트 시작 ===")
    
    df = await create_project_list()
    
    if df is not None:
        # 부서별 프로젝트 수 출력
        dept_counts = df.groupby(['department_code', 'department_name']).size().reset_index(name='count')
        print("\n부서별 프로젝트 수:")
        for _, row in dept_counts.iterrows():
            print(f"- {row['department_code']}_{row['department_name']}: {row['count']}개")
            
        # 처음 5개 프로젝트 출력
        print("\n처음 5개 프로젝트:")
        print(df.head().to_string())
    
    print("\n=== 테스트 완료 ===")

if __name__ == "__main__":
    print("프로젝트 목록 생성 시작")
    asyncio.run(test_create_project_list())

## python Get_data.py    

