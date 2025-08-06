# /my_flask_app/config.py
import os
from pathlib import Path  # Path 클래스를 사용하기 위해 pathlib 모듈 임포트
import logging
from dotenv import load_dotenv
from config_assets import AUDIT_FILTERS, AUDIT_FILTERS_depart, DOCUMENT_TYPES

load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Google API 설정
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')

# API 키 설정
TAVILY_API_KEY = os.getenv('TAVILY_API', '')
BRAVE_API_KEY = os.getenv('BRAVE_API', '')

# 프로젝트 루트 경로
PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
STATIC_PATH = os.path.join(PROJECT_ROOT, 'static')
STATIC_DATA_PATH = os.path.join(PROJECT_ROOT, 'static', 'data')
STATIC_IMAGES_PATH = os.path.join(PROJECT_ROOT, 'static', 'images')
PROJECT_LIST_CSV = os.path.join(STATIC_DATA_PATH, 'project_list.csv')
DEPART_LIST_PATH = os.path.join(STATIC_DATA_PATH, 'depart_list.csv')
AUDIT_TARGETS_CSV = os.path.join(STATIC_DATA_PATH, 'audit_targets.csv')  # 감사 대상 CSV 경로 추가
CONTRACT_STATUS_CSV = os.path.join(STATIC_DATA_PATH, 'contract_status.csv')
RESULTS_DIR = os.path.join(STATIC_PATH, 'results')

# 네트워크 드라이브 설정 (캐싱)
_NETWORK_DRIVE_CACHE = None
_PATH_CACHE = {}

def get_network_drive(verbose=False):
    """사용 가능한 네트워크 드라이브 찾기 (캐싱 적용)"""
    global _NETWORK_DRIVE_CACHE
    
    if _NETWORK_DRIVE_CACHE is not None:
        return _NETWORK_DRIVE_CACHE

    # 기본값 설정
    _NETWORK_DRIVE_CACHE = 'T:'
    
    if verbose:
        drives = ['T:', 'Z:', 'Y:', 'X:', 'U:']
        for drive in drives:
            try:
                if os.path.exists(drive):
                    _NETWORK_DRIVE_CACHE = drive
                    logger.debug(f"Found network drive: {drive}")
                    break
            except Exception:
                continue
        
        if _NETWORK_DRIVE_CACHE == 'T:':
            logger.warning("No network drive found, using default T:")
    
    return _NETWORK_DRIVE_CACHE

def get_full_path(relative_path, check_exists=False, verbose=False):
    """상대 경로를 절대 경로로 변환하되, 네트워크 조회를 최소화"""
    if not relative_path:
        return None
    
    cache_key = str(relative_path)
    if cache_key in _PATH_CACHE:
        return _PATH_CACHE[cache_key]
    
    drive = get_network_drive(verbose=False)  # verbose를 False로 고정
    
    if ':' in relative_path:
        _, path = relative_path.split(':', 1)
        full_path = f"{drive}{path}"
    else:
        full_path = os.path.join(drive, relative_path)

    # 경로 정규화 (실제 파일 시스템 접근 없이)
    full_path = str(Path(full_path))
    
    # 네트워크 드라이브 확인 최소화
    if check_exists and verbose:  # check_exists가 True이고 verbose가 True일 때만 확인
        if not os.path.exists(full_path):
            logger.warning(f"Path does not exist: {full_path}")

    _PATH_CACHE[cache_key] = full_path
    if verbose:
        logger.debug(f"Converted path: {relative_path} -> {full_path}")
    
    return full_path

def clear_path_cache():
    """경로 캐시 초기화"""
    global _PATH_CACHE, _NETWORK_DRIVE_CACHE
    _PATH_CACHE = {}
    _NETWORK_DRIVE_CACHE = None
    logger.info("Path cache cleared")

# 네트워크 드라이브 초기화 (시작 시 한 번만)
NETWORK_BASE_PATH = get_network_drive()

# Discord 설정
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# MCP 서버 설정
MCP_SERVERS = {
    "tavily-mcp": {
        "command": "npx",
        "args": ["-y", "tavily-mcp@0.1.2"],
        "env": {
            "TAVILY_API_KEY": TAVILY_API_KEY
        }
    },
    "brave-search": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {
            "BRAVE_API_KEY": BRAVE_API_KEY
        }
    },
    "sequential-thinking": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
}

# 감사 대상 필터링 설정 (config_assets에서 가져옴)
# config_assets에서 정의된 AUDIT_FILTERS와 AUDIT_FILTERS_depart를 사용