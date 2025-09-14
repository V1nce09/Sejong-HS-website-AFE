from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from datetime import datetime

app = Flask(__name__)

# API 키, 학교 코드
API_KEY = "e940bcda8d8e44d2a2d72d3b3c0a0e63"
ATPT_OFCDC_SC_CODE = "I10"
SD_SCHUL_CODE = "9300054"
SEM = "2"

# 📌 급식 API
def get_meal(date):
    url = (
        f"https://open.neis.go.kr/hub/mealServiceDietInfo"
        f"?KEY={API_KEY}&Type=xml&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={ATPT_OFCDC_SC_CODE}"
        f"&SD_SCHUL_CODE={SD_SCHUL_CODE}&MLSV_YMD={date}"
    )
    info = requests.get(url).text
    soup = BeautifulSoup(info, "xml")

    meal_data = []
    times = [t.text for t in soup.find_all("MMEAL_SC_NM")]
    menus = [m.text.replace("<br/>", "\n") for m in soup.find_all("DDISH_NM")]

    for t, m in zip(times, menus):
        meal_data.append({"time": t, "menu": m})

    return meal_data


# 📌 시간표 API
def get_timetable(date, grade, classroom):
    url = (
        f"https://open.neis.go.kr/hub/hisTimetable"
        f"?KEY={API_KEY}&Type=xml&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={ATPT_OFCDC_SC_CODE}"
        f"&SD_SCHUL_CODE={SD_SCHUL_CODE}&SEM={SEM}"
        f"&GRADE={grade}&CLASS_NM={classroom}&ALL_TI_YMD={date}"
    )
    info = requests.get(url).text
    soup = BeautifulSoup(info, "xml")

    timetable = [i.text for i in soup.find_all("ITRT_CNTNT")]
    return timetable


@app.route("/")
def index():
    return render_template("main.html")


@app.route("/api/data", methods=["GET"])
def api_data():
    date = request.args.get("date", datetime.now().strftime("%Y%m%d"))
    grade = request.args.get("grade", "1")
    classroom = request.args.get("classroom", "1")

    meal_data = get_meal(date)
    timetable = get_timetable(date, grade, classroom)

    return jsonify({
        "meal": meal_data,
        "timetable": timetable,
        "grade": grade,
        "classroom": classroom,
        "date": date
    })


if __name__ == "__main__":
    app.run(debug=True)
