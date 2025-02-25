# my-flask-app/config.py
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd
import pytz
import pandas_market_calendars as mcal
import yfinance as yf
# from config_assets import PROJECTS  # STOCKS를 별도의 파일에서 가져옴
# STOCKS = config_asset.STOCKS (import하여 이미 정의됨)


load_dotenv()

# Discord configuration
DISCORD_APPLICATION_TOKEN = os.getenv('DISCORD_APPLICATION_TOKEN', 'your_token_here')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', 'your_channel_id_here'))
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', 'your_webhook_url_here')


# 프로젝트 루트 경로 설정
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# static/images 폴더 경로 설정 (프로젝트 루트 기준)
STATIC_IMAGES_PATH = os.path.join(PROJECT_ROOT, 'static', 'images')

# static/data 폴더 경로 설정 (프로젝트 루트 기준)
STATIC_DATA_PATH = os.path.join(PROJECT_ROOT, 'static', 'data')


# depart_list.csv 파일 경로 설정
DEPART_LIST_PATH = os.path.join(STATIC_DATA_PATH, 'depart_list.csv')



def is_gemini_analysis_complete(ticker):
    report_file_path = os.path.join(STATIC_IMAGES_PATH, f'report_{project}.txt')
    
    if not os.path.exists(report_file_path):
        return False
    
    try:
        with open(report_file_path, 'r', encoding='utf-8') as file:
            first_line = file.readline().strip()
            today_date_str = datetime.now().strftime('%Y-%m-%d')
            
            if today_date_str in first_line:
                return True
            else:
                return False
    except Exception as e:
        print(f"Error reading report file for {ticker}: {e}")
        return False
    


def is_cache_valid(cache_file, start_date, end_date):
    """
    캐시 파일의 유효성을 검사합니다:
    """


# 이 함수들을 봇의 다른 부분에서 호출하여 유효성을 검토할 수 있습니다.
if __name__ == '__main__':
    # 분석할 프로젝트 설정
    project = '20230050'
    deliverables_analysis_complete = is_deliverables_analysis_complete(project)
    gemini_analysis_complete = is_gemini_analysis_complete(project)
    print(f"Deliverables analysis complete for {project}: {deliverables_analysis_complete}")
    print(f"Gemini analysis complete for {project}: {gemini_analysis_complete}")
    
# python config.py

