from flask import Flask, render_template, request, jsonify, redirect, url_for
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

app = Flask(__name__)

# --- 설정 (원본값 사용) ---
API_KEY = "e940bcda8d8e44d2a2d72d3b3c0a0e63"
ATPT_OFCDC_SC_CODE = "I10"
SD_SCHUL_CODE = "9300054"
SEM = "2"

# -----------------------
# 급식 API (원본 코드 사용)
def get_meal(date):
    """
    date: 'YYYYMMDD' 문자열
    반환: [{"time": "중식", "menu": "밥\n국\n반찬"}, ...] or []
    """
    url = (
        f"https://open.neis.go.kr/hub/mealServiceDietInfo"
        f"?KEY={API_KEY}&Type=xml&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={ATPT_OFCDC_SC_CODE}"
        f"&SD_SCHUL_CODE={SD_SCHUL_CODE}&MLSV_YMD={date}"
    )
    try:
        info = requests.get(url, timeout=8).text
        soup = BeautifulSoup(info, "xml")
        times = [t.text for t in soup.find_all("MMEAL_SC_NM")]
        menus = [m.text.replace("<br/>", "\n") for m in soup.find_all("DDISH_NM")]
        meal_data = []
        for t, m in zip(times, menus):
            meal_data.append({"time": t, "menu": m})
        return meal_data
    except Exception as e:
        # 에러 발생 시 빈 리스트 리턴
        return []

# 시간표 API (원본 코드 사용)
def get_timetable_for_date(date, grade, classroom):
    """
    date: 'YYYYMMDD'
    grade, classroom: 문자열 또는 숫자
    NEIS hisTimetable API에서 ITRT_CNTNT(수업명)들을 가져옴.
    반환: list of subjects (순서대로) 또는 빈 리스트
    """
    url = (
        f"https://open.neis.go.kr/hub/hisTimetable"
        f"?KEY={API_KEY}&Type=xml&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={ATPT_OFCDC_SC_CODE}"
        f"&SD_SCHUL_CODE={SD_SCHUL_CODE}&SEM={SEM}"
        f"&GRADE={grade}&CLASS_NM={classroom}&ALL_TI_YMD={date}"
    )
    try:
        info = requests.get(url, timeout=8).text
        soup = BeautifulSoup(info, "xml")
        timetable = [i.text for i in soup.find_all("ITRT_CNTNT")]
        return timetable
    except Exception as e:
        return []

# 헬퍼: 입력 날짜(YYYYMMDD)를 기준으로 그 날짜가 포함된 주의 월요일을 찾음
def get_monday_of_week(date_obj):
    # date_obj: datetime.date
    return date_obj - timedelta(days=date_obj.weekday())  # Monday = weekday 0

@app.route("/")
def index():
    return render_template("login.html")

@app.route("/main")
def main_page():
    return render_template("main.html")

@app.route("/api/data", methods=["GET"])
def api_data():
    """
    요청쿼리:
        date=YYYYMMDD (선택된 날짜 — 우측 급식용, 기준이 될 날짜)
        grade, classroom
    반환:
        {
          "grade": "1",
          "classroom": "1",
          "base_date": "YYYYMMDD",
          "timetable": {
              "YYYYMMDD": ["과목1","과목2",...],  # 날짜별로 과목 리스트 (교시 순)
              ...
          },
          "meal": [ {"time":"중식","menu":"..."}, ... ]
        }
    ※ timetable은 10일치(해당 주 월~금 + 다음 주 월~금) 포함
    """
    date_str = request.args.get("date")
    if not date_str:
        date_obj = datetime.now().date()
        date_str = date_obj.strftime("%Y%m%d")
    else:
        try:
            date_obj = datetime.strptime(date_str, "%Y%m%d").date()
        except Exception:
            date_obj = datetime.now().date()
            date_str = date_obj.strftime("%Y%m%d")

    grade = request.args.get("grade", "1")
    classroom = request.args.get("classroom", "1")

    # 주의 월요일을 기준으로 첫째주 월요일
    monday = get_monday_of_week(date_obj)
    # 첫 주 월~금 (5일), 다음주 월~금 (5일) => 총 10일
    dates = []
    for week_offset in (0, 7):  # 0일, +7일
        base = monday + timedelta(days=week_offset)
        for d in range(5):  # Mon-Fri
            day = base + timedelta(days=d)
            dates.append(day.strftime("%Y%m%d"))

    # 각 날짜별 시간표 수집
    timetable_data = {}
    for d in dates:
        t = get_timetable_for_date(d, grade, classroom)
        # t가 비어있을 경우 빈 리스트로 표기
        timetable_data[d] = t

    # 선택된 날짜의 급식 (조식/중식/석식 포함)
    meal_data = get_meal(date_str)

    return jsonify({
        "grade": grade,
        "classroom": classroom,
        "base_date": date_str,
        "timetable": timetable_data,
        "meal": meal_data,
        "dates": dates
    })

if __name__ == "__main__":
    app.run(debug=True)