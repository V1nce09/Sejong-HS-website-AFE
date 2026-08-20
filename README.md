# 세종고 통합 포털

## 메인 정보 구조
- 메인 화면: 오늘의 급식 / 오늘의 시간표 / 오늘 날씨
- 내 정보 보기: 이름·학번 확인 및 변경
- 시간표: 이번주 개인 시간표, 2학년 선택과목 설정, 관리자 반별 기준 시간표
- 게시판: 가입된 게시판 모음
- 급식: 이번주 식단
- 학교 소식: NEIS 학사일정 / 관리자 공지
- 사이트 정보: 만든 취지 / 제작팀 (관리자 편집)

## 외부 데이터와 캐시
- 급식: NEIS `mealServiceDietInfo`, 주간 범위 1회 조회, 7일 파일 캐시
- 학사일정: NEIS `SchoolSchedule`, 주 시작일 기준 범위 조회, 7일 파일 캐시
- 시간표: NEIS `hisTimetable`, 월~금 범위 캐시
- 날씨: Open-Meteo Forecast API, 기본 30분 파일 캐시

## 주요 환경변수
- `SECRET_KEY`
- `API_KEY` (NEIS)
- `ATPT_OFCDC_SC_CODE`
- `SD_SCHUL_CODE`
- `SEM`
- `WEATHER_LATITUDE` (기본 36.61065)
- `WEATHER_LONGITUDE` (기본 127.29946)
- `WEATHER_LOCATION_NAME` (기본 세종고등학교)
