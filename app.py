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
        info = requests.get(url).text
        soup = BeautifulSoup(info, "xml")
        meal_data = []
        # Check for API error response from NEIS
        if soup.find("RESULT") and soup.find("CODE").text != "INFO-000":
            print(f"NEIS API 오류 응답 (급식): {soup.find('MESSAGE').text}")
            meal_data = []
        else:
            times = [t.text for t in soup.find_all("MMEAL_SC_NM")]
            menus = [m.text.replace("<br/>", "\n") for m in soup.find_all("DDISH_NM")]
            for t, m in zip(times, menus):
                meal_data.append({"time": t, "menu": m})

        meal_cache[cache_key] = (meal_data, time.time())
        return meal_data

    except requests.exceptions.RequestException as e:
        print(f"API 요청 오류 (급식): {e}")
        return []

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
        info = requests.get(url).text
        soup = BeautifulSoup(info, "xml")
        
        if soup.find("RESULT") and soup.find("CODE").text != "INFO-000":
            print(f"NEIS API 오류 응답 (시간표): {soup.find('MESSAGE').text}")
            timetable_cache[cache_key] = ([], time.time())
            return []

        # 날짜별로 시간표를 그룹화할 딕셔너리
        weekly_schedule = {}
        for row in soup.find_all("row"):
            day = row.find("ALL_TI_YMD").text
            period = int(row.find("PERIO").text)
            subject = row.find("ITRT_CNTNT").text
            
            if day not in weekly_schedule:
                weekly_schedule[day] = {}
            weekly_schedule[day][period] = subject

        # 프론트엔드가 원하는 형태로 데이터 재구성
        # [{'date': '20231023', 'timetable': ['국어', '수학', ...]}, ...]
        result = []
        for day, periods in sorted(weekly_schedule.items()):
            # 교시(period) 순서대로 과목 정렬
            day_timetable = [periods[p] for p in sorted(periods.keys())]
            result.append({"date": day, "timetable": day_timetable})

        timetable_cache[cache_key] = (result, time.time())
        return result

    except requests.exceptions.RequestException as e:
        print(f"API 요청 오류 (시간표): {e}")
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
    """
    )
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
    return redirect(url_for("main"))

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
    return render_template(
        "main.html",
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
    data_type = request.args.get("data_type", "all") # 'meal', 'timetable', 'all'
    start_offset = int(request.args.get("start_offset", "0")) # 몇 일 뒤부터 시작할지
    num_days_to_fetch = int(request.args.get("num_days", "10")) # 몇 일치를 가져올지 (기본 10일)

    response_data = {}

    if data_type in ["meal", "all"]:
        try:
            meal_data = get_meal(date)
        except Exception:
            meal_data = []
        response_data["meal"] = meal_data

    if data_type in ["timetable", "all"]:
        week_data = []
        try:
            all_timetable_data = []
            base_date = datetime.strptime(date, "%Y%m%d")
            
            fetched_count = 0
            # start_offset부터 시작하여 최대 14일 범위 내에서 num_days_to_fetch 만큼의 주중 데이터를 가져옴
            for i in range(start_offset, start_offset + 14): 
                if fetched_count >= num_days_to_fetch:
                    break

                current_date = base_date + timedelta(days=i)
                # 주말(토, 일)은 건너뛰기
                if current_date.weekday() >= 5: # 0=월, 1=화, ..., 4=금, 5=토, 6=일
                    continue
                
                current_date_str = current_date.strftime("%Y%m%d")
                daily_timetable = get_timetable(current_date_str, grade, classroom)
                if daily_timetable:
                    all_timetable_data.extend(daily_timetable)
                    fetched_count += 1 # 유효한 주중 날짜만 카운트
            
            # 중복 제거 및 날짜순 정렬
            unique_dates = {}
            for item in all_timetable_data:
                unique_dates[item['date']] = item
            
            week_data = sorted(list(unique_dates.values()), key=lambda x: x['date'])

        except Exception as e:
            print(f"시간표 데이터 처리 중 오류 발생 ({date}): {e}")
        
        response_data["timetable"] = week_data

    response_data["grade"] = grade
    response_data["classroom"] = classroom
    response_data["date"] = date

    return jsonify(response_data)


if __name__ == "__main__":
    app.run(debug=True)