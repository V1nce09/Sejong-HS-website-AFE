import os
from datetime import timedelta

# AES 암호화 키는 배포 환경변수에서만 읽습니다.
APP_AES_KEY = os.getenv('APP_AES_KEY')
if not APP_AES_KEY:
    raise RuntimeError('APP_AES_KEY environment variable is required')

# 기본 디렉토리
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Flask 설정
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY environment variable is required')

# 관리자 계정도 소스에 하드코딩하지 않고 배포 환경변수에서만 읽습니다.
ADMIN_ID = os.getenv('ADMIN_ID')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
if not ADMIN_ID:
    raise RuntimeError('ADMIN_ID environment variable is required')
if not ADMIN_PASSWORD:
    raise RuntimeError('ADMIN_PASSWORD environment variable is required')

DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')

# 로그인 세션: 마지막 활동 기준 30일 유지.
# PythonAnywhere는 HTTPS이므로 Secure 쿠키를 기본으로 사용합니다.
PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.getenv("SESSION_LIFETIME_DAYS", "30")))
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "True").lower() in ("true", "1", "t")
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_REFRESH_EACH_REQUEST = True

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

# Supabase Storage (게시글 사진 첨부)
# 새 Secret key(sb_secret_*) 또는 legacy service_role 키 중 하나를 서버 환경변수에 넣습니다.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_STORAGE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "school-post-images")
SUPABASE_STORAGE_TIMEOUT = int(os.getenv("SUPABASE_STORAGE_TIMEOUT", "20"))
POST_IMAGE_MAX_COUNT = 3
POST_IMAGE_SOURCE_MAX_BYTES = 8 * 1024 * 1024
POST_IMAGE_MAX_BYTES = 1024 * 1024
POST_IMAGE_MAX_EDGE = 1600

# 게시글 3장(각 원본 최대 8MB) 업로드를 허용하되 그 이상 요청은 Flask 단계에서 차단합니다.
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(26 * 1024 * 1024)))
