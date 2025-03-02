# my_flask_app/tests/test_search_project_data.py
import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from search_project_data import ProjectDocumentSearcher
from pathlib import Path
import pandas as pd
import os
from config import PROJECT_LIST_CSV, NETWORK_BASE_PATH, STATIC_DATA_PATH

# 로깅 설정 (테스트용으로 최소화)
@pytest.fixture
def searcher(tmp_path):
    # 모의 경로 설정
    mock_static_data = tmp_path / "static" / "data"
    mock_static_data.mkdir(parents=True)
    mock_projects = tmp_path / "static" / "projects"
    mock_projects.mkdir(parents=True)

    with patch('search_project_data.PROJECT_LIST_CSV', str(mock_static_data / "project_list.csv")):
        with patch('search_project_data.NETWORK_BASE_PATH', str(tmp_path)):
            with patch('search_project_data.STATIC_DATA_PATH', str(tmp_path / "static")):
                return ProjectDocumentSearcher(verbose=True)

@pytest.fixture
def mock_project_list(tmp_path):
    # 모의 project_list.csv 생성
    csv_content = (
        "department_code,department_name,project_id,project_name,original_folder\n"
        "01010,도로,20180076,영락공원 진입도로,01010_도로\\20180076\n"
    )
    csv_file = tmp_path / "static" / "data" / "project_list.csv"
    csv_file.parent.mkdir(parents=True)
    csv_file.write_text(csv_content)
    yield csv_file

@pytest.mark.asyncio
async def test_get_project_info_success(searcher, mock_project_list):
    """_get_project_info가 프로젝트 ID로 올바른 정보를 반환하는지 테스트"""
    project_info = await searcher._get_project_info("20180076")
    assert project_info is not None
    assert project_info["project_id"] == "20180076"
    assert project_info["department_code"] == "01010"
    assert project_info["project_name"] == "영락공원 진입도로"

@pytest.mark.asyncio
async def test_get_project_info_not_found(searcher, mock_project_list):
    """존재하지 않는 프로젝트 ID로 None 반환 테스트"""
    project_info = await searcher._get_project_info("99999999")
    assert project_info is None

@pytest.mark.asyncio
async def test_search_project_success(searcher, mock_project_list, tmp_path):
    """search_project가 프로젝트를 검색하고 JSON을 저장하는지 테스트"""
    # 모의 프로젝트 폴더와 파일 생성
    project_path = tmp_path / "01010_도로" / "20180076"
    project_path.mkdir(parents=True)
    (project_path / "계약서.pdf").touch()

    result = await searcher.search_project("20180076")
    assert result is not None
    assert result["project_id"] == "20180076"
    assert result["documents"]["contract"]["exists"] is True
    assert len(result["documents"]["contract"]["details"]) == 1
    assert result["documents"]["contract"]["details"][0]["name"] == "계약서.pdf"

    # JSON 파일 확인 (STATIC_DATA_PATH 기준)
    json_path = tmp_path / "static" / "projects" / "01010_20180076.json"
    assert json_path.exists()
    with open(json_path, 'r', encoding='utf-8') as f:
        saved_data = json.load(f)
        assert saved_data["project_id"] == "20180076"

@pytest.mark.asyncio
async def test_search_project_not_found(searcher, mock_project_list):
    """존재하지 않는 프로젝트 ID로 None 반환 테스트"""
    result = await searcher.search_project("99999999")
    assert result is None

@pytest.mark.asyncio
async def test_search_document_success(searcher, tmp_path):
    """search_document가 특정 문서 유형을 찾는지 테스트"""
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "계약서.pdf").touch()

    with patch('search_project_data.NETWORK_BASE_PATH', str(tmp_path)):
        result = await searcher.search_document(str(project_path), "contract")
        assert len(result) == 1
        assert result[0]["name"] == "계약서.pdf"
        assert result[0]["doc_type"] == "contract"

@pytest.mark.asyncio
async def test_clear_cache(searcher):
    """clear_cache가 캐시를 초기화하는지 테스트"""
    searcher._cache["test"] = "data"
    searcher._dir_cache["test_dir"] = "data"
    searcher._file_cache["test_file"] = "data"
    searcher.cache_hits = 5
    searcher.cache_misses = 3

    searcher.clear_cache()
    assert len(searcher._cache) == 0
    assert len(searcher._dir_cache) == 0
    assert len(searcher._file_cache) == 0
    assert searcher.cache_hits == 0
    assert searcher.cache_misses == 0
    
# # pytest test/test_search_project_data.py -v