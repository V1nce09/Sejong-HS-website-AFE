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

## 게시글 사진 첨부 (Supabase Storage)

사진은 PythonAnywhere 로컬 디스크가 아니라 Supabase Storage에 저장하고, SQLite에는 Storage 경로와 공개 URL만 저장합니다.

Supabase Dashboard에서 다음처럼 설정합니다.

1. Storage에 `school-post-images` 버킷을 생성하고 **Public bucket**으로 설정합니다.
2. 버킷 제한은 가능하면 `image/webp`, 최대 파일 크기 `1 MB`로 설정합니다. 서버가 JPG/PNG/WebP 원본을 받아 긴 변 1600px 이하의 WebP로 변환한 뒤 업로드합니다.
3. 서버 환경변수에 아래 값을 추가합니다. 새 Supabase 프로젝트라면 `SUPABASE_SECRET_KEY` 사용을 권장하고, 기존 legacy 키를 쓰는 경우 `SUPABASE_SERVICE_ROLE_KEY`도 지원합니다.

```text
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
SUPABASE_STORAGE_BUCKET=school-post-images
```

`SUPABASE_SECRET_KEY`/`SUPABASE_SERVICE_ROLE_KEY`는 절대 브라우저 코드나 GitHub에 넣지 마세요.

게시글당 최대 3장, 원본 한 장당 최대 8MB를 받고, 저장 전 EXIF를 제거하고 긴 변 1600px 이하/최종 1MB 이하 WebP로 압축합니다. 게시글 수정에서 사진을 제거하거나 게시글을 삭제하면 연결된 Storage 객체도 정리합니다.
