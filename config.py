import os

# 기본 디렉토리
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Flask 설정
SECRET_KEY = "secret"  # 실제 운영 환경에서는 더 복잡하고 안전한 키를 사용해야 합니다.
DEBUG = True

# 데이터베이스 설정
DATABASE_PATH = os.path.join(BASE_DIR, "users.db")

# NEIS API 정보
# 참고: API 키는 보안을 위해 환경 변수나 별도의 시크릿 관리 도구를 사용하는 것이 가장 좋습니다.
API_KEY = "e940bcda8d8e44d2a2d72d3b3c0a0e63"
ATPT_OFCDC_SC_CODE = "I10"
SD_SCHUL_CODE = "9300054"
SEM = "2"

# 캐시 설정
CACHE_LIFETIME = 3600  # 캐시 유효 시간 (초), 1시간
CACHE_DIR = os.path.join(BASE_DIR, "cache")
