import os

# AES 암호화 키 설정 (환경 변수)
os.environ['APP_AES_KEY'] = 'dI0rRkx6mTZi--S97R50jDVkLcQgqB5A2dYFGVjMgCY='

# 기본 디렉토리
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Flask 설정
SECRET_KEY = os.getenv('SECRET_KEY')  # 실제 운영 환경에서는 더 복잡하고 안전한 키를 사용해야 합니다.
DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')

# 데이터베이스 설정
DATABASE_PATH = os.path.join(BASE_DIR, "users.db")

# NEIS API 정보
# 참고: API 키는 보안을 위해 환경 변수나 별도의 시크릿 관리 도구를 사용하는 것이 가장 좋습니다.
API_KEY = os.getenv("API_KEY")
ATPT_OFCDC_SC_CODE = os.getenv('ATPT_OFCDC_SC_CODE')
SD_SCHUL_CODE = os.getenv('SD_SCHUL_CODE')
SEM = os.getenv("SEM","1")

# 캐시 설정
# NEIS 공유 캐시 설정
# 지난 급식은 사실상 바뀌지 않으므로 길게, 오늘/미래 급식과 시간표는 비교적 짧게 유지합니다.
MEAL_CACHE_LIFETIME = int(os.getenv("MEAL_CACHE_LIFETIME", str(12 * 60 * 60)))       # 12시간
MEAL_PAST_CACHE_LIFETIME = int(os.getenv("MEAL_PAST_CACHE_LIFETIME", str(30 * 24 * 60 * 60)))  # 30일
TIMETABLE_CACHE_LIFETIME = int(os.getenv("TIMETABLE_CACHE_LIFETIME", str(6 * 60 * 60)))  # 6시간
CACHE_STALE_MAX_AGE = int(os.getenv("CACHE_STALE_MAX_AGE", str(7 * 24 * 60 * 60)))  # 장애 시 최대 7일 stale 사용
CACHE_FILE_MAX_AGE = int(os.getenv("CACHE_FILE_MAX_AGE", str(45 * 24 * 60 * 60)))  # 오래된 캐시 파일 정리 기준
CACHE_DIR = os.path.join(BASE_DIR, "cache")
