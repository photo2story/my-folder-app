# -*- coding: utf-8 -*-

# my-flask-app/gemini.py
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

# Gemini 설정
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 캐시 및 rate limit 설정
_analysis_cache = {}
_rate_limit = asyncio.Semaphore(10)  # 동시 요청 제한
_last_request_time = {}
MIN_REQUEST_INTERVAL = 0.1  # 초당 최대 10개 요청

class DocumentAnalyzer:
    def __init__(self):
        self._session = None
        self._cache = {}
        
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
            'evaluation': 10    # 용역수행평가
        }
        
        for doc in missing_docs:
            if doc in risk_weights:
                base_score -= risk_weights[doc]
        
        return max(0, base_score)

    def _generate_cache_key(self, project_data: dict) -> str:
        """캐시 키 생성 (문서 상태 해시 포함)"""
        docs_hash = hashlib.md5(str(project_data['documents']).encode()).hexdigest()
        return f"{project_data['project_id']}_{datetime.now().strftime('%Y%m%d')}_{docs_hash}"

    async def _wait_for_rate_limit(self):
        """Rate limit 준수"""
        async with _rate_limit:
            now = datetime.now()
            if self._last_request_time.get(os.getpid()):
                elapsed = (now - self._last_request_time[os.getpid()]).total_seconds()
                if elapsed < MIN_REQUEST_INTERVAL:
                    await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
            self._last_request_time[os.getpid()] = now

    async def analyze_batch(self, projects: List[Dict]) -> List[Dict]:
        """프로젝트 배치 분석"""
        tasks = [self.analyze_with_gemini(project) for project in projects]
        return await asyncio.gather(*tasks)

    async def analyze_with_gemini(self, project_data: Dict) -> str:
        """개별 프로젝트 분석"""
        try:
            cache_key = self._generate_cache_key(project_data)
            if cache_key in self._cache:
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

            # 간소화된 프롬프트
            prompt = f"""
프로젝트 {project_data['project_id']} 문서 분석:
부서: {project_data['department']}

현황:
- 확인된 문서: {', '.join(existing_docs)}
- 누락된 문서: {', '.join([DOCUMENT_TYPES[d]['name'] for d in missing_docs])}
- 기본 위험도: {risk_score}/100

다음 사항을 간단히 평가해주세요:
1. 현재 문서화 상태 (상/중/하)
2. 가장 시급한 보완 필요 문서
3. 위험도 점수 조정 필요성 (있다면)

간단명료하게 답변해주세요.
"""
            # Rate limit 관리
            await self._wait_for_rate_limit()

            # Gemini API 호출
            response = await asyncio.to_thread(model.generate_content, prompt)
            
            analysis = f"""문서 분석 결과 ({datetime.now().strftime('%Y-%m-%d %H:%M')}):
{response.text}

요약:
- 확인된 문서: {len(existing_docs)}개 유형
- 누락된 문서: {len(missing_docs)}개 유형
- 기본 위험도: {risk_score}/100
"""
            # 캐시 저장
            self._cache[cache_key] = analysis

            # Discord 알림 (선택적)
            if DISCORD_WEBHOOK_URL:
                session = await self.get_session()
                notification = f"🔍 프로젝트 {project_data['project_id']} 분석 완료 (위험도: {risk_score})"
                async with session.post(DISCORD_WEBHOOK_URL, json={'content': notification}) as resp:
                    await resp.read()

            return analysis

        except Exception as e:
            error_msg = f"AI 분석 오류: {str(e)}"
            if DISCORD_WEBHOOK_URL:
                session = await self.get_session()
                async with session.post(DISCORD_WEBHOOK_URL, json={'content': f"❌ {error_msg}"}) as resp:
                    await resp.read()
            return error_msg

    def clear_cache(self):
        """캐시 초기화"""
        self._cache.clear()
        self.calculate_risk_score.cache_clear()

    async def close(self):
        """리소스 정리"""
        if self._session and not self._session.closed:
            await self._session.close()

# 전역 인스턴스
analyzer = DocumentAnalyzer()

async def analyze_with_gemini(project_data: Dict) -> str:
    """기존 인터페이스 유지를 위한 래퍼"""
    return await analyzer.analyze_with_gemini(project_data)

def clear_analysis_cache():
    """기존 인터페이스 유지를 위한 래퍼"""
    analyzer.clear_cache()

# 테스트 코드
if __name__ == "__main__":
    async def test():
        test_data = {
            'project_id': '20230001',
            'department': '도로설계부',
            'documents': {
                'contract': {'exists': True, 'details': [{'name': 'contract1.pdf'}, {'name': 'contract2.pdf'}]},
                'specification': {'exists': False, 'details': []},
                'budget': {'exists': True, 'details': [{'name': 'budget.xlsx'}]}
            }
        }
        
        try:
            result = await analyze_with_gemini(test_data)
            print(result)
        finally:
            await analyzer.close()

    asyncio.run(test())

# python gemini.py
 