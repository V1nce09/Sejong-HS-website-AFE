import requests
import time
import os
import json
import hashlib
from functools import wraps
from datetime import datetime

import config


class NeisRequestError(Exception):
    """NEIS 요청/응답 자체가 실패했음을 나타냅니다.

    정상적인 '데이터 없음(INFO-200)'과 네트워크/서버 오류를 구분하여,
    오류일 때는 만료된 캐시라도 재사용할 수 있게 합니다.
    """


_last_cache_cleanup = 0


def _cleanup_cache_if_needed():
    """캐시 디렉토리가 무한히 커지지 않도록 하루에 한 번 오래된 파일을 정리합니다."""
    global _last_cache_cleanup
    now = time.time()
    if now - _last_cache_cleanup < 24 * 60 * 60:
        return
    _last_cache_cleanup = now

    max_age = getattr(config, "CACHE_FILE_MAX_AGE", 45 * 24 * 60 * 60)
    try:
        for name in os.listdir(config.CACHE_DIR):
            if not name.endswith(".json"):
                continue
            path = os.path.join(config.CACHE_DIR, name)
            try:
                if now - os.path.getmtime(path) > max_age:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def _cache_path(func_name, args, kwargs):
    raw_key = json.dumps(
        {"func": func_name, "args": args, "kwargs": sorted(kwargs.items())},
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return os.path.join(config.CACHE_DIR, f"{func_name}_{digest}.json")


def file_cache(lifetime, cache_empty=True):
    """파일 기반 공유 캐시.

    - 여러 사용자가 같은 급식/시간표를 조회해도 NEIS에는 캐시 만료 전 한 번만 요청합니다.
    - []도 정상 결과로 캐시하여 주말/방학에 같은 '데이터 없음' 요청이 반복되지 않게 합니다.
    - NEIS 장애/타임아웃 시에는 일정 기간 내의 만료 캐시(stale)를 대신 반환합니다.
    - lifetime은 초(int) 또는 인자를 받아 초를 반환하는 함수일 수 있습니다.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            os.makedirs(config.CACHE_DIR, exist_ok=True)
            _cleanup_cache_if_needed()
            cache_filename = _cache_path(func.__name__, args, kwargs)
            ttl = lifetime(*args, **kwargs) if callable(lifetime) else lifetime
            cached = None
            cache_age = None

            if os.path.exists(cache_filename):
                try:
                    with open(cache_filename, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    cache_age = time.time() - float(cached.get("timestamp", 0))
                    if cache_age < ttl:
                        return cached.get("data", [])
                except (OSError, ValueError, TypeError, json.JSONDecodeError) as e:
                    print(f"캐시 파일 읽기 오류: {e}")
                    cached = None
                    cache_age = None

            try:
                result = func(*args, **kwargs)
            except NeisRequestError as e:
                print(f"NEIS 요청 실패, 캐시 대체 시도: {e}")
                max_stale = getattr(config, "CACHE_STALE_MAX_AGE", 7 * 24 * 60 * 60)
                if cached is not None and cache_age is not None and cache_age < max_stale:
                    return cached.get("data", [])
                return []

            should_cache = cache_empty or bool(result)
            if should_cache:
                temp_filename = f"{cache_filename}.tmp"
                try:
                    with open(temp_filename, "w", encoding="utf-8") as f:
                        json.dump(
                            {"timestamp": time.time(), "data": result},
                            f,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    os.replace(temp_filename, cache_filename)
                except OSError as e:
                    print(f"캐시 파일 쓰기 오류: {e}")
                    try:
                        if os.path.exists(temp_filename):
                            os.remove(temp_filename)
                    except OSError:
                        pass

            return result
        return wrapper
    return decorator


def _meal_cache_lifetime(date, **_kwargs):
    """지난 날짜 급식은 장기 캐시, 오늘/미래 급식은 비교적 짧게 캐시합니다."""
    try:
        requested = datetime.strptime(str(date), "%Y%m%d").date()
        if requested < datetime.now().date():
            return getattr(config, "MEAL_PAST_CACHE_LIFETIME", 30 * 24 * 60 * 60)
    except ValueError:
        pass
    return getattr(config, "MEAL_CACHE_LIFETIME", 12 * 60 * 60)


# --- NEIS API 연동 함수 ---

@file_cache(lifetime=_meal_cache_lifetime, cache_empty=True)
def get_meal(date):
    """지정된 날짜의 급식 정보를 NEIS API에서 가져옵니다."""
    url = (
        f"https://open.neis.go.kr/hub/mealServiceDietInfo"
        f"?KEY={config.API_KEY}&Type=json&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={config.ATPT_OFCDC_SC_CODE}"
        f"&SD_SCHUL_CODE={config.SD_SCHUL_CODE}&MLSV_YMD={date}"
    )
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        if "RESULT" in data:
            error_code = data["RESULT"]["CODE"]
            if error_code == "INFO-200":
                return []
            if error_code != "INFO-000":
                raise NeisRequestError(f"급식 API: {data['RESULT'].get('MESSAGE', error_code)}")

        meal_data = []
        rows = data.get("mealServiceDietInfo", [{}, {}])[1].get("row", [])
        for row in rows:
            meal_data.append({
                "time": row["MMEAL_SC_NM"],
                "menu": row["DDISH_NM"].replace("<br/>", "\n")
            })
        return meal_data

    except requests.exceptions.RequestException as e:
        raise NeisRequestError(f"급식 네트워크 오류: {e}") from e
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        raise NeisRequestError(f"급식 응답 처리 오류: {e}") from e


@file_cache(lifetime=lambda *_args, **_kwargs: getattr(config, "TIMETABLE_CACHE_LIFETIME", 6 * 60 * 60), cache_empty=True)
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
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        if "RESULT" in data:
            error_code = data["RESULT"]["CODE"]
            if error_code == "INFO-200":
                return []
            if error_code != "INFO-000":
                raise NeisRequestError(f"시간표 API: {data['RESULT'].get('MESSAGE', error_code)}")

        weekly_schedule = {}
        rows = data.get("hisTimetable", [{}, {}])[1].get("row", [])
        for row in rows:
            day = row["ALL_TI_YMD"]
            period = int(row["PERIO"])
            subject = row["ITRT_CNTNT"]

            if day not in weekly_schedule:
                weekly_schedule[day] = {}
            weekly_schedule[day][period] = subject

        result = []
        for day, periods in sorted(weekly_schedule.items()):
            ordered_periods = sorted(periods.keys())
            day_timetable = [periods[p] for p in ordered_periods]
            # 기존 프런트 호환용 timetable 리스트는 유지하면서, 개인 시간표 변경 감지에서는
            # 결강 등으로 교시가 비연속적이어도 정확히 비교할 수 있도록 period_map도 함께 저장합니다.
            result.append({
                "date": day,
                "timetable": day_timetable,
                "period_map": {str(p): periods[p] for p in ordered_periods},
            })

        return result

    except requests.exceptions.RequestException as e:
        raise NeisRequestError(f"시간표 네트워크 오류: {e}") from e
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        raise NeisRequestError(f"시간표 응답 처리 오류: {e}") from e


@file_cache(lifetime=lambda *_args, **_kwargs: getattr(config, "MEAL_CACHE_LIFETIME", 7 * 24 * 60 * 60), cache_empty=True)
def get_meal_range(start_date, end_date):
    """기간 급식을 한 번의 NEIS 요청으로 가져옵니다. 결과는 날짜별 dict입니다."""
    params = {
        "KEY": config.API_KEY, "Type": "json", "pIndex": 1, "pSize": 100,
        "ATPT_OFCDC_SC_CODE": config.ATPT_OFCDC_SC_CODE,
        "SD_SCHUL_CODE": config.SD_SCHUL_CODE,
        "MLSV_FROM_YMD": start_date, "MLSV_TO_YMD": end_date,
    }
    try:
        response = requests.get("https://open.neis.go.kr/hub/mealServiceDietInfo", params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if "RESULT" in data:
            code = data["RESULT"].get("CODE")
            if code == "INFO-200":
                return {}
            if code != "INFO-000":
                raise NeisRequestError(f"급식 API: {data['RESULT'].get('MESSAGE', code)}")
        result = {}
        rows = data.get("mealServiceDietInfo", [{}, {}])[1].get("row", [])
        for row in rows:
            date = row.get("MLSV_YMD", "")
            if not date:
                continue
            result.setdefault(date, []).append({
                "time": row.get("MMEAL_SC_NM", "급식"),
                "menu": row.get("DDISH_NM", "").replace("<br/>", "\n"),
            })
        return result
    except requests.exceptions.RequestException as e:
        raise NeisRequestError(f"기간 급식 네트워크 오류: {e}") from e
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        raise NeisRequestError(f"기간 급식 응답 처리 오류: {e}") from e


@file_cache(lifetime=lambda *_args, **_kwargs: getattr(config, "SCHEDULE_CACHE_LIFETIME", 7 * 24 * 60 * 60), cache_empty=True)
def get_school_schedule(start_date, end_date):
    """NEIS 학사일정을 기간 단위로 가져옵니다."""
    params = {
        "KEY": config.API_KEY, "Type": "json", "pIndex": 1, "pSize": 100,
        "ATPT_OFCDC_SC_CODE": config.ATPT_OFCDC_SC_CODE,
        "SD_SCHUL_CODE": config.SD_SCHUL_CODE,
        "AA_FROM_YMD": start_date, "AA_TO_YMD": end_date,
    }
    try:
        response = requests.get("https://open.neis.go.kr/hub/SchoolSchedule", params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if "RESULT" in data:
            code = data["RESULT"].get("CODE")
            if code == "INFO-200":
                return []
            if code != "INFO-000":
                raise NeisRequestError(f"학사일정 API: {data['RESULT'].get('MESSAGE', code)}")
        rows = data.get("SchoolSchedule", [{}, {}])[1].get("row", [])
        events = []
        for row in rows:
            events.append({
                "date": row.get("AA_YMD", ""),
                "name": row.get("EVENT_NM", ""),
                "content": row.get("EVENT_CNTNT", ""),
                "grade1": row.get("ONE_GRADE_EVENT_YN", "N") == "Y",
                "grade2": row.get("TW_GRADE_EVENT_YN", "N") == "Y",
                "grade3": row.get("THREE_GRADE_EVENT_YN", "N") == "Y",
            })
        return sorted(events, key=lambda x: x.get("date", ""))
    except requests.exceptions.RequestException as e:
        raise NeisRequestError(f"학사일정 네트워크 오류: {e}") from e
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        raise NeisRequestError(f"학사일정 응답 처리 오류: {e}") from e
