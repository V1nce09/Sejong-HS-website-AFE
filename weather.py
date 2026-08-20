import hashlib
import json
import os
import time

import requests

import config


WEATHER_CODES = {
    0: "맑음", 1: "대체로 맑음", 2: "부분적으로 흐림", 3: "흐림",
    45: "안개", 48: "서리 안개", 51: "약한 이슬비", 53: "이슬비", 55: "강한 이슬비",
    56: "약한 어는 이슬비", 57: "강한 어는 이슬비", 61: "약한 비", 63: "비", 65: "강한 비",
    66: "약한 어는 비", 67: "강한 어는 비", 71: "약한 눈", 73: "눈", 75: "강한 눈",
    77: "싸락눈", 80: "약한 소나기", 81: "소나기", 82: "강한 소나기",
    85: "약한 눈 소나기", 86: "강한 눈 소나기", 95: "뇌우", 96: "우박 동반 뇌우", 99: "강한 우박 동반 뇌우",
}


def _cache_path():
    raw = f"weather:{config.WEATHER_LATITUDE}:{config.WEATHER_LONGITUDE}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, f"weather_{digest}.json")


def _read_cache(max_age):
    path = _cache_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if time.time() - float(cached.get("timestamp", 0)) <= max_age:
            return cached.get("data")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return None


def _write_cache(data):
    path = _cache_path()
    temp = path + ".tmp"
    try:
        with open(temp, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "data": data}, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp, path)
    except OSError:
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except OSError:
            pass


def get_current_weather():
    cached = _read_cache(config.WEATHER_CACHE_LIFETIME)
    if cached is not None:
        return cached

    params = {
        "latitude": config.WEATHER_LATITUDE,
        "longitude": config.WEATHER_LONGITUDE,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "timezone": "Asia/Seoul",
        "forecast_days": 1,
    }
    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=5)
        response.raise_for_status()
        payload = response.json()
        current = payload.get("current") or {}
        daily = payload.get("daily") or {}
        code = int(current.get("weather_code", 0))
        data = {
            "location": config.WEATHER_LOCATION_NAME,
            "temperature": current.get("temperature_2m"),
            "apparent_temperature": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "precipitation": current.get("precipitation"),
            "wind_speed": current.get("wind_speed_10m"),
            "weather_code": code,
            "condition": WEATHER_CODES.get(code, "날씨 정보"),
            "max_temperature": (daily.get("temperature_2m_max") or [None])[0],
            "min_temperature": (daily.get("temperature_2m_min") or [None])[0],
            "precipitation_probability": (daily.get("precipitation_probability_max") or [None])[0],
            "observed_at": current.get("time"),
        }
        _write_cache(data)
        return data
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError):
        stale = _read_cache(config.CACHE_STALE_MAX_AGE)
        return stale or {}
