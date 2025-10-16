from flask import Flask, render_template, request, redirect, url_for, jsonify, session, g
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = "secret"
DATABASE = os.path.join(os.path.dirname(__file__), "users.db")

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

# --- 새로 추가: 루트(랜딩) 페이지 ---
@app.route("/")
def index():
    # 간단한 랜딩 페이지: 로그인, 회원가입, 게스트
    return render_template("index.html")

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
                (userid, generate_password_hash(password), grade or None, classroom or None, student_no or None, datetime.now().isoformat())
            )
            db.commit()
        except sqlite3.IntegrityError:
            return render_template("register.html", error="이미 사용 중인 아이디입니다.")

        # 회원가입 완료 후 자동 로그인 대신 로그인 페이지로 이동
        return redirect(url_for("login"))

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
            # 로그인 성공시 세션에 필요한 정보 저장
            session["user"] = userid
            session["student_no"] = user["student_no"] or ""
            session["display_name"] = user["userid"]
            return redirect(url_for("main"))
        return render_template("login.html", error="아이디 또는 비밀번호가 올바르지 않습니다.")
    return render_template("login.html")

# --- main route: 로그인한 학생이면 자동으로 오늘 학급 시간표/급식 미리 로드 ---
@app.route("/main")
def main():
    # 비로그인 사용자는 guest 파라가 있어야 접근 허용
    if "user" not in session and request.args.get("guest") != "1":
        return redirect(url_for("login"))

    # 오늘 / 내일 날짜 문자열
    today = datetime.now()
    date_str = today.strftime("%Y%m%d")
    tomorrow = (today + timedelta(days=1)).strftime("%Y%m%d")

    # 우선적으로 쿼리스트링(수동 조회) -> 세션의 학번 파싱(자동) -> 기본값
    grade = request.args.get("grade")
    classroom = request.args.get("classroom")

    if session.get("student_no") and request.args.get("guest") != "1":
        sn = session.get("student_no", "")
        if sn and sn.isdigit() and len(sn) >= 5:
            grade = grade or sn[0]
            classroom = classroom or str(int(sn[1:3]))

    grade = grade or "1"
    classroom = classroom or "1"

    # 서버에서 오늘과 내일 데이터 로드 (안정성 확보)
    timetable_list = []
    for d in (date_str, tomorrow):
        try:
            tt = get_timetable(d, grade, classroom) or []
        except Exception:
            tt = []
        if tt:
            timetable_list.append({"date": d, "timetable": tt})

    try:
        meal = get_meal(date_str) or []
    except Exception:
        meal = []

    return render_template(
        "main.html",
        meal=meal,
        timetable=timetable_list,
        grade=grade,
        classroom=classroom,
        date=date_str
    )

# 로그아웃 라우트 추가 (GET으로 간단 구현)
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

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
