# /my_flask_app/search_project_data.py

import os
import json
import asyncio
import aiofiles
import logging
import time
from pathlib import Path
from datetime import datetime
from functools import lru_cache
import pandas as pd
from config import PROJECT_LIST_CSV, STATIC_DATA_PATH, get_full_path, NETWORK_BASE_PATH
from config_assets import DOCUMENT_TYPES
from concurrent.futures import ThreadPoolExecutor
import re
from unittest.mock import patch, AsyncMock

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 정규표현식 미리 컴파일
KEYWORD_PATTERNS = {
    doc_type: re.compile('|'.join(map(re.escape, info['keywords'])), re.IGNORECASE)
    for doc_type, info in DOCUMENT_TYPES.items()
}

# 문서 유형 우선순위 (중복 방지, agreement와 completion 우선)
DOCUMENT_PRIORITY = ['agreement', 'completion', 'contract', 'specification', 'initiation', 'budget', 
                    'deliverable1', 'deliverable2', 'certificate', 'evaluation']

class ProjectDocumentSearcher:
    def __init__(self, verbose=False):
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
        self._dir_cache = {}
        self._file_cache = {}  # 파일별 문서 유형 캐싱
        
        # 검색 제외 패턴
        self._skip_patterns = {'backup', '백업', 'old', '이전', 'temp', '임시'}
        self._valid_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.hwp', '.zip'}
        self._exclude_extensions = {'.tmp', '.bak'}
        
        self.verbose = verbose
        
        # 스레드 풀 초기화
        self.executor = ThreadPoolExecutor(max_workers=8)
        
        # 디렉토리 생성
        os.makedirs(self.projects_dir, exist_ok=True)

        # 캐시 통계
        self.cache_hits = 0
        self.cache_misses = 0

    async def _load_project_list(self):
        """프로젝트 목록 로드"""
        try:
            df = pd.read_csv(PROJECT_LIST_CSV)
            self._project_df = {
                str(row['project_id']): {
                    'department_code': str(row['department_code']).zfill(5),
                    'department_name': row['department_name'],
                    'project_name': row['project_name'],
                    'original_folder': get_full_path(row['original_folder'], verbose=self.verbose)
                }
                for _, row in df.iterrows()
            }
            if self.verbose:
                logger.debug(f"프로젝트 목록 로드 완료: {len(self._project_df)}개 프로젝트")
            return self._project_df
        except Exception as e:
            logger.error(f"프로젝트 목록 로드 실패: {str(e)}")
            return {}

    async def get_project_info(self, project_id, department_code=None):
        """부서 코드와 project_id로 프로젝트 정보 비동기 조회"""
        project_list = await self._load_project_list()
        if department_code:
            filtered_projects = {k: v for k, v in project_list.items() if k == str(project_id) and v['department_code'] == str(department_code)}
        else:
            filtered_projects = {k: v for k, v in project_list.items() if k == str(project_id)}
        
        if not filtered_projects:
            logger.error(f"Project ID {project_id} not found in project list for department {department_code}")
            return None
        
        # 지정된 department_code가 있으면 해당 부서의 데이터만 반환, 없으면 첫 번째 부서 반환
        if department_code:
            project_info = next((v for k, v in filtered_projects.items() if v['department_code'] == str(department_code)), None)
            if not project_info:
                logger.error(f"Department code {department_code} not found for project ID {project_id}")
                return None
            return project_info
        else:
            return list(filtered_projects.values())[0]  # 기본적으로 첫 번째 부서 반환

    @lru_cache(maxsize=1000)
    def is_valid_document(self, path):
        """문서 유효성 검사 (캐시 적용)"""
        ext = Path(path).suffix.lower()
        return ext in self._valid_extensions and ext not in self._exclude_extensions

    def _should_skip_path(self, path):
        """검색 제외 경로 확인"""
        name = Path(path).name.lower()
        return any(skip in name for skip in self._skip_patterns)

    async def _scan_directory_entries(self, path):
        """디렉토리 항목을 비동기적으로 스캔 (캐싱 최최화)"""
        cache_key = str(path)
        if cache_key in self._dir_cache:
            self.cache_hits += 1
            return self._dir_cache[cache_key]

        self.cache_misses += 1
        try:
            loop = asyncio.get_event_loop()
            entries = await loop.run_in_executor(self.executor, os.scandir, str(path))
            result = list(entries)
            self._dir_cache[cache_key] = result
            if self.verbose:
                logger.debug(f"Scanned directory: {path}, entries: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"디렉토리 스캔 실패 {path}: {str(e)}")
            return []

    def _match_document_type(self, file_name):
        """파일 이름에서 문서 유형 매칭 (중복 방지, 우선순위 적용, 재검사 포함)"""
        file_lower = file_name.lower()
        if file_lower in self._file_cache:
            self.cache_hits += 1
            logger.debug(f"Cache hit for {file_name}: {self._file_cache[file_lower]}")
            return self._file_cache[file_lower]

        self.cache_misses += 1
        for doc_type in DOCUMENT_PRIORITY:
            if KEYWORD_PATTERNS[doc_type].search(file_lower):
                logger.debug(f"Matched {file_name} with {doc_type} using pattern: {KEYWORD_PATTERNS[doc_type].pattern}")
                self._file_cache[file_lower] = doc_type
                return doc_type

        # 재검사 로직: agreement, completion, evaluation 우선 재검사
        for doc_type in ['agreement', 'completion', 'evaluation']:
            if KEYWORD_PATTERNS[doc_type].search(file_lower):
                logger.debug(f"Re-matched {file_name} with {doc_type} using pattern: {KEYWORD_PATTERNS[doc_type].pattern}")
                self._file_cache[file_lower] = doc_type
                if self.verbose:
                    logger.debug(f"재검사 성공 - 파일: {file_name}, 유형: {doc_type}")
                return doc_type

        logger.debug(f"매칭 실패 - 파일: {file_name}")
        self._file_cache[file_lower] = None
        return None

    async def search_document(self, project_path, doc_type, depth=0, max_found=3, found_count=0):
        """프로젝트 폴더에서 특정 유형의 문서 파일을 검색 (최대 3개까지)"""
        if found_count >= max_found or depth > 7:
            return []

        found_items = []
        total_found = found_count
        pattern = KEYWORD_PATTERNS[doc_type]
        doc_name = DOCUMENT_TYPES[doc_type]['name']

        try:
            if self.verbose:
                logger.debug(f"Searching in {project_path}, depth: {depth}, doc_type: {doc_type}")
            entries = await self._scan_directory_entries(project_path)
            
            # 파일 먼저 처리 (최대 3개까지만)
            for entry in entries:
                if total_found >= max_found:
                    break
                    
                try:
                    if entry.is_file():
                        item_path = Path(entry.path)
                        if self.is_valid_document(item_path):
                            item_lower = item_path.name.lower()
                            matched_type = self._match_document_type(item_lower)
                            if matched_type == doc_type:
                                logger.info(f"[발견] {doc_name}: {item_path.name}")
                                found_items.append({
                                    'type': 'file',
                                    'name': item_path.name,
                                    'path': str(item_path.relative_to(project_path)),
                                    'full_path': str(item_path),
                                    'depth': depth,
                                    'doc_type': doc_type
                                })
                                total_found += 1
                                if total_found >= max_found:
                                    break
                            elif matched_type is None and self.verbose:
                                logger.debug(f"매칭 실패 - 파일: {item_path.name}, 예상 유형: {doc_type}")
                    elif entry.is_dir() and not self._should_skip_path(entry.path):
                        if self.verbose:
                            logger.debug(f"Found directory: {entry.path}")
                except Exception as item_error:
                    logger.error(f"항목 처리 중 오류 {entry.path}: {str(item_error)}")
                    continue

            # 아직 3개를 못 찾았다면 디렉토리 검색 (최대 10개 디렉토리만)
            if total_found < max_found:
                dir_entries = [
                    entry.path for entry in entries 
                    if entry.is_dir() and not self._should_skip_path(entry.path)
                ][:10]  # 최대 10개 디렉토리로 증가
                
                for dir_path in dir_entries:
                    if total_found >= max_found:
                        break
                        
                    sub_items = await self.search_document(
                        dir_path,
                        doc_type,
                        depth + 1,
                        max_found,
                        total_found
                    )
                    
                    if sub_items:
                        remaining = max_found - total_found
                        found_items.extend(sub_items[:remaining])
                        total_found += len(sub_items[:remaining])

            return found_items

        except Exception as e:
            logger.error(f"[오류] 검색 중 오류 발생: {str(e)}")
            return []

    async def process_single_project(self, project_id, department_code=None):
        """특정 프로젝트 및 부서 처리"""
        start_time = time.time()
        try:
            # 프로젝트 목록 읽기
            df_load_start = time.time()
            df = pd.read_csv(PROJECT_LIST_CSV, dtype={
                'department_code': str,
                'project_id': str
            })
            
            # 특정 프로젝트와 부서 찾기
            if department_code:
                project = df[(df['project_id'] == str(project_id)) & (df['department_code'] == str(department_code))]
            else:
                project = df[df['project_id'] == str(project_id)]
            
            if len(project) == 0:
                logger.error(f"프로젝트 ID {project_id}를 부서 {department_code}에서 찾을 수 없습니다.")
                return None
            
            # 지정된 부서가 있으면 해당 부서만 처리, 없으면 첫 번째 부서 처리
            row = project.iloc[0] if department_code else project.iloc[0]  # 부서 지정 시 해당 부서만, 없으면 첫 번째
            dept_code = row['department_code'].zfill(5)
            project_path = get_full_path(row['original_folder'], verbose=self.verbose)
            
            logger.info(f"\n=== 프로젝트 {project_id} 검색 시작 (부서: {dept_code}_{row['department_name']}) ===")
            
            # 각 문서 유형별로 검색 수행
            all_documents = {}
            search_start = time.time()
            for doc_type, info in DOCUMENT_TYPES.items():
                type_start = time.time()
                found_items = await self.search_document(project_path, doc_type, max_found=3)
                
                if found_items:  # 발견된 항목이 있을 때만 저장 및 로깅
                    all_documents[doc_type] = found_items[:3]  # 최대 3개로 확실히 제한
                    logger.info(f"{info['name']}: {len(found_items[:3])}개 발견 ({time.time() - type_start:.2f}초)")
            
            # 결과를 저장
            result = {
                'project_id': project_id,
                'department_code': dept_code,
                'department_name': str(row['department_name']),
                'project_name': str(row['project_name']),
                'project_path': str(project_path),
                'documents': all_documents,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'performance': {
                    'total_time': time.time() - start_time,
                    'search_time': time.time() - search_start,
                    'document_counts': {
                        doc_type: len(docs) for doc_type, docs in all_documents.items()
                    }
                }
            }
            
            # JSON 파일로 저장 (부서별로 별도 저장)
            json_path = os.path.join(self.projects_dir, f'{project_id}_{dept_code}.json')
            async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(result, ensure_ascii=False, indent=2))
            
            logger.info(f"\n=== 검색 완료 (부서: {dept_code}_{row['department_name']}, 소요 시간: {time.time() - start_time:.2f}초) ===")
            logger.info(f"- 발견된 문서 유형: {len(all_documents)}개")
            logger.info(f"- 총 발견 파일 수: {sum(len(docs) for docs in all_documents.values())}개")
            return result
                
        except Exception as e:
            logger.error(f"프로젝트 처리 중 오류 발생: {str(e)}")
            if self.verbose:
                logger.exception("상세 오류:")
            return None

    async def search_all_documents(self, project_id, department_code=None):
        """모든 문서 유형에 대한 검색 수행 (부서별 병렬 처리, audit_service와 호환성 보장)"""
        try:
            # 프로젝트 정보 조회
            project_info = await self.get_project_info(project_id, department_code)
            if not project_info:
                logger.error(f"프로젝트 ID {project_id}를 부서 {department_code}에서 찾을 수 없습니다.")
                return {
                    'documents': {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES},
                    'performance': {'search_time': 0, 'document_counts': {}}
                }
            
            project_path = project_info['original_folder']
            if not Path(project_path).exists():
                logger.error(f"프로젝트 경로를 찾을 수 없습니다: {project_path}")
                return {
                    'documents': {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES},
                    'performance': {'search_time': 0, 'document_counts': {}}
                }
            
            # 각 문서 유형별로 병렬 검색
            all_documents = {}
            search_start = time.time()
            
            tasks = [
                self.search_document(project_path, doc_type, max_found=3)
                for doc_type in DOCUMENT_TYPES.keys()
            ]
            
            results = await asyncio.gather(*tasks)
            
            for doc_type, found_items in zip(DOCUMENT_TYPES.keys(), results):
                all_documents[doc_type] = {
                    'exists': bool(found_items),
                    'details': found_items[:3]  # 최대 3개로 확실히 제한
                }
                if self.verbose and found_items:
                    logger.info(f"{DOCUMENT_TYPES[doc_type]['name']}: {len(found_items[:3])}개 발견 ({time.time() - search_start:.2f}초)")
            
            search_time = time.time() - search_start
            document_counts = {doc_type: len(all_documents[doc_type]['details']) for doc_type in all_documents}
            logger.info(f"\n전체 문서 검색 완료: {len([d for d in all_documents.values() if d['exists']])}개 유형 발견 ({search_time:.2f}초)")
            
            return {
                'documents': all_documents,
                'performance': {
                    'search_time': search_time,
                    'document_counts': document_counts
                }
            }
            
        except Exception as e:
            logger.error(f"문서 검색 중 오류 발생: {str(e)}")
            if self.verbose:
                logger.exception("상세 오류:")
            return {
                'documents': {doc_type: {'exists': False, 'details': []} for doc_type in DOCUMENT_TYPES},
                'performance': {'search_time': time.time() - search_start if 'search_start' in locals() else 0, 'document_counts': {}}
            }

    def clear_cache(self):
        """캐시 초기화"""
        self._cache.clear()
        self._dir_cache.clear()
        self._file_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        logger.info("Searcher cache cleared")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="프로젝트 문서 검색")
    parser.add_argument('--project-id', type=str, required=True, help="검색할 프로젝트 ID")
    parser.add_argument('--department-code', type=str, default=None, help="부서 코드 (예: 01010, 01030)")
    parser.add_argument('--verbose', action='store_true', help="상세 로그 출력")
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=== 프로젝트 문서 검색 시작 ===")
    searcher = ProjectDocumentSearcher(verbose=args.verbose)
    searcher.clear_cache()  # 캐시 초기화
    
    asyncio.run(searcher.process_single_project(args.project_id, args.department_code))
    
    logger.info("\n=== 검색 완료 ===")

# python search_project_data.py
# python search_project_data.py --project-id 20180076 --department-code 01010 --verbose
# python search_project_data.py --project-id 20240178 --department-code 06010 --verbose
# python search_project_data.py --project-id 20240178 --verbose