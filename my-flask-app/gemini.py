# -*- coding: utf-8 -*-

# gemini.py

import os
import sys
import pandas as pd
import requests
from dotenv import load_dotenv
import google.generativeai as genai
import shutil
import asyncio
from datetime import datetime
import logging
import config

# 로깅 설정을 간단하게
logging.basicConfig(level=logging.WARNING)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from git_operations import move_files_to_images_folder

# 프로젝트 루트 경로 설정
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# static/images 폴더 경로 설정 (프로젝트 루트 기준)
STATIC_IMAGES_PATH = os.path.join(PROJECT_ROOT, 'static', 'images')
STATIC_DATA_PATH = os.path.join(PROJECT_ROOT, 'static', 'data')

# 기타 CSV 파일 경로 설정
CSV_PATH = os.path.join(STATIC_IMAGES_PATH, 'stock_market.csv')
DEPART_LIST_PATH = os.path.join(config.STATIC_DATA_PATH, 'depart_list.csv')

# 환경 변수 로드
load_dotenv()
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

# Google Generative AI 설정
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
# model = genai.GenerativeModel(
# model_name="gemini-1.5-flash-latest",
# generation_config=generation_config,
# )


# CSV 파일에서 티커 정보를 읽어옴

# CSV 파일을 다운로드 대신 로컬 폴더에서 찾는 함수
def download_csv(ticker):
    # GitHub 대신 로컬 폴더 경로에서 CSV 파일을 찾음
    ticker_vs_voo_path = os.path.join(STATIC_IMAGES_PATH, f'result_VOO_{ticker}.csv')
    simplified_ticker_path = os.path.join(STATIC_IMAGES_PATH, f'result_{ticker}.csv')

    # 파일이 존재하는지 확인
    if os.path.exists(ticker_vs_voo_path) and os.path.exists(simplified_ticker_path):
        return True
    else:
        return False
    
# Relative Divergence CSV에서 티커 데이터를 읽음
def get_relative_divergence_data(ticker):
    if not os.path.exists(RELATIVE_DIVERGENCE_CSV) or os.path.getsize(RELATIVE_DIVERGENCE_CSV) == 0:
        raise ValueError(f"{RELATIVE_DIVERGENCE_CSV} file is missing or empty.")

    df = pd.read_csv(RELATIVE_DIVERGENCE_CSV)
    row = df[df['Ticker'] == ticker]
    if row.empty:
        raise ValueError(f"{ticker} 데이터를 찾을 수 없습니다.")
    return row.iloc[0]


# 암호화폐 및 ETF 필터링
def get_detailed_financial_trends(ticker):
    # 암호화폐 및 ETF 목록
    non_financial_tickers = ['BTC-USD', 'QQQ', 'VOO', 'SPY', 'DOGE-USD', 'ETH-USD']

    # 만약 ticker가 non_financial_tickers에 포함되어 있으면 재무 분석을 건너뜀
    if ticker in non_financial_tickers:
        return f"No detailed financial trends available for {ticker}."

    stock = yf.Ticker(ticker)

    try:
        financials_quarterly = stock.quarterly_financials
        balance_sheet_quarterly = stock.quarterly_balance_sheet
    except Exception as e:
        print(f"Failed to retrieve financials for {ticker}: {e}")
        return f"Financial data not available for {ticker}."

    if 'Total Revenue' not in financials_quarterly.index or 'Gross Profit' not in financials_quarterly.index:
        print(f"'Total Revenue' or 'Gross Profit' not found for {ticker}")
        return f"No 'Total Revenue' or 'Gross Profit' data available for {ticker}."

    dates = list(financials_quarterly.columns[:5])

    # 5. Financial Information:
    financial_summary = "5. Financial Information:\n\n"

    # Revenue and Profitability 테이블
    financial_summary += "Revenue and Profitability:\n\n"
    financial_summary += "| Quarter | Revenue | Profit Margin |\n"
    financial_summary += "|---------|----------|---------------|\n"

    for date in dates:
        revenue = financials_quarterly.loc['Total Revenue'].get(date)
        gross_profit = financials_quarterly.loc['Gross Profit'].get(date)
        
        if pd.notna(revenue) and pd.notna(gross_profit) and revenue != 0:
            margin = (gross_profit / revenue) * 100
            revenue_b = revenue / 1e9
            financial_summary += f"| {date.strftime('%Y-%m-%d')} | ${revenue_b:.2f}B | {margin:.2f}% |\n"

    # Capital and Profitability 테이블
    financial_summary += "\nCapital and Profitability:\n\n"
    financial_summary += "| Quarter | Equity | ROE |\n"
    financial_summary += "|---------|---------|-----|\n"

    equity_fields = ['Total Stockholder Equity', 'Stockholders Equity', 'Total Equity']
    equity_data = None
    for field in equity_fields:
        if field in balance_sheet_quarterly.index:
            equity_data = balance_sheet_quarterly.loc[field]
            break

    if equity_data is not None:
        for date in dates:
            equity = equity_data.get(date)
            net_income = financials_quarterly.loc['Net Income'].get(date) if 'Net Income' in financials_quarterly.index else None
            
            if pd.notna(equity) and pd.notna(net_income) and equity != 0:
                roe = (net_income / equity) * 100
                equity_b = equity / 1e9
                financial_summary += f"| {date.strftime('%Y-%m-%d')} | ${equity_b:.2f}B | {roe:.2f}% |\n"

    return financial_summary


def format_earnings_text(earnings_data):
    if not earnings_data:
        return "No earnings data available."

    has_revenue = any(isinstance(entry, tuple) and len(entry) >= 4 for entry in earnings_data)

    if has_revenue:
        earnings_text = "| 날짜 | EPS | 매출 |\n|---|---|---|\n"
    else:
        earnings_text = "| 날짜 | EPS | 예상 EPS |\n|---|---|---|\n"

    for entry in earnings_data:
        if isinstance(entry, tuple):
            if has_revenue:
                if len(entry) == 5:
                    end, filed, actual_eps, revenue, estimated_revenue = entry
                    earnings_text += f"| {filed} | {actual_eps} | {revenue / 1e9:.2f} B$ |\n"
                elif len(entry) == 4:
                    end, filed, actual_eps, revenue = entry
                    earnings_text += f"| {filed} | {actual_eps} | {revenue / 1e9:.2f} B$ |\n"
            else:
                if len(entry) == 3:
                    end, actual_eps, estimated_eps = entry
                    earnings_text += f"| {end} | {actual_eps} | {estimated_eps} |\n"
                else:
                    earnings_text += "| Invalid data format |\n"
        else:
            earnings_text += "| Invalid data format |\n"
    
    return earnings_text

def get_alpha_beta_data(ticker):
    alpha_beta_path = os.path.join(STATIC_DATA_PATH, f"result_alpha_{ticker}.csv")

    # 파일 존재와 크기 확인
    if not os.path.exists(alpha_beta_path) or os.path.getsize(alpha_beta_path) == 0:
        print(f"Warning: Alpha/Beta data for {ticker} is missing or empty. Skipping Alpha/Beta analysis.")
        return "| No Alpha/Beta data available |"

    # 데이터프레임을 읽으면서 오류가 발생하면 기본 메시지 반환
    try:
        alpha_beta_df = pd.read_csv(alpha_beta_path)
        if alpha_beta_df.empty:
            print(f"Warning: Alpha/Beta data for {ticker} is empty. Skipping Alpha/Beta analysis.")
            return "| No Alpha/Beta data available |"
    except pd.errors.EmptyDataError:
        print(f"Warning: Alpha/Beta data for {ticker} is empty or corrupted. Skipping Alpha/Beta analysis.")
        return "| No Alpha/Beta data available |"

    # 데터가 존재할 때만 테이블 생성
    Alpha_Beta = "| Year       | CAGR | MDD  | Alpha | Beta | Cap(B) |\n|------------|------|------|-------|------|-------|\n"
    for _, row in alpha_beta_df.iterrows():
        year = row.get('Year', "N/A")
        cagr = f"{row.get('CAGR', 'N/A'):.1f}%" if 'CAGR' in row else "N/A"
        mdd = f"{row.get('MDD', 'N/A'):.1f}%" if 'MDD' in row else "N/A"
        alpha = f"{row.get('Alpha', 'N/A'):.1f}%" if 'Alpha' in row else "N/A"
        beta = f"{row.get('Beta', 'N/A'):.1f}" if 'Beta' in row else "N/A"
        market_cap = f"{row.get('Cap(B)', 'N/A'):.1f}" if 'Cap(B)' in row and pd.notna(row['Cap(B)']) else "N/A"

        Alpha_Beta += f"| {year:<10} | {cagr} | {mdd} | {alpha} | {beta} | {market_cap} |\n"
    
    return Alpha_Beta

    
async def analyze_with_gemini(ticker):
    try:
        start_message = f"Starting analysis for {ticker}"
        print(start_message)
        requests.post(DISCORD_WEBHOOK_URL, data={'content': start_message})

        if not download_csv(ticker):
            error_message = f'Error: The file for {ticker} does not exist.'
            print(error_message)
            requests.post(DISCORD_WEBHOOK_URL, data={'content': error_message})
            return

        company_name = ticker_to_name.get(ticker, "Unknown Company")
        
        # 로컬에서 CSV 파일을 읽어옴
        voo_file = os.path.join(STATIC_IMAGES_PATH, f'result_VOO_{ticker}.csv')
        simplified_file = os.path.join(STATIC_IMAGES_PATH, f'result_{ticker}.csv')

        # voo_file을 읽어옴
        try:
            df_voo = pd.read_csv(voo_file)
        except FileNotFoundError:
            print(f"{voo_file} 파일을 찾을 수 없습니다.")
            return

        # simplified_file을 읽어옴
        try:
            df_simplified = pd.read_csv(simplified_file)
        except FileNotFoundError:
            print(f"{simplified_file} 파일을 찾을 수 없습니다.")
            return

        final_rate = df_voo['rate'].iloc[-1]
        final_rate_vs = df_voo['rate_vs'].iloc[-1]
        Close = df_voo['Close'].iloc[-1]
        sma_5 = df_voo['sma05_ta'].iloc[-1]
        sma_20 = df_voo['sma20_ta'].iloc[-1]
        sma_60 = df_voo['sma60_ta'].iloc[-1]
        rsi = df_voo['rsi_ta'].iloc[-1]
        ppo = df_voo['ppo_histogram'].iloc[-1]
        
        # results_relative_divergence.csv 파일에서 데이터 가져오기
        try:
            divergence_data = get_relative_divergence_data(ticker)
            Alpha_Beta = get_alpha_beta_data(ticker)
        except ValueError as e:
            print(str(e))
            requests.post(DISCORD_WEBHOOK_URL, data={'content': f"Error fetching data: {e}"})
            return
        
        max_divergence = divergence_data['Max_Divergence']
        min_divergence = divergence_data['Min_Divergence']
        current_divergence = divergence_data['Divergence']
        relative_divergence = divergence_data['Relative_Divergence']
        delta_previous_relative_divergence = divergence_data['Delta_Previous_Relative_Divergence']
        
        if delta_previous_relative_divergence > 0:
            divergence_trend = "(+): 단기상승"
        else:
            divergence_trend = "(-): 단기하락"        
            
        Expected_Return = divergence_data['Expected_Return']
        Dynamic_Expected_Return = divergence_data['Dynamic_Expected_Return']
        
        # 포스트마켓 가격 가져오기
        post_market_price = await get_post_market_prices(ticker)
        
        # Alpha_Beta 데이터를 가져옴
        Alpha_Beta = get_alpha_beta_data(ticker)        
        
        earnings_text = "No earnings data available."  # 기본값 설정

        try:
            recent_earnings = get_recent_eps_and_revenue(ticker)
            if recent_earnings is None or all(entry[3] is None for entry in recent_earnings):
                print(f"Primary data source failed for {ticker}, attempting secondary source...")
                recent_earnings = get_recent_eps_and_revenue_fmp(ticker)
                if recent_earnings is not None:
                    earnings_text = format_earnings_text(recent_earnings)
            else:
                earnings_text = format_earnings_text(recent_earnings)
        except Exception as e:
            print(f"No earnings data found for {ticker}. Skipping earnings section. Error: {e}")

        print(f"Earnings Text for {ticker}: {earnings_text}")
        
        # 추가: Yahoo Financials 요약 정보
        financials_summary = get_detailed_financial_trends(ticker)
        print(f"Financials Summary for {ticker}: {financials_summary}")
    
        # 각 섹션의 데이터 유무를 확인
        has_earnings = earnings_text != "No earnings data available."
        has_financials = "No financial trends available" not in financials_summary
        is_crypto = ticker in ['DOGE-USD', 'BTC-USD', 'ETH-USD']

        # 조건부로 프롬프트 구성
        prompt_voo = f"""
        0) 레포트는 영어로 만들고, 간단한 숫자를 먼저 보여준 다음 간단한 분석을 추가해줘
        1) 제공된 자료의 수익율(rate)와 S&P 500(VOO)의 수익율(rate_vs)과 비교해서 이격된 정도를 알려줘 (간단하게 자료 맨마지막날의 누적수익율차이):
           리뷰할 주식티커명 = {ticker}: 회사이름 = {company_name}
           회사 개요 설명해줘(1줄로)
           리뷰주식의 누적수익률 = {final_rate}
           기준이 되는 비교주식(S&P 500, VOO)의 누적수익율 = {final_rate_vs}
           이격도 (max: {max_divergence}, min: {min_divergence}, 현재: {current_divergence}, 상대이격도: {relative_divergence})
           (상대이격도는 최소~최대 변동폭을 100으로 했을 때 현재의 위치를 나타내고 있어, 예를 들면 상대이격도 90이면 비교주식(S&P 500, VOO)보다 90% 더 우월하다는 것이 아니라 과거 데이터의 90%분위로 상단에 위치한다는 의미야)
           알파,베타 분석{Alpha_Beta} 표로 표시된 제공된 내용을 분석해주세요
        
        2) 제공된 자료의 최근 주가 변동(간단하게: 5일, 20일, 60일 이동평균 수치로):
           종가 = {Close} 
           Last-market = {post_market_price}
           5일이동평균 = {sma_5}
           20일이동평균 = {sma_20}
           60일이동평균 = {sma_60}

        3) 제공된 자료의 RSI, PPO 인덱스 지표와 Delta_Previous_Relative_Divergence,Expected_Return 을 분석해줘 (간단하게):
           RSI = {rsi}
           PPO = {ppo}
           최근(20일) 상대이격도 변화량 = {delta_previous_relative_divergence} {divergence_trend}
           만약, {post_market_price}가 크면 변동 이슈를 반영해줘(급반등,급하락) 
           기대수익(%) = {Dynamic_Expected_Return}, 현 시점부터 장기적으로(2년이상)적립 투자할 경우 예상되는 S&P 500대비 초과 수익률
        """

        # 실적 데이터가 있는 경우에만 추가
        if has_earnings and not is_crypto:
            prompt_voo += f"""
        4) Recent Earnings Analysis:
           {earnings_text} 표를 보여주고 제공된 분기별 데이터를 분석해줘
        5) 재무정보 = {financials_summary}  표를 보여주고 제공된 분기별 데이터를 분석해줘
        6) 종합적으로 분석해줘(이전 항목들의 요약)
        """

        print(f"Sending prompt to Gemini API for {ticker}")
        
        # Gemini API를 사용하여 분석 텍스트 생성
        response_ticker = model.generate_content(prompt_voo)
        
        # 분석 결과를 날짜와 함께 전체 report_text로 구성
        report_text = f"{datetime.now().strftime('%Y-%m-%d')} - Analysis Report\n" + response_ticker.text

        # report_text를 최대 2000자씩 5개의 파트로 분할
        part1 = report_text[:2000]
        part2 = report_text[2000:4000]
        part3 = report_text[4000:6000]
        part4 = report_text[6000:8000]
        part5 = report_text[8000:] if len(report_text) > 8000 else None

        # Discord로 첫 번째 파트 전송
        print(f"Sending part 1 to Discord for {ticker}")
        requests.post(DISCORD_WEBHOOK_URL, json={'content': part1})

        # Discord로 두 번째 파트 전송
        if part2:
            print(f"Sending part 2 to Discord for {ticker}")
            requests.post(DISCORD_WEBHOOK_URL, json={'content': part2})

        # Discord로 세 번째 파트 전송
        if part3:
            print(f"Sending part 3 to Discord for {ticker}")
            requests.post(DISCORD_WEBHOOK_URL, json={'content': part3})

        # Discord로 네 번째 파트 전송
        if part4:
            print(f"Sending part 4 to Discord for {ticker}")
            requests.post(DISCORD_WEBHOOK_URL, json={'content': part4})

        # Discord로 다섯 번째 파트 전송 (필요한 경우)
        if part5:
            print(f"Sending part 5 to Discord for {ticker}")
            requests.post(DISCORD_WEBHOOK_URL, json={'content': part5})
            
        # 파일로 전체 report_text 저장
        report_file = f'report_{ticker}.txt'
        destination_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static', 'images'))
        report_file_path = os.path.join(destination_dir, report_file)

        with open(report_file_path, 'w', encoding='utf-8') as file:
            file.write(report_text)

        # 필요한 파일들을 이동
        if os.path.exists(voo_file):
            shutil.move(voo_file, os.path.join(destination_dir, os.path.basename(voo_file)))
        await move_files_to_images_folder(report_file_path)

        return f'Gemini Analysis for {ticker} has been sent to Discord and saved as a text file.'

    except Exception as e:
        error_message = f"Error analyzing {ticker}: {str(e)}"
        print(error_message)
        requests.post(DISCORD_WEBHOOK_URL, data={'content': f"```\n{error_message}\n```"})
        raise
        

def setup_logging():
    # absl 로깅 초기화
    logging.root.removeHandler(absl.logging._absl_handler)
    absl.logging._warn_preinit_stderr = False

# 메인 코드 시작 전에 추가
if __name__ == '__main__':
    # setup_logging()
    # Top 10 티커 목록
    tickers = ['TSLA']
    
    print("Starting Gemini analysis for Top 10 tickers...")
    
    for ticker in tickers:
        print(f"\nProcessing {ticker}...")
        try:
            # Gemini 분석 실행
            result = asyncio.run(analyze_with_gemini(ticker))
            print(result)
            
            # 재무 정보 가져오기 (암호화폐가 아닌 경우에만)
            if ticker not in ['DOGE-USD', 'BTC-USD', 'ETH-USD']:
                financials_summary = get_detailed_financial_trends(ticker)
                print(f"Financial trends retrieved for {ticker}")
            
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            continue
    
    print("\nAll analyses completed.")

# python gemini.py
 