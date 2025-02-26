# my-flask-app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Google API 설정
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')  # .env 파일에서 API 키를 가져옴

# 프로젝트 루트 경로 (app.py 기준 상위 디렉토리)
PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
STATIC_DATA_PATH = os.path.join(PROJECT_ROOT, 'static', 'data')
STATIC_IMAGES_PATH = os.path.join(PROJECT_ROOT, 'static', 'images')
PROJECT_LIST_CSV = os.path.join(STATIC_DATA_PATH, 'project_list.csv')
DEPART_LIST_PATH = os.path.join(STATIC_DATA_PATH, 'depart_list.csv')  # 부서 목록 CSV 경로 추가
# 네트워크 드라이브 경로 (Z:로 변경)
NETWORK_BASE_PATH = r"Z:"  # Z: 드라이브 네트워크 경로 변경

# Discord 설정
# 환경 변수
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# 검색 대상 문서 유형
DOCUMENT_TYPES = {
    'contract': {'name': '계약서', 'keywords': ['계약서', 'contract']},
    'specification': {'name': '과업지시서', 'keywords': ['과업지시서', '과업지시', '내용서', 'specification']},
    'initiation': {'name': '착수계', 'keywords': ['착수계', '착수', 'initiation']},
    'agreement': {'name': '공동도급협정', 'keywords': ['분담', '협정','협약', 'agreement']},
    'budget': {'name': '실행예산', 'keywords': ['실행예산', '실행' 'budget']},
    'deliverable': {'name': '성과품', 'keywords': ['성과품', 'deliverable']},
    # 'final_deliverable': {'name': '최종성과품', 'keywords': ['최종성과품', 'final deliverable']},
    'completion': {'name': '준공계', 'keywords': ['준공계', 'completion']},
    'evaluation': {'name': '용역수행평가', 'keywords': ['용역수행평가', '용역수행', 'evaluation']},
    'certificate': {'name': '실적증명', 'keywords': ['실적증명', '증명', 'certificate']}
}
# python config.py

