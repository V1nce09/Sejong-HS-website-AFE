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
# 무료 서버의 외부 API 호출을 줄이기 위해 급식·학사일정은 7일간 공유 캐시합니다.
MEAL_CACHE_LIFETIME = int(os.getenv("MEAL_CACHE_LIFETIME", str(7 * 24 * 60 * 60)))
MEAL_PAST_CACHE_LIFETIME = int(os.getenv("MEAL_PAST_CACHE_LIFETIME", str(7 * 24 * 60 * 60)))
SCHEDULE_CACHE_LIFETIME = int(os.getenv("SCHEDULE_CACHE_LIFETIME", str(7 * 24 * 60 * 60)))
TIMETABLE_CACHE_LIFETIME = int(os.getenv("TIMETABLE_CACHE_LIFETIME", str(6 * 60 * 60)))
WEATHER_CACHE_LIFETIME = int(os.getenv("WEATHER_CACHE_LIFETIME", str(30 * 60)))
CACHE_STALE_MAX_AGE = int(os.getenv("CACHE_STALE_MAX_AGE", str(14 * 24 * 60 * 60)))
CACHE_FILE_MAX_AGE = int(os.getenv("CACHE_FILE_MAX_AGE", str(45 * 24 * 60 * 60)))
CACHE_DIR = os.path.join(BASE_DIR, "cache")

# 세종고등학교(세종특별자치시 조치원읍) 기본 위치. 배포 환경변수로 교체할 수 있습니다.
WEATHER_LATITUDE = float(os.getenv("WEATHER_LATITUDE", "36.61065"))
WEATHER_LONGITUDE = float(os.getenv("WEATHER_LONGITUDE", "127.29946"))
WEATHER_LOCATION_NAME = os.getenv("WEATHER_LOCATION_NAME", "세종고등학교")
