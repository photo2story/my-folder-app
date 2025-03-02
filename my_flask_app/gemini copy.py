# -*- coding: utf-8 -*-

# my_flask_app/gemini.py
import google.generativeai as genai
import os
import asyncio
import hashlib
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict
from functools import lru_cache
from config import GOOGLE_API_KEY, DISCORD_WEBHOOK_URL, DOCUMENT_TYPES
import requests
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Gemini 설정
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 캐시 및 rate limit 설정
_analysis_cache = {}
_rate_limit = asyncio.Semaphore(5)  # Gemini API 제한에 맞춰 조정 (초당 5건 가정)
_last_request_time = {}
MIN_REQUEST_INTERVAL = 0.2  # 초당 5개 요청에 맞춘 간격
MAX_RETRIES = 3  # 재시도 횟수

class DocumentAnalyzer:
    def __init__(self):
        self._session = None
        self._cache = {}
        self._last_request_time = {}  # 인스턴스 속성으로 변경
        
    async def get_session(self):
        """비동기 HTTP 세션 관리"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    @lru_cache(maxsize=1000)
    def calculate_risk_score(self, missing_docs: tuple) -> int:
        """문서 누락에 따른 위험도 점수 계산 (오프라인)"""
        base_score = 100
        risk_weights = {
            'contract': 30,    # 계약서
            'specification': 25,  # 과업지시서
            'budget': 20,      # 실행예산
            'completion': 15,   # 준공계
            'certificate': 10,  # 실적증명
            'evaluation': 5,    # 용역수행평가
            'initiation': 5,    # 착수계
            'agreement': 5,     # 공동도급협정
            'deliverable1': 5,  # 성과품(보고서)
            'deliverable2': 5   # 성과품(도면)
        }
        
        for doc in missing_docs:
            if doc in risk_weights:
                base_score -= risk_weights[doc]
        
        return max(0, base_score)

    def _generate_cache_key(self, project_data: dict) -> str:
        """캐시 키 생성 (문서 상태 해시 포함, 날짜 제거)"""
        docs_hash = hashlib.md5(str(project_data['documents']).encode()).hexdigest()
        return f"{project_data['project_id']}_{docs_hash}"

    async def _wait_for_rate_limit(self):
        """Rate limit 준수 및 재시도 처리"""
        for attempt in range(MAX_RETRIES):
            async with _rate_limit:
                now = datetime.now()
                if self._last_request_time.get(os.getpid()):
                    elapsed = (now - self._last_request_time[os.getpid()]).total_seconds()
                    if elapsed < MIN_REQUEST_INTERVAL:
                        await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
                self._last_request_time[os.getpid()] = now
                return  # 성공 시 반환
            await asyncio.sleep(0.5 * (attempt + 1))  # 재시도 전 지연
        raise Exception("Rate limit 초과 또는 요청 실패")

    async def _call_gemini_with_retry(self, prompt: str, max_retries=MAX_RETRIES) -> str:
        """Gemini API 호출 재시도 로직"""
        for attempt in range(max_retries):
            try:
                await self._wait_for_rate_limit()
                response = await asyncio.to_thread(model.generate_content, prompt)
                return response.text
            except Exception as e:
                logger.error(f"Gemini API 호출 실패 (시도 {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # 재시도 전 지연
                else:
                    raise

    async def analyze_batch(self, projects: List[Dict]) -> List[Dict]:
        """프로젝트 배치 분석"""
        tasks = [self.analyze_with_gemini(project) for project in projects]
        return await asyncio.gather(*tasks)

    async def analyze_with_gemini(self, project_data: dict, session: aiohttp.ClientSession = None) -> str:
        """프로젝트 문서 분석을 수행"""
        try:
            # 세션 관리
            if session is None:
                session = await self.get_session()
                should_close = True
            else:
                should_close = False

            cache_key = self._generate_cache_key(project_data)
            if cache_key in self._cache:
                logger.debug(f"캐시에서 결과 반환: {cache_key}")
                return self._cache[cache_key]

            # 문서 상태 분석
            missing_docs = []
            existing_docs = []
            for doc_type, info in project_data['documents'].items():
                doc_name = DOCUMENT_TYPES[doc_type]['name']
                if info['exists']:
                    files_count = len(info['details'])
                    existing_docs.append(f"{doc_name} ({files_count}개)")
                else:
                    missing_docs.append(doc_type)

            # 오프라인 위험도 계산
            risk_score = self.calculate_risk_score(tuple(missing_docs))

            # 상세화된 프롬프트
            prompt = f"""
프로젝트 {project_data['project_id']} 문서 분석:
부서: {project_data['department']}

현황:
- 확인된 문서: {', '.join(existing_docs)}
- 누락된 문서: {', '.join([DOCUMENT_TYPES[d]['name'] for d in missing_docs])}
- 기본 위험도: {risk_score}/100

다음 사항을 상세히 평가해주세요:
1. 현재 문서화 상태 (상/중/하) 및 그 이유
2. 가장 시급한 보완 필요 문서와 이유
3. 위험도 점수 조정 필요성 (있다면, 구체적인 개선 방안 제시)

간단명료하고 구체적으로 답변해주세요.
"""
            # Gemini API 호출
            response_text = await self._call_gemini_with_retry(prompt)
            
            analysis = f"""문서 분석 결과 ({datetime.now().strftime('%Y-%m-%d %H:%M')}):
{response_text}

요약:
- 확인된 문서: {len(existing_docs)}개 유형
- 누락된 문서: {len(missing_docs)}개 유형
- 기본 위험도: {risk_score}/100
"""
            # 캐시 저장 (TTL 24시간 설정)
            self._cache[cache_key] = analysis
            asyncio.create_task(self._clear_cache_after_delay(cache_key, 24 * 60 * 60))  # 24시간 후 캐시 삭제

            # Discord 알림 (선택적, 에러 처리 추가)
            if DISCORD_WEBHOOK_URL:
                try:
                    notification = f"🔍 프로젝트 {project_data['project_id']} 분석 완료 (위험도: {risk_score})"
                    async with session.post(DISCORD_WEBHOOK_URL, json={'content': notification}) as resp:
                        await resp.read()
                except Exception as e:
                    logger.error(f"Discord 알림 실패: {str(e)}")

            logger.info(f"프로젝트 {project_data['project_id']} 분석 완료, 위험도: {risk_score}/100")
            return analysis

        except Exception as e:
            error_msg = f"AI 분석 오류: {str(e)}"
            logger.error(error_msg)
            if DISCORD_WEBHOOK_URL:
                try:
                    async with session.post(DISCORD_WEBHOOK_URL, json={'content': f"❌ {error_msg}"}) as resp:
                        await resp.read()
                except Exception as discord_e:
                    logger.error(f"Discord 에러 알림 실패: {str(discord_e)}")
            return error_msg

        finally:
            if should_close and session:
                await session.close()

    async def _clear_cache_after_delay(self, cache_key: str, delay_seconds: int):
        """지정된 시간 후 캐시 삭제"""
        await asyncio.sleep(delay_seconds)
        if cache_key in self._cache:
            del self._cache[cache_key]
            logger.debug(f"캐시 삭제: {cache_key}")

    def clear_cache(self):
        """캐시 초기화"""
        self._cache.clear()
        self.calculate_risk_score.cache_clear()
        logger.info("분석 캐시 초기화 완료")

    async def close(self):
        """리소스 정리"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("HTTP 세션 종료")

# 전역 인스턴스
analyzer = DocumentAnalyzer()

async def analyze_with_gemini(project_data: dict, session: aiohttp.ClientSession = None) -> str:
    """기존 인터페이스 유지를 위한 래퍼"""
    return await analyzer.analyze_with_gemini(project_data, session)

def clear_analysis_cache():
    """기존 인터페이스 유지를 위한 래퍼"""
    analyzer.clear_cache()

# 테스트 코드
if __name__ == "__main__":
    async def test():
        # 실제 project_id="20180076" 데이터로 테스트
        test_data = {
            'project_id': '20180076',
            'department': '01010_도로',  # 또는 '01010_도로' 등
            'documents': {
                'contract': {'exists': True, 'details': [
                    {'name': '00 계약관련.zip'}, {'name': '191223_변경계약서(1차).pdf'}, {'name': '200506_변경계약서(2차).pdf'}
                ]},
                'specification': {'exists': False, 'details': []},  # 과업지시서 누락
                'initiation': {'exists': True, 'details': [
                    {'name': '착수계(영락공원 진입도로)_18년6월26일 착수.pdf'}, {'name': '착수계.hwp'}
                ]},
                'deliverable1': {'exists': True, 'details': [
                    {'name': '최종 성과품 제본 현황.hwp'}, {'name': '영락공원외4지구지반조사보고서.zip'}, 
                    {'name': '측량보고서-영락공원 진입도로개설공사 외4개소 기본 및 실시설계용역.zip'}
                ]},
                'deliverable2': {'exists': True, 'details': [
                    {'name': '동구청~조대사거리 설계도면.pdf'}
                ]},
                'completion': {'exists': True, 'details': [
                    {'name': '4.03.04 영락공원외 4개소 준공계.zip'}, {'name': '4.03.04 준공계.zip'}, {'name': '영락공원 준공계 공문.pdf'}
                ]},
                'certificate': {'exists': True, 'details': [
                    {'name': '실적증명서_영락공원(최종).hwp'}, {'name': '실적증명서_영락공원(최종)_수성.hwp'}, 
                    {'name': '실적증명서_영락공원(최종)_수성2.hwp'}
                ]}
            }
        }
        
        try:
            result = await analyze_with_gemini(test_data)
            logger.info(result)
        except Exception as e:
            logger.error(f"테스트 실패: {str(e)}")
        finally:
            await analyzer.close()

    asyncio.run(test())
# python gemini.py
 