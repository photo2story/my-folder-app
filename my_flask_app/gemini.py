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
from config import GOOGLE_API_KEY, DISCORD_WEBHOOK_URL, DOCUMENT_TYPES, AUDIT_FILTERS
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

    def calculate_risk_score(self, missing_docs: tuple, status: str, contractor: str) -> int:
        """문서 누락, 상태, 주관사/비주관사에 따른 위험도 점수 계산 (오프라인)"""
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
        
        # 주관사/비주관사 기준
        required_docs = []
        if contractor == '주관사':
            required_docs = list(risk_weights.keys())  # 모든 문서 필요
        elif contractor == '비주관사':
            required_docs = ['contract', 'agreement', 'deliverable1', 'deliverable2']  # 최소 필요 문서

        # 진행/준공 기준
        if status == '준공':
            required_docs = list(risk_weights.keys())  # 모든 문서 필요
        elif status == '진행':
            required_docs = ['contract', 'specification', 'initiation', 'agreement', 'budget']  # 우선 필요 문서

        # 누락된 문서에 따른 위험도 계산 (실제 존재 확인)
        for doc in missing_docs:
            if doc in risk_weights and doc in required_docs:
                base_score -= risk_weights[doc]
        
        return max(0, min(100, base_score))  # 0~100 범위로 제한

    def _generate_cache_key(self, project_id: str, documents: dict) -> str:
        """캐시 키 생성 (문서 상태 해시 포함, 날짜 제거)"""
        docs_hash = hashlib.md5(str(documents).encode()).hexdigest()
        return f"{project_id}_{docs_hash}"

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

            # project_id, department, status, contractor, project_name, documents, csv_data 추출
            project_id = project_data.get('project_id', 'Unknown')
            department = project_data.get('department', 'Unknown')
            status = project_data.get('status', '진행')
            contractor = project_data.get('contractor', '주관사')
            project_name = project_data.get('project_name', 'Unknown')
            documents = project_data.get('documents', {})
            csv_data = project_data.get('csv_data', {})

            # 디버깅: Gemini AI에 전달되는 데이터 출력
            logger.debug(f"Gemini AI에 전달되는 project_data: {project_data}")
            logger.debug(f"Gemini AI에 전달되는 documents: {documents}")
            logger.debug(f"Gemini AI에 전달되는 CSV 데이터: {csv_data}")

            # 문서 상태 분석 (documents가 딕셔너리 형식이 아닌 경우 처리)
            if not isinstance(documents, dict):
                logger.error(f"Invalid documents format: {documents}")
                documents = {}  # 빈 딕셔너리로 초기화

            existing_docs = []
            missing_docs = []
            processed_documents = {}

            # 모든 DOCUMENT_TYPES를 순회하며 처리
            for doc_type in DOCUMENT_TYPES.keys():
                doc_data = documents.get(doc_type, [])
                if isinstance(doc_data, list):  # 리스트로 반환된 경우
                    processed_documents[doc_type] = {
                        'exists': len(doc_data) > 0,
                        'details': [{'name': path} for path in doc_data if isinstance(path, str)]
                    }
                elif isinstance(doc_data, dict):  # 이미 딕셔너리로 반환된 경우
                    processed_documents[doc_type] = {
                        'exists': doc_data.get('exists', False),
                        'details': [{'name': path} for path in doc_data.get('details', []) if isinstance(path, (str, dict))]
                    }
                else:
                    logger.warning(f"Unknown documents format for {doc_type}: {doc_data}")
                    processed_documents[doc_type] = {
                        'exists': False,
                        'details': []
                    }

                doc_name = DOCUMENT_TYPES.get(doc_type, {}).get('name', doc_type)
                if processed_documents[doc_type]['exists']:
                    files_count = len(processed_documents[doc_type]['details'])
                    existing_docs.append(f"{doc_name} ({files_count}개)")
                else:
                    missing_docs.append(f"{doc_name} (0개)")  # 발견되지 않은 문서는 0개로 표시

            # 디버깅: 처리된 documents 출력
            logger.debug(f"Processed documents for project {project_id}: {processed_documents}")

            # 오프라인 위험도 계산 (상태와 주관사/비주관사 반영)
            risk_score = self.calculate_risk_score(tuple(doc_type for doc_type, info in processed_documents.items() if not info['exists']), status, contractor)

            # 상세화된 프롬프트 (AUDIT_FILTERS, 주관사/비주관사, 진행/준공 기준 반영)
            prompt = f"""
프로젝트 {project_id} 문서 분석:
부서: {department}
프로젝트명: {project_name}
상태: {status}
주관사 여부: {contractor}

현황:
- 확인된 문서: {', '.join(existing_docs) if existing_docs else '없음'}
- 누락된 문서: {', '.join(missing_docs) if missing_docs else '없음'}
- 기본 위험도: {risk_score}/100

다음 기준을 바탕으로 상세히 평가해주세요:
1. 현재 문서화 상태 (상/중/하) 및 그 이유
   - 주관사: 모든 문서 유형(계약서, 과업지시서, 착수계, 공동도급협정, 실행예산, 성과품(보고서), 성과품(도면), 준공계, 실적증명, 용역수행평가)이 100% 완비되어야 함 (위험도 0/100).
   - 비주관사: 계약서, 공동도급협정, 성과품(보고서/도면)만 필요 (위험도 50/100 이하).
   - 진행: 계약서, 과업지시서, 착수계, 공동도급협정, 실행예산이 우선적으로 존재해야 하며, 나머지 문서는 부분적으로 누락 가능 (위험도 30~70/100).
   - 준공: 모든 문서 유형이 완비되어야 함 (위험도 0/100).

2. 가장 시급한 보완 필요 문서와 이유
3. 위험도 점수 조정 필요성 (있다면, 구체적인 개선 방안 제시)

간단명료하고 구체적으로 답변해주세요.
"""
            cache_key = self._generate_cache_key(project_id, processed_documents)
            if cache_key in self._cache:
                logger.debug(f"캐시에서 결과 반환: {cache_key}")
                return self._cache[cache_key]

            # Gemini API 호출
            response_text = await self._call_gemini_with_retry(prompt)
            
            analysis = f"""문서 분석 결과 ({datetime.now().strftime('%Y-%m-%d %H:%M')}):
{response_text}

요약:
- 확인된 문서: {len([d for d in existing_docs if '(0개)' not in d])}개 유형
- 누락된 문서: {len([d for d in missing_docs if '(0개)' in d])}개 유형
- 기본 위험도: {risk_score}/100
"""
            # 캐시 저장 (TTL 24시간 설정)
            self._cache[cache_key] = analysis
            asyncio.create_task(self._clear_cache_after_delay(cache_key, 24 * 60 * 60))  # 24시간 후 캐시 삭제

            # Discord 알림 (선택적, 에러 처리 추가)
            if DISCORD_WEBHOOK_URL:
                try:
                    notification = f"🔍 프로젝트 {project_id} 분석 완료 (위험도: {risk_score}/100)"
                    async with session.post(DISCORD_WEBHOOK_URL, json={'content': notification}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        await resp.read()
                except Exception as e:
                    logger.error(f"Discord 알림 실패: {str(e)}")

            logger.info(f"프로젝트 {project_id} 분석 완료, 위험도: {risk_score}/100")
            return analysis

        except Exception as e:
            error_msg = f"AI 분석 오류: {str(e)}"
            logger.error(error_msg)
            if DISCORD_WEBHOOK_URL:
                try:
                    async with session.post(DISCORD_WEBHOOK_URL, json={'content': f"❌ {error_msg}"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
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
            'department': '도로',
            'project_name': '20180076 영락공원 진입도로 개설공사 외 4개소 기본 및 실시설계용역',
            'status': '진행',
            'contractor': '주관사',
            'documents': {
                'contract': {'exists': True, 'details': [{'name': '00 계약관련.zip'}, {'name': '191223_변경계약서(1차).pdf'}, {'name': '200506_변경계약서(2차).pdf'}]},
                'specification': {'exists': True, 'details': [{'name': '00-과업별 연락처 현황-ver9.xls'}, {'name': '과업 추진할사항 및 메모사항(2022.07.18).hwp'}, {'name': '20180533106-00_1527228162532_과업지시서(영락공원 진입도로등 5개소)-기본및실시설계.hwp'}]},
                'initiation': {'exists': True, 'details': [{'name': '180624 설계내역서(낙찰)-착수.xls'}, {'name': '착수계(영락공원 진입도로)_18년6월26일 착수.pdf'}, {'name': '착수계.hwp'}]},
                'agreement': {'exists': True, 'details': [{'name': '업무분담합의서(영락공원).pdf'}]},
                'budget': {'exists': True, 'details': [{'name': '2018076_영락공원 실행예산.pdf'}, {'name': '231109 실행예산서 2차(영락공원).pdf'}, {'name': '231124 실행예산서 4차(영락공원).pdf'}]},
                'deliverable1': {'exists': True, 'details': [{'name': '최종 성과품 제본 현황.hwp'}, {'name': '00 보고서_표지(전기).hwp'}, {'name': '01 전기보고서.hwp'}]},
                'deliverable2': {'exists': True, 'details': [{'name': '영락공원진입도로 전기설계도면.pdf'}, {'name': '신창2제 전기설계도면.pdf'}, {'name': '전기설계도면(동구청~조대사거리).pdf'}]},
                'completion': {'exists': True, 'details': [{'name': '외주비 청구 필수서류(기성,준공 검사원)_영락공원.hwp'}, {'name': '외주비 청구 필수서류(기성,준공 검사원)_영락공원-아이로드작성.pdf'}, {'name': '외주비 청구 필수서류(기성,준공 검사원)_영락공원.hwp'}]},
                'certificate': {'exists': True, 'details': [{'name': '실적증명서_영락공원(최종).hwp'}, {'name': '실적증명서_영락공원(최종)_수성.hwp'}, {'name': '실적증명서_영락공원(최종)_수성2.hwp'}]},
                'evaluation': {'exists': False, 'details': []}  # 용역수행평가 누락
            },
            'csv_data': {
                'Depart_ProjectID': '01010_20180076',
                'Depart': '도로',
                'Status': '진행',
                'Contractor': '주관사',
                'ProjectName': '20180076 영락공원 진입도로 개설공사 외 4개소 기본 및 실시설계용역',
                'contract_exists': 1,
                'contract_count': 3,
                'specification_exists': 1,
                'specification_count': 3,
                'initiation_exists': 1,
                'initiation_count': 3,
                'agreement_exists': 1,
                'agreement_count': 1,
                'budget_exists': 1,
                'budget_count': 3,
                'deliverable1_exists': 1,
                'deliverable1_count': 3,
                'deliverable2_exists': 1,
                'deliverable2_count': 3,
                'completion_exists': 1,
                'completion_count': 3,
                'certificate_exists': 1,
                'certificate_count': 3,
                'evaluation_exists': 0,
                'evaluation_count': 0
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