# my-flask-app/search_project_data.py
import os
import json
import asyncio
import aiofiles
from pathlib import Path
from datetime import datetime
from functools import lru_cache
from io import StringIO
import pandas as pd
from config import DOCUMENT_TYPES, PROJECT_LIST_CSV, STATIC_DATA_PATH

class ProjectDocumentSearcher:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.static_dir = os.path.join(self.base_dir, 'static')
        self.data_dir = os.path.join(self.static_dir, 'data')
        self.projects_dir = os.path.join(self.static_dir, 'projects')
        
        # CSV 파일 경로
        self.project_list_csv = PROJECT_LIST_CSV
        
        # DataFrame 초기화
        self._project_df = None
        
        # 검색 결과 캐시 초기화
        self._cache = {}
        
        # 검색 제외 패턴
        self._skip_patterns = {'backup', '백업', 'old', '이전', 'temp', '임시'}
        self._valid_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx'}
        self._exclude_extensions = {'.tmp', '.bak'}
        
        # 디렉토리 생성
        os.makedirs(self.projects_dir, exist_ok=True)

    async def _load_project_list(self):
        """프로젝트 목록 비동기 로드"""
        if self._project_df is None:
            try:
                async with aiofiles.open(self.project_list_csv, encoding='utf-8') as f:
                    content = await f.read()
                    self._project_df = pd.read_csv(StringIO(content))
                print(f"[DEBUG] 프로젝트 목록 로드 완료: {len(self._project_df)}개 프로젝트")
            except Exception as e:
                print(f"[ERROR] 프로젝트 목록 로드 실패: {str(e)}")
                self._project_df = pd.DataFrame()
        return self._project_df

    async def get_project_info(self, project_id):
        """프로젝트 정보 비동기 조회"""
        df = await self._load_project_list()
        project = df[df['project_id'].astype(str) == str(project_id)]
        if project.empty:
            print(f"[ERROR] Project ID {project_id} not found in project list")
            return None
        return project.iloc[0].to_dict()

    @lru_cache(maxsize=1000)
    def is_valid_document(self, path):
        """문서 유효성 검사 (캐시 적용)"""
        ext = Path(path).suffix.lower()
        return ext in self._valid_extensions and ext not in self._exclude_extensions

    def _should_skip_path(self, path):
        """검색 제외 경로 확인"""
        name = Path(path).name.lower()
        return any(skip in name for skip in self._skip_patterns)

    async def _scan_files(self, path: Path):
        """파일 목록을 비동기적으로 스캔"""
        try:
            # os.scandir을 비동기적으로 실행
            entries = await asyncio.to_thread(lambda: list(os.scandir(str(path))))
            return entries
        except Exception as e:
            print(f"[ERROR] Failed to scan directory {path}: {str(e)}")
            return []

    async def _scan_directory(self, project_path: Path, current_depth=0, max_depth=3):
        """디렉토리 비동기 스캔"""
        if current_depth > max_depth or self._should_skip_path(project_path):
            return {}, {}

        results = {doc_type: [] for doc_type in DOCUMENT_TYPES.keys()}
        total_found = {doc_type: 0 for doc_type in DOCUMENT_TYPES.keys()}

        try:
            # 디렉토리 스캔
            entries = await self._scan_files(project_path)
            
            # 파일 처리
            files = [entry for entry in entries if entry.is_file()]
            for entry in files:
                item_path = Path(entry.path)
                if not self._should_skip_path(item_path):
                    if self.is_valid_document(item_path):
                        item_name = item_path.name.lower()
                        for doc_type, type_info in DOCUMENT_TYPES.items():
                            if len(results[doc_type]) >= 3:
                                continue
                            if any(keyword.lower() in item_name for keyword in type_info['keywords']):
                                total_found[doc_type] += 1
                                print(f"[DEBUG] Found {type_info['name']} at depth {current_depth}: {item_path.name}")
                                results[doc_type].append({
                                    'type': 'file',
                                    'name': item_path.name,
                                    'path': str(item_path.relative_to(project_path.parent)),
                                    'full_path': str(item_path),
                                    'depth': current_depth
                                })
                                break

            # 하위 디렉토리 처리
            dirs = [Path(entry.path) for entry in entries if entry.is_dir() and not self._should_skip_path(Path(entry.path))]
            if dirs and current_depth < max_depth:
                tasks = [self._scan_directory(d, current_depth + 1, max_depth) for d in dirs]
                subdir_results = await asyncio.gather(*tasks)
                
                # 결과 병합
                for subdir_result, subdir_total in subdir_results:
                    for doc_type in DOCUMENT_TYPES.keys():
                        current_count = len(results[doc_type])
                        if current_count < 3:
                            space_left = 3 - current_count
                            results[doc_type].extend(subdir_result[doc_type][:space_left])
                        total_found[doc_type] += subdir_total[doc_type]

        except Exception as e:
            print(f"[ERROR] Directory scan failed: {str(e)}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")

        return results, total_found

    async def search_all_documents(self, project_id, max_depth=3):
        """프로젝트 문서 검색 (비동기 최적화)"""
        print(f"\n[DEBUG] Starting async document search for project: {project_id}")
        
        # 캐시 키에 마지막 수정 시간 포함
        mtime = os.path.getmtime(self.project_list_csv)
        cache_key = f"docs_{project_id}_{max_depth}_{mtime}"
        
        if cache_key in self._cache:
            print("[DEBUG] Using cached results")
            return self._cache[cache_key]

        project_info = await self.get_project_info(project_id)
        if not project_info:
            return {}

        project_path = Path(project_info['original_folder'])
        if not project_path.exists():
            print(f"[ERROR] Project path does not exist: {project_path}")
            return {}

        print(f"[DEBUG] Processing project path: {project_path}")
        results, total_found = await self._scan_directory(project_path, max_depth=max_depth)

        # 결과 요약
        print("\n[DEBUG] Search Results Summary:")
        found_any = False
        for doc_type, items in results.items():
            if items:
                found_any = True
                print(f"[DEBUG] - {DOCUMENT_TYPES[doc_type]['name']}: {len(items)} saved (total: {total_found[doc_type]})")
        
        if not found_any:
            print("[WARNING] No documents found in any category")

        self._cache[cache_key] = results
        return results

    async def search_document(self, project_path, doc_type, depth=0):
        """프로젝트 폴더에서 특정 유형의 문서 관련 폴더를 단계별로 검색"""
        found_files = []
        
        # 검색할 키워드 가져오기
        doc_info = DOCUMENT_TYPES[doc_type]
        keywords = doc_info['keywords']
        doc_name = doc_info['name']
        indent = "  " * depth
        
        try:
            # 현재 폴더의 내용물 검색
            print(f"\n{indent}검색 중: {os.path.basename(project_path)}")
            
            # 현재 폴더에서 관련 폴더 찾기
            for item in os.listdir(project_path):
                item_path = os.path.join(project_path, item)
                
                if os.path.isdir(item_path):
                    if any(keyword in item for keyword in keywords):
                        print(f"{indent}{doc_name} 폴더 발견: {item}")
                        found_files.append({
                            'type': 'directory',
                            'name': item,
                            'path': os.path.relpath(item_path, project_path),
                            'full_path': item_path,
                            'depth': depth,
                            'doc_type': doc_type
                        })
                        # 발견된 폴더의 하위 검색
                        sub_results = await self.search_document(item_path, doc_type, depth + 1)
                        found_files.extend(sub_results)
            
            return found_files
            
        except Exception as e:
            print(f"{indent}검색 중 오류 발생: {str(e)}")
            return []

    async def process_single_project(self, project_id):
        """특정 프로젝트만 처리"""
        try:
            # 프로젝트 목록 읽기 (부서 코드를 문자열로 읽기)
            df = pd.read_csv(self.project_list_csv, dtype={
                'department_code': str,
                'project_id': str
            })
            
            # 특정 프로젝트 찾기
            project = df[df['project_id'] == str(project_id)]
            
            if len(project) == 0:
                print(f"프로젝트 ID {project_id}를 찾을 수 없습니다.")
                return
            
            row = project.iloc[0]
            project_path = row['original_folder']
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
            for doc_type in DOCUMENT_TYPES.keys():
                doc_files = await self.search_document(project_path, doc_type)
                all_documents[doc_type] = doc_files
                
                # 결과 출력
                doc_name = DOCUMENT_TYPES[doc_type]['name']
                if doc_files:
                    print(f"\n{doc_name} 관련 항목 발견: {len(doc_files)}개")
                    for doc in doc_files:
                        indent = "  " * doc['depth']
                        print(f"\n{indent}- 유형: {doc['type']}")
                        print(f"{indent}  이름: {doc['name']}")
                        print(f"{indent}  경로: {doc['path']}")
                else:
                    print(f"\n{doc_name} 관련 항목 없음")
            
            # 결과를 JSON으로 저장
            result = {
                'project_id': project_id,
                'department_code': dept_code,
                'department_name': str(row['department_name']),
                'project_name': str(row['project_name']),
                'project_path': str(project_path),
                'documents': all_documents
            }
            
            # JSON 파일로 저장
            json_path = os.path.join(self.projects_dir, f'{project_id}.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\nJSON 저장됨: {json_path}")
                
        except Exception as e:
            print(f"프로젝트 처리 중 오류 발생: {str(e)}")

if __name__ == "__main__":
    import asyncio
    
    print("=== 프로젝트 문서 검색 시작 ===")
    searcher = ProjectDocumentSearcher()
    
    # 특정 프로젝트만 검색
    test_project_id = "20180076"
    asyncio.run(searcher.process_single_project(test_project_id))
    
    print("\n=== 검색 완료 ===")


