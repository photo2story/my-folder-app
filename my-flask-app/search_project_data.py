## /my-flask-app/search_project_data.py

import os
import json
import pandas as pd

class ProjectDocumentSearcher:
    # 문서 유형별 검색 키워드 정의
    DOCUMENT_KEYWORDS = {
        'contract': {
            'name': '계약서',
            'keywords': ['계약서', '계약']
        },
        'specification': {
            'name': '과업지시서',
            'keywords': ['과업지시서', '과업지시', '지시서', '내용서']  # 콤마 추가
        }
    }

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.static_dir = os.path.join(self.base_dir, 'static')
        self.data_dir = os.path.join(self.static_dir, 'data')
        self.projects_dir = os.path.join(self.static_dir, 'projects')
        
        # CSV 파일 경로
        self.project_list_csv = os.path.join(self.data_dir, 'project_list.csv')
        
        # 디렉토리 생성
        os.makedirs(self.projects_dir, exist_ok=True)

    def search_document(self, project_path, doc_type, depth=0):
        """프로젝트 폴더에서 특정 유형의 문서 관련 폴더를 단계별로 검색"""
        found_files = []
        
        # 검색할 키워드 가져오기
        keywords = self.DOCUMENT_KEYWORDS[doc_type]['keywords']
        doc_name = self.DOCUMENT_KEYWORDS[doc_type]['name']
        indent = "  " * depth
        
        try:
            # 현재 폴더의 내용물 검색
            print(f"\n{indent}검색 중: {os.path.basename(project_path)}")
            
            # 모든 하위 폴더 목록 가져오기
            for root, dirs, files in os.walk(project_path):
                # 현재 검색 중인 상대 경로
                rel_path = os.path.relpath(root, project_path)
                if rel_path != '.':
                    print(f"{indent}검색 중: {rel_path}")
                
                # 현재 폴더의 하위 폴더들 검사
                for dir_name in dirs:
                    if any(keyword in dir_name for keyword in keywords):
                        dir_path = os.path.join(root, dir_name)
                        relative_path = os.path.relpath(dir_path, project_path)
                        print(f"{indent}{doc_name} 폴더 발견: {relative_path}")
                        found_files.append({
                            'type': 'directory',
                            'name': dir_name,
                            'path': relative_path,
                            'full_path': dir_path,
                            'depth': len(relative_path.split(os.sep)) - 1,
                            'doc_type': doc_type
                        })
            
            return found_files
            
        except Exception as e:
            print(f"{indent}검색 중 오류 발생: {str(e)}")
            return []

    def process_single_project(self, project_id):
        """특정 프로젝트만 처리"""
        try:
            # 프로젝트 목록 읽기 (부서 코드를 문자열로 읽기)
            df = pd.read_csv(self.project_list_csv, dtype={
                'department_code': str,  # 부서 코드를 문자열로 읽기
                'project_id': str  # 프로젝트 ID도 문자열로 읽기
            })
            
            # 특정 프로젝트 찾기
            project = df[df['project_id'] == str(project_id)]
            
            if len(project) == 0:
                print(f"프로젝트 ID {project_id}를 찾을 수 없습니다.")
                return
            
            row = project.iloc[0]
            project_path = row['original_folder']
            
            # 부서 코드를 5자리로 맞추기
            dept_code = row['department_code'].zfill(5)
            
            print(f"\n프로젝트 정보:")
            print(f"- ID: {project_id}")
            print(f"- 부서: {dept_code}_{row['department_name']}")
            print(f"- 이름: {row['project_name']}")
            print(f"- 경로: {project_path}")
            
            # 프로젝트 경로가 존재하는지 확인
            if not os.path.exists(project_path):
                print(f"경로를 찾을 수 없음: {project_path}")
                return
            
            # 각 문서 유형별로 검색 수행
            all_documents = {}
            for doc_type in self.DOCUMENT_KEYWORDS.keys():
                doc_files = self.search_document(project_path, doc_type)
                all_documents[doc_type] = doc_files
                
                # 결과 출력
                doc_name = self.DOCUMENT_KEYWORDS[doc_type]['name'] # 문서 유형 이름
                if doc_files:
                    print(f"\n{doc_name} 관련 항목 발견: {len(doc_files)}개")
                    for doc in doc_files:
                        indent = "  " * doc['depth']
                        print(f"\n{indent}- 유형: {doc['type']}")
                        print(f"{indent}  이름: {doc['name']}")
                        print(f"{indent}  경로: {doc['path']}")
                else:
                    print(f"\n{doc_name} 관련 항목 없음")
            
            # JSON 직렬화를 위해 데이터 타입 변환
            result = {
                'project_id': str(row['project_id']),
                'department_code': dept_code,
                'department_name': str(row['department_name']),
                'project_name': str(row['project_name']),
                'project_path': str(row['original_folder']),
                'documents': {
                    doc_type: [
                        {
                            'type': str(doc['type']),
                            'name': str(doc['name']),
                            'path': str(doc['path']),
                            'full_path': str(doc['full_path']),
                            'depth': int(doc['depth'])
                        }
                        for doc in files
                    ]
                    for doc_type, files in all_documents.items()
                }
            }
            
            # JSON 파일로 저장
            json_path = os.path.join(self.projects_dir, f'{project_id}.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\nJSON 저장됨: {json_path}")
                
        except Exception as e:
            print(f"프로젝트 처리 중 오류 발생: {str(e)}")

if __name__ == "__main__":
    print("=== 프로젝트 문서 검색 시작 ===")
    searcher = ProjectDocumentSearcher()
    
    # 특정 프로젝트만 검색
    test_project_id = "20180076"
    searcher.process_single_project(test_project_id)
    
    print("\n=== 검색 완료 ===")

## python search_project_data.py    


