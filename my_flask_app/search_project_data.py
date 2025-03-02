# /my_flask_app/search_project_data.py
import os
import asyncio
import aiofiles
import logging
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
from my_flask_app.config import PROJECT_LIST_CSV, NETWORK_BASE_PATH
from config_assets import DOCUMENT_TYPES
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

KEYWORD_PATTERNS = {
    doc_type: re.compile('|'.join(map(re.escape, info['keywords'])), re.IGNORECASE)
    for doc_type, info in DOCUMENT_TYPES.items()
}

class ProjectDocumentSearcher:
    def __init__(self, verbose=False):
        self.projects_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'projects')
        os.makedirs(self.projects_dir, exist_ok=True)
        self.verbose = verbose

    async def _get_project_info(self, project_id):
        """프로젝트 ID로 정보 조회"""
        try:
            df = pd.read_csv(PROJECT_LIST_CSV, dtype={'department_code': str, 'project_id': str})
            project = df[df['project_id'] == str(project_id)]
            if project.empty:
                logger.error(f"Project ID {project_id} not found in {PROJECT_LIST_CSV}")
                return None
            
            row = project.iloc[0]  # 첫 번째 매칭 항목 사용
            project_path = os.path.join(NETWORK_BASE_PATH, str(row['original_folder']))
            return {
                'project_id': str(row['project_id']),
                'department_code': str(row['department_code']).zfill(5),
                'department_name': str(row['department_name']),
                'project_name': str(row['project_name']),
                'project_path': project_path
            }
        except Exception as e:
            logger.error(f"Error loading project info for {project_id}: {str(e)}")
            return None

    async def search_project(self, project_id):
        """프로젝트 ID로 검색하고 JSON 저장"""
        start_time = datetime.now()
        project_info = await self._get_project_info(project_id)
        if not project_info:
            return None

        project_path = project_info['project_path']
        if not Path(project_path).exists():
            logger.error(f"Project path not found: {project_path}")
            return None

        logger.info(f"Searching project {project_id}")
        documents = {}
        tasks = [
            asyncio.create_task(self._search_document_type(project_path, doc_type))
            for doc_type in DOCUMENT_TYPES.keys()
        ]
        results = await asyncio.gather(*tasks)

        for doc_type, found_items in zip(DOCUMENT_TYPES.keys(), results):
            documents[doc_type] = {
                'exists': bool(found_items),
                'details': found_items[:3]  # 최대 3개 제한
            }

        result = {
            'project_id': project_id,
            'department_code': project_info['department_code'],
            'department_name': project_info['department_name'],
            'project_name': project_info['project_name'],
            'project_path': project_path,
            'documents': documents,
            'timestamp': start_time.strftime('%Y-%m-%d %H:%M:%S')
        }

        # JSON 저장
        json_path = os.path.join(self.projects_dir, f"{project_info['department_code']}_{project_id}.json")
        async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(result, ensure_ascii=False, indent=2))

        if self.verbose:
            logger.info(f"Saved search result to {json_path}")
        return result

    async def _search_document_type(self, project_path, doc_type, max_found=3):
        """특정 문서 유형 검색"""
        try:
            found_items = []
            for root, _, files in os.walk(project_path):
                for file in files[:max_found - len(found_items)]:
                    if len(found_items) >= max_found:
                        break
                    if KEYWORD_PATTERNS[doc_type].search(file.lower()):
                        found_items.append({
                            'type': 'file',
                            'name': file,
                            'full_path': os.path.join(root, file)
                        })
                if len(found_items) >= max_found:
                    break
            return found_items
        except Exception as e:
            logger.error(f"Error searching {doc_type} in {project_path}: {str(e)}")
            return []

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Search project documents by ID")
    parser.add_argument('--project-id', type=str, required=True, help="Project ID to search (e.g., 20180076)")
    parser.add_argument('--verbose', action='store_true', help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    searcher = ProjectDocumentSearcher(verbose=args.verbose)
    asyncio.run(searcher.search_project(args.project_id))

# python search_project_data.py --project-id 20180076 --verbose

# python search_project_data.py
# python search_project_data.py --project-id 20180076 --department-code 01010 --verbose
# python search_project_data.py --project-id 20240178 --department-code 06010 --verbose
# python search_project_data.py --project-id 20240178 --verbose