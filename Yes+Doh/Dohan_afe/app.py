from flask import Flask, render_template, request, redirect, url_for, jsonify, session, g
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
import time

app = Flask(__name__)
app.secret_key = "secret"
DATABASE = os.path.join(os.path.dirname(__file__), "users.db")

# NEIS API 정보
API_KEY = "e940bcda8d8e44d2a2d72d3b3c0a0e63"
ATPT_OFCDC_SC_CODE = "I10"
SD_SCHUL_CODE = "9300054"
SEM = "2"

#캐싱 설정 및 저장소
CACHE_LIFETIME = 3600
meal_cache = {}
timetable_cache = {}

# 📌 급식 정보
def get_meal(date):
    cache_key = date
    
    if cache_key in meal_cache:
        cached_data, timestamp = meal_cache[cache_key]
        if time.time() - timestamp < CACHE_LIFETIME:
            print(f"급식 정보 캐시 히트: {date}")
            return cached_data
        else:
            print(f"급식 정보 캐시 만료: {date}")

    print(f"급식 정보 API 호출: {date}")
    url = (
        f"https://open.neis.go.kr/hub/mealServiceDietInfo"
        f"?KEY={API_KEY}&Type=xml&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={ATPT_OFCDC_SC_CODE}"
        f"&SD_SCHUL_CODE={SD_SCHUL_CODE}&MLSV_YMD={date}"
    )
    
    try:
        info = requests.get(url, timeout=5).text
        soup = BeautifulSoup(info, "xml")
        
        if soup.find("RESULT") and soup.find("CODE").text != "INFO-000":

            meal_data = [] 
        else:
            meal_data = []
            times = [t.text for t in soup.find_all("MMEAL_SC_NM")]
            menus = [m.text.replace("<br/>", "\n") for m in soup.find_all("DDISH_NM")]
            for t, m in zip(times, menus):
                meal_data.append({"time": t, "menu": m})

        meal_cache[cache_key] = (meal_data, time.time())
        return meal_data

    except requests.exceptions.RequestException as e:
        print(f"API 요청 오류: {e}")
        return []

#시간표
def get_timetable(date, grade, classroom):

    cache_key = f"{date}_{grade}_{classroom}"

    if cache_key in timetable_cache:
        cached_data, timestamp = timetable_cache[cache_key]
        if time.time() - timestamp < CACHE_LIFETIME:
            print(f"시간표 캐시 히트: {cache_key}")
            return cached_data
        else:
            print(f"시간표 캐시 만료: {cache_key}")

    print(f"시간표 API 호출: {cache_key}")
    url = (
        f"https://open.neis.go.kr/hub/hisTimetable"
        f"?KEY={API_KEY}&Type=xml&pIndex=1&pSize=100"
        f"&ATPT_OFCDC_SC_CODE={ATPT_OFCDC_SC_CODE}"
        f"&SD_SCHUL_CODE={SD_SCHUL_CODE}&SEM={SEM}"
        f"&GRADE={grade}&CLASS_NM={classroom}&ALL_TI_YMD={date}"
    )

    try:
        info = requests.get(url, timeout=5).text
        soup = BeautifulSoup(info, "xml")

        if soup.find("RESULT") and soup.find("CODE").text != "INFO-000":
            timetable = []
        else:
            timetable = [i.text for i in soup.find_all("ITRT_CNTNT")]

        timetable_cache[cache_key] = (timetable, time.time())
        return timetable

    except requests.exceptions.RequestException as e:
        print(f"API 요청 오류: {e}")
        return []

# ---------- DB helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        userid TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        grade TEXT,
        classroom TEXT,
        student_no TEXT,
        created_at TEXT NOT NULL
    )
    """)
    # ensure default admin (password 1234) exists
    cur.execute("SELECT id FROM users WHERE userid = ?", ("admin",))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (userid, password, created_at) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("1234"), datetime.now().isoformat())
        )
    db.commit()
    db.close()

# initialize DB on startup
init_db()

# 📌 회원가입
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        userid = request.form.get("userid", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        student_no = request.form.get("student_no", "").strip()  # 5자리 학번

        if not userid or not password:
            return render_template("register.html", error="아이디와 비밀번호를 입력하세요.")
        if password != password2:
            return render_template("register.html", error="비밀번호가 일치하지 않습니다.")
        if len(password) < 4:
            return render_template("register.html", error="비밀번호는 4자 이상이어야 합니다.")

        # 학번 유효성 검사: 반드시 5자리 숫자
        if student_no:
            if not (student_no.isdigit() and len(student_no) == 5):
                return render_template("register.html", error="학번은 정확히 5자리 숫자여야 합니다.")
            # 파싱: 첫자리=학년, 2-3자리=반, 4-5자리=번호
            grade = student_no[0]
            classroom = str(int(student_no[1:3]))  # "01" -> "1"
            short_no = student_no[3:]
        else:
            grade = None
            classroom = None
            short_no = None

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (userid, password, grade, classroom, student_no, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (userid, generate_password_hash(password), grade, classroom, student_no or None, datetime.now().isoformat())
            )
            db.commit()
        except sqlite3.IntegrityError:
            return render_template("register.html", error="이미 사용 중인 아이디입니다.")

        # 자동 로그인 후 메인으로 이동
        session["user"] = userid
        return redirect(url_for("main"))

    return render_template("register.html")

# 📌 로그인 (DB 연동)
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        userid = request.form["userid"]
        password = request.form["password"]

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE userid = ?", (userid,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session["user"] = userid
            return redirect(url_for("main"))

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

    start_date = datetime.strptime(date, "%Y%m%d")
    days = [(start_date + timedelta(days=i)).strftime("%Y%m%d") for i in range(0, 14)]

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
