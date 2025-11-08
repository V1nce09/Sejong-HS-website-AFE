import requests
from bs4 import BeautifulSoup
import time
import os
import json
from functools import wraps
from datetime import datetime, timedelta

import config

# --- 파일 기반 캐시 데코레이터 ---
def file_cache(lifetime):
    """지정된 시간(초) 동안 결과를 파일에 캐시하는 데코레이터입니다."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 캐시 키 생성 (함수명 + 인자)
            # args와 kwargs를 정렬하여 순서에 상관없이 동일한 키를 갖도록 함
            sorted_kwargs = sorted(kwargs.items())
            key_parts = [func.__name__] + list(map(str, args)) + [f"{k}={v}" for k, v in sorted_kwargs]
            cache_key = "_".join(key_parts)
            cache_filename = os.path.join(config.CACHE_DIR, f"{cache_key}.json")

            # 캐시 파일 확인
            if os.path.exists(cache_filename):
                try:
                    with open(cache_filename, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                        # 캐시 유효 시간 확인
                        if time.time() - cache_data['timestamp'] < lifetime:
                            print(f"캐시 히트: {cache_key}")
                            return cache_data['data']
                        else:
                            print(f"캐시 만료: {cache_key}")
                except (IOError, json.JSONDecodeError) as e:
                    print(f"캐시 파일 읽기 오류: {e}")

            # 캐시가 없거나 만료된 경우, 실제 함수 호출
            print(f"API 호출 또는 데이터 생성: {cache_key}")
            result = func(*args, **kwargs)

            # 성공적인 결과만 파일에 저장 (빈 리스트는 실패로 간주하고 캐시하지 않음)
            if result:
                try:
                    with open(cache_filename, 'w', encoding='utf-8') as f:
                        cache_content = {'timestamp': time.time(), 'data': result}
                        json.dump(cache_content, f, ensure_ascii=False, indent=2)
                except IOError as e:
                    print(f"캐시 파일 쓰기 오류: {e}")

            return result
        return wrapper
    return decorator


# --- NEIS API 연동 함수 ---

@file_cache(lifetime=config.CACHE_LIFETIME)
def get_meal(date):
    """지정된 날짜의 급식 정보를 NEIS API에서 가져옵니다."""
    url = (
        f"https://open.neis.go.kr/hub/mealServiceDietInfo"
        f"?KEY={config.API_KEY}&Type=json&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={config.ATPT_OFCDC_SC_CODE}"
        f"&SD_SCHUL_CODE={config.SD_SCHUL_CODE}&MLSV_YMD={date}"
    )
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # 200 OK가 아니면 예외 발생
        data = response.json()

        # API 에러 처리
        if 'RESULT' in data:
            error_code = data['RESULT']['CODE']
            if error_code != 'INFO-000':
                print(f"NEIS API 오류 (급식): {data['RESULT']['MESSAGE']}")
                return []

        meal_data = []
        rows = data.get('mealServiceDietInfo', [{}])[1].get('row', [])
        for row in rows:
            meal_data.append({
                "time": row['MMEAL_SC_NM'],
                "menu": row['DDISH_NM'].replace('<br/>', '\n')
            })
        return meal_data

    except requests.exceptions.RequestException as e:
        print(f"API 요청 오류 (급식): {e}")
        return []
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"API 응답 처리 오류 (급식): {e}")
        return []


@file_cache(lifetime=config.CACHE_LIFETIME)
def get_timetable_range(grade, classroom, start_date, end_date):
    """지정된 기간의 시간표 정보를 NEIS API에서 한 번에 가져옵니다."""
    url = (
        f"https://open.neis.go.kr/hub/hisTimetable"
        f"?KEY={config.API_KEY}&Type=json&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={config.ATPT_OFCDC_SC_CODE}"
        f"&SD_SCHUL_CODE={config.SD_SCHUL_CODE}&SEM={config.SEM}"
        f"&GRADE={grade}&CLASS_NM={classroom}"
        f"&TI_FROM_YMD={start_date}&TI_TO_YMD={end_date}"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if 'RESULT' in data:
            error_code = data['RESULT']['CODE']
            if error_code != 'INFO-000':
                # 데이터가 없는 경우(INFO-200)는 정상 처리
                if error_code == 'INFO-200':
                    return []
                print(f"NEIS API 오류 (시간표): {data['RESULT']['MESSAGE']}")
                return []

        weekly_schedule = {}
        rows = data.get('hisTimetable', [{}])[1].get('row', [])
        for row in rows:
            day = row["ALL_TI_YMD"]
            period = int(row["PERIO"])
            subject = row["ITRT_CNTNT"]
            
            if day not in weekly_schedule:
                weekly_schedule[day] = {}
            weekly_schedule[day][period] = subject

        result = []
        for day, periods in sorted(weekly_schedule.items()):
            day_timetable = [periods[p] for p in sorted(periods.keys())]
            result.append({"date": day, "timetable": day_timetable})

        return result

    except requests.exceptions.RequestException as e:
        print(f"API 요청 오류 (시간표): {e}")
        return []
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"API 응답 처리 오류 (시간표): {e}")
        return []
