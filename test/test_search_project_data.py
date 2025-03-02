# test/test_search_project_data.py
import pytest
import asyncio
from unittest.mock import patch
from my_flask_app.search_project_data import ProjectDocumentSearcher
from pathlib import Path
import os

@pytest.fixture
def searcher(tmp_path):
    # tmp_path를 NETWORK_BASE_PATH로 설정
    with patch('my_flask_app.search_project_data.NETWORK_BASE_PATH', str(tmp_path)):
        return ProjectDocumentSearcher(verbose=True)

@pytest.fixture
def mock_project_list(tmp_path):
    # 모의 project_list.csv 생성
    csv_content = (
        "department_code,department_name,project_id,project_name,original_folder\n"
        "01010,도로,20180076,영락공원 진입도로,01010_도로\\20180076\n"
    )
    csv_file = tmp_path / "project_list.csv"
    csv_file.write_text(csv_content)
    with patch('my_flask_app.search_project_data.PROJECT_LIST_CSV', str(csv_file)):
        yield csv_file

@pytest.mark.asyncio
async def test_search_project_success(searcher, tmp_path, mock_project_list):
    # 모의 프로젝트 폴더와 파일 생성
    project_path = tmp_path / "01010_도로" / "20180076"
    project_path.mkdir(parents=True)
    (project_path / "계약서.pdf").touch()

    # 검색 실행
    result = await searcher.search_project("20180076")
    
    # 결과 검증
    assert result is not None
    assert result["project_id"] == "20180076"
    assert result["department_code"] == "01010"
    assert result["documents"]["contract"]["exists"] is True
    assert len(result["documents"]["contract"]["details"]) == 1
    assert result["documents"]["contract"]["details"][0]["name"] == "계약서.pdf"

    # JSON 파일 확인
    json_path = tmp_path / "static" / "projects" / "01010_20180076.json"
    assert json_path.exists()
    with open(json_path, 'r', encoding='utf-8') as f:
        saved_data = json.load(f)
        assert saved_data["project_id"] == "20180076"

@pytest.mark.asyncio
async def test_search_project_not_found(searcher, tmp_path, mock_project_list):
    # 존재하지 않는 프로젝트 ID 테스트
    result = await searcher.search_project("99999999")
    assert result is None

@pytest.mark.asyncio
async def test_search_project_missing_path(searcher, tmp_path, mock_project_list):
    # 프로젝트 폴더가 없는 경우
    result = await searcher.search_project("20180076")
    assert result is None

if __name__ == "__main__":
    pytest.main(["-v"])
    
# pytest test/test_search_project_data.py -v
