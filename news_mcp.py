import aiohttp
import asyncio
from typing import List, Dict, Any
import json
from datetime import datetime, timedelta

class NewsSearchMCP:
    def __init__(self):
        self.session = None
        self.base_urls = {
            'naver': 'https://openapi.naver.com/v1/search/news.json',
            'daum': 'https://dapi.kakao.com/v2/search/web'
        }
        
    async def initialize(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
            
    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None
            
    async def search_naver_news(self, query: str, display: int = 10) -> List[Dict[str, Any]]:
        """네이버 뉴스 검색 API를 사용하여 기사 검색"""
        headers = {
            'X-Naver-Client-Id': 'YOUR_NAVER_CLIENT_ID',
            'X-Naver-Client-Secret': 'YOUR_NAVER_CLIENT_SECRET'
        }
        
        params = {
            'query': query,
            'display': display,
            'sort': 'date'
        }
        
        async with self.session.get(self.base_urls['naver'], 
                                  headers=headers, 
                                  params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('items', [])
            return []
            
    async def search_daum_news(self, query: str, size: int = 10) -> List[Dict[str, Any]]:
        """다음 검색 API를 사용하여 기사 검색"""
        headers = {
            'Authorization': 'KakaoAK YOUR_KAKAO_API_KEY'
        }
        
        params = {
            'query': f'{query} site:news.daum.net',
            'size': size
        }
        
        async with self.session.get(self.base_urls['daum'], 
                                  headers=headers, 
                                  params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('documents', [])
            return []
            
    async def search_all_news(self, query: str, limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """모든 뉴스 소스에서 통합 검색"""
        await self.initialize()
        
        tasks = [
            self.search_naver_news(query, limit),
            self.search_daum_news(query, limit)
        ]
        
        results = await asyncio.gather(*tasks)
        
        return {
            'naver': results[0],
            'daum': results[1]
        }

# 사용 예시
async def main():
    news_mcp = NewsSearchMCP()
    try:
        results = await news_mcp.search_all_news("주식시장")
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        await news_mcp.close()

if __name__ == "__main__":
    asyncio.run(main()) 