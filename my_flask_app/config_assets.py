# my_flask_app/config_assets.py
# 폴더 스캔 설정
SCAN_CONFIG = {
    'max_category_depth': 10,      # 깊은 트리 구조를 커버 (필요 시 조정)
    'sample_size': 3,             # 각 깊이에서 검사할 폴더 수
    'search_keywords': [          # 검색할 폴더 키워드
        # 문서 관련
        '설계', '보고서', '계획', '예산', '성과품', '문서', '파일',
        # 프로젝트 상태
        '준공', '완료', '진행', '착수',
        # 문서 유형별
        '계약', '과업', '협약', '실행', '도면',
        # 조직 관련
        '부서', '팀', '본부',
        # 기타
        'documents', 'files', 'reports', 'drawings'
    ],
    'skip_patterns': [           # 검색 제외할 폴더 패턴
        'backup', '백업', 'old', '이전',
        'temp', '임시', 'test', '테스트',
        'archive', '보관', 'delete', '삭제'
    ]
}

# 프로젝트 폴더 검색 설정
FORCE_SCAN_CONFIG = {
    'deep_scan_keywords': [
        # 상태 키워드
        '진행', '완료', '준공', '준공프로젝트',
        # 업무 키워드
        '조사', '해외', '환경영향',
        # 조직 키워드
        '팀', '기타', '퇴사',
        # 부서 키워드
        '01. 도로, 공항부', '03. 구조부', '04. 지반부', '05. 교통부', '06. 안전진단부',
        '07. 철도설계부', '08. 철도건설관리부', '10. 도시계획부', '11. 도시설계부',
        '12. 조경부', '13. 수자원부', '15. 상하수도부', '16. 항만부', '17. 환경사업부',
        '18. 건설사업관리부'
    ],
    'year_pattern': r'(?:199|20[0-2])\d'  # 1990~2029년 패턴
}

# 프로젝트 정보 추출 규칙
PROJECT_INFO_PATTERNS = {
    'year_pattern': r'((?:199|20[0-2])\d)'  # 1990~2029년
}

# 검색 대상 문서 유형
DOCUMENT_TYPES = {
    'contract': {'name': '계약서', 'keywords': ['계약서', '변경계약서', '계약', 'contract'], 'type': ['pdf']},
    'specification': {'name': '과업지시서', 'keywords': ['과업지시', '내용서', 'specification'], 'type': ['pdf', 'hwp']},
    'initiation': {'name': '착수계', 'keywords': ['착수', '착수계', 'initiation'], 'type': ['pdf']},
    'agreement': {'name': '공동도급협정', 'keywords': ['분담', '협정', '협약', 'agreement'], 'type': ['pdf']},
    'budget': {'name': '실행예산', 'keywords': ['실행', '실행예산', 'budget'], 'type': ['pdf', 'xls', 'xlsx']},
    'deliverable1': {'name': '성과품(보고서)', 'keywords': ['성과품', '성과', '보고서', '1장', 'deliverable1'], 'type': ['hwp', 'pdf']},
    'deliverable2': {'name': '성과품(도면)', 'keywords': ['성과품', '성과', '도면', '일반도', '평면도', 'deliverable2'], 'type': ['dwg', 'pdf']},
    'completion': {'name': '준공계', 'keywords': ['준공', '준공계', 'completion'], 'type': ['pdf']},
    'certificate': {'name': '실적증명', 'keywords': ['실적증명', '증명', 'certificate'], 'type': ['pdf']},
    'evaluation': {'name': '용역수행평가', 'keywords': ['용역수행평가', '용역수행', 'evaluation'], 'type': ['pdf', 'hwp']}
}

# 부서 매핑 (PM부서 → department_code)
DEPARTMENT_MAPPING = {
    '도로부': '01010',
    '공항및인프라사업부': '01020',
    '구조부': '01030',
    '지반부': '01040',
    '교통부': '01050',
    '안전진단부': '01060',
    '도시철도부': '02010',
    '철도설계부': '03010',
    '철도건설관리부': '03020',
    '도시계획부': '04010',
    '도시설계부': '04020',
    '조경부': '04030',
    '수자원부': '05010',
    '환경사업부': '06010',
    '상하수도부': '07010',
    '항만부': '07020',  # 항만부 코드 변경
    '건설사업관리부': '08010',
    '해외영업부': '09010',  # '해외영업' → '해외영업부'로 수정 (한글 부서명 일관성)
    '플랫폼사업실': '10010',
    '기술지원실': '11010',
    '수성엔지니어링': '99999'  # 예비 부서
}

# 감사 대상 필터링 설정
AUDIT_FILTERS = {
    'status': ['준공', '진행'],  # 진행 상태 필터 (다중 값 가능: '준공', '진행', '중지', '탈락')
                                 # - '준공': 성과품 완벽히 포함해야 함 (주관사 100%, 비주관사 최소 필요)
                                 # - '진행': 성과품 미완성 가능
                                 # - '중지': 진행보다 미흡한 상태, 성과품 누락 가능
                                 # - '탈락': 입찰 탈락, 감사 제외 가능
    'is_main_contractor': ['주관사', '비주관사'],  # 
                                                 # 주관사 여부
                                                 # - '주관사': 모든 자료 완비 (100% 문서 필요)
                                                 # - '비주관사': 최소 필요 자료만 있음
    'year': [2024],  # 준공 연도 필터 (다중 값 가능, 최근 준공 프로젝트 감사)
    'department': None  # 기본값 없음, AUDIT_FILTERS_depart 참조
}

# 부서 필터링 (한글 부서명으로 설정, 기본값으로 모든 부서 포함)
AUDIT_FILTERS_depart = [
    '도로부',
    '공항및인프라사업부',
    '구조부',
    '지반부',
    '교통부',
    '안전진단부',
    '도시철도부',
    '철도설계부',
    '철도건설관리부',
    '도시계획부',
    '도시설계부',
    '조경부',
    '수자원부',
    '환경사업부',
    '상하수도부',
    '항만부',
    # '건설사업관리부',
    '해외영업부',
    '플랫폼사업실',
]

# 부서 코드 → 부서명 한글 매핑
# 부서 코드 → 한글 부서명 매핑
DEPARTMENT_NAMES = {
    code: name for code, name in DEPARTMENT_MAPPING.items()
}
# 부서 매핑 유틸리티 함수
def get_department_code(department_name):
    """한글 부서명에서 department_code 반환"""
    return DEPARTMENT_MAPPING.get(department_name, '99999')

def get_department_name(department_code):
    """department_code에서 한글 부서명 반환"""
    return DEPARTMENT_NAMES.get(department_code, '미정의 부서')