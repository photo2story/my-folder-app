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
from config import DOCUMENT_TYPES, PROJECT_LIST_CSV

class ProjectDocumentSearcher:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.static_dir = os.path.join(self.base_dir, 'static')
        self.data_dir = os.path.join(self.static_dir, 'data')
        self.project_list_csv = PROJECT_LIST_CSV
        self._cache = {}
        self._project_df = None
        
        # 유효한 확장자 및 제외 패턴
        self._valid_extensions = {'.pdf', '.hwp', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'}
        self._exclude_extensions = {'.bak', '.tmp', '.temp', '.bk', '.log'}
        self._skip_patterns = {'backup', 'old', 'temp', '휴지통', '백업', '임시', 'test', '테스트'}

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

    async def search_document(self, project_id, doc_type):
        """특정 문서 유형 검색 (비동기)"""
        all_results = await self.search_all_documents(project_id)
        return all_results.get(doc_type, [])

    def clear_cache(self):
        """캐시 초기화"""
        self._cache = {}
        self._project_df = None

if __name__ == "__main__":
    # 테스트 코드
    async def run_test():
        searcher = ProjectDocumentSearcher()
        test_project_id = "20180076"
        
        print("\n=== 프로젝트 정보 테스트 ===")
        project_info = await searcher.get_project_info(test_project_id)
        if project_info:
            print(f"프로젝트 정보:")
            print(f"- ID: {project_info['project_id']}")
            print(f"- 부서: {project_info['department_code']}_{project_info['department_name']}")
            print(f"- 이름: {project_info['project_name']}")
            print(f"- 경로: {project_info['original_folder']}")
        
        print("\n=== 문서 검색 테스트 ===")
        results = await searcher.search_all_documents(test_project_id)
        
        print("\n검색 결과 요약:")
        total_docs = 0
        for doc_type, items in results.items():
            if items:
                doc_name = DOCUMENT_TYPES[doc_type]['name']
                print(f"\n{doc_name} ({len(items)}개):")
                total_docs += len(items)
                for item in items[:3]:
                    print(f"- {item['name']}")
        
        print(f"\n총 {total_docs}개의 문서를 찾았습니다.")

    asyncio.run(run_test())


