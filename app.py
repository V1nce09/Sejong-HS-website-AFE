from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = "secret"

# NEIS API 정보
API_KEY = "e940bcda8d8e44d2a2d72d3b3c0a0e63"
ATPT_OFCDC_SC_CODE = "I10"
SD_SCHUL_CODE = "9300054"
SEM = "2"

# 📌 급식 정보
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

# 📌 시간표 정보
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


# 📌 로그인
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        userid = request.form["userid"]
        password = request.form["password"]
        if userid == "admin" and password == "1234":
            session["user"] = userid
            return redirect(url_for("main"))
        else:
            return render_template("login.html", error="아이디 또는 비밀번호가 올바르지 않습니다.")
    return render_template("login.html")

# 📌 메인
@app.route("/main")
def main():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("main.html")

# 📌 API 데이터 요청
@app.route("/api/data", methods=["GET"])
def api_data():
    date = request.args.get("date", datetime.now().strftime("%Y%m%d"))
    grade = request.args.get("grade", "1")
    classroom = request.args.get("classroom", "1")

    # 2주(14일) 데이터 생성
    start_date = datetime.strptime(date, "%Y%m%d")
    days = [(start_date + timedelta(days=i)).strftime("%Y%m%d") for i in range(0, 14)]

    # 시간표 (요일별 리스트)
    week_data = []
    for d in days:
        timetable = get_timetable(d, grade, classroom)
        if timetable:
            week_data.append({"date": d, "timetable": timetable})

    meal_data = get_meal(date)

    return jsonify({
        "meal": meal_data,
        "timetable": week_data,
        "grade": grade,
        "classroom": classroom,
        "date": date
    })


if __name__ == "__main__":
    app.run(debug=True)
