from flask import Flask, render_template, request, redirect, url_for, jsonify, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os

import config
import database
import neis
import crypto_utils

app = Flask(__name__)
app.config.from_object(config) # config.py에서 설정 로드

# 데이터베이스 초기화 및 teardown 등록
database.init_app(app)

# --- 헬퍼 함수 ---
def pw_class_count(password):
    """비밀번호 복잡도 검사: 소문자, 대문자, 숫자, 특수문자 중 몇 가지를 포함하는지 반환"""
    count = 0
    if any(c.islower() for c in password): count += 1
    if any(c.isupper() for c in password): count += 1
    if any(c.isdigit() for c in password): count += 1
    if any(not c.isalnum() for c in password): count += 1 # 특수문자
    return count

# --- 라우트 정의 ---

# 루트 경로: 이제 바로 main 페이지로 리다이렉트
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
        student_no = request.form.get("student_no", "").strip()

        if not userid or not password:
            return render_template("register.html", error="아이디와 비밀번호를 입력하세요.")
        if password != password2:
            return render_template("register.html", error="비밀번호가 일치하지 않습니다.")
        
        # 서버 측 비밀번호 복잡도 검사 (클라이언트 측과 동일하게)
        if len(password) < 8:
            return render_template("register.html", error="비밀번호는 8자 이상이어야 합니다.")
        if pw_class_count(password) < 3:
            return render_template("register.html", error="비밀번호는 소문자·대문자·숫자·특수문자 중 3가지 이상을 포함해야 합니다.")

        # 학번 유효성 검사: 반드시 5자리 숫자
        if student_no:
            if not (student_no.isdigit() and len(student_no) == 5):
                return render_template("register.html", error="학번은 정확히 5자리 숫자여야 합니다.")
            # 파싱: 첫자리=학년, 2-3자리=반, 4-5자리=번호
            grade = student_no[0]
            classroom = str(int(student_no[1:3]))  # "01" -> "1"
            # short_no = student_no[3:] # 현재 사용되지 않으므로 제거
        else:
            grade = None
            classroom = None

        # 학생번호 암호화 (있을 경우) 
        if student_no:
            enc_sn = crypto_utils.aesgcm_encrypt(student_no.encode())
        else:
            enc_sn = None

        db = database.get_db()
        try:
            db.execute(
                "INSERT INTO users (userid, password, grade, classroom, student_no, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (userid, generate_password_hash(password), grade, classroom, enc_sn, datetime.now().isoformat())
            )
            db.commit()
        except database.sqlite3.IntegrityError:
            return render_template("register.html", error="이미 사용 중인 아이디입니다.")

        return redirect(url_for("login"))

    return render_template("register.html")

# 로그인 (DB 연동)
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        userid = request.form["userid"]
        password = request.form["password"]

        db = database.get_db()
        user = db.execute("SELECT * FROM users WHERE userid = ?", (userid,)).fetchone()
        if user and check_password_hash(user["password"], password):
            # 로그인 성공시 세션에 필요한 정보 저장
            session["user"] = userid
            # 학생번호 복호화
            plain_sn = ""
            enc_sn = user["student_no"] if user["student_no"] is not None else ""
            if enc_sn:
                try:
                    plain_sn = crypto_utils.aesgcm_decrypt(enc_sn).decode()
                except Exception:
                    plain_sn = ""
            session["student_no"] = plain_sn
            session["display_name"] = user["userid"]
            return redirect(url_for("main"))
        return render_template("login.html", error="아이디 또는 비밀번호가 올바르지 않습니다.")
    return render_template("login.html")

# --- main route: 로그인한 학생이면 자동으로 오늘 학급 시간표/급식 미리 로드 ---
@app.route("/main")
def main():
    # 오늘 날짜 문자열
    today = datetime.now()
    date_str = today.strftime("%Y%m%d")

    # 우선적으로 쿼리스트링(수동 조회) -> 세션의 학번 파싱(자동) -> 기본값
    grade = request.args.get("grade")
    classroom = request.args.get("classroom")

    # 로그인한 사용자이고, 게스트 모드가 아니라면 세션의 학번 정보 사용
    if session.get("student_no") and request.args.get("guest") != "1":
        sn = session.get("student_no", "")
        if sn and sn.isdigit() and len(sn) >= 5:
            grade = grade or sn[0]
            classroom = classroom or str(int(sn[1:3]))

    # 기본값 설정
    grade = grade or "1"
    classroom = classroom or "1"

    return render_template(
        "main.html",
        grade=grade,
        classroom=classroom,
        date=date_str
    )

# 로그아웃 라우트
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login")) # 로그아웃 후 로그인 페이지로 이동

# 📌 API 데이터 요청
@app.route("/api/data", methods=["GET"])
def api_data():
    date_str = request.args.get("date", datetime.now().strftime("%Y%m%d"))
    grade = request.args.get("grade", "1")
    classroom = request.args.get("classroom", "1")
    
    response_data = {}

    # 급식 데이터
    meal_data = neis.get_meal(date_str)
    response_data["meal"] = meal_data

    # 시간표 데이터
    try:
        base_date = datetime.strptime(date_str, "%Y%m%d")
        # 현재 날짜부터 10일치 (주말 제외) 시간표를 가져오기 위해 충분한 기간 설정
        # 예를 들어, 14일 정도면 10일치 주중 데이터를 얻기에 충분
        end_date = (base_date + timedelta(days=13)).strftime("%Y%m%d") 

        all_timetable_data = neis.get_timetable_range(grade, classroom, date_str, end_date)
        
        # 주말 제외 및 요청된 날짜부터 10일치만 필터링
        filtered_timetable = []
        fetched_count = 0
        for item in all_timetable_data:
            current_item_date = datetime.strptime(item['date'], "%Y%m%d")
            if current_item_date.weekday() < 5: # 주중만 포함 (월=0, 일=6)
                filtered_timetable.append(item)
                fetched_count += 1
            if fetched_count >= 10: # 최대 10일치만 가져옴
                break

        response_data["timetable"] = filtered_timetable

    except Exception as e:
        print(f"시간표 데이터 처리 중 오류 발생 ({date_str}): {e}")
        response_data["timetable"] = []

    response_data["grade"] = grade
    response_data["classroom"] = classroom
    response_data["date"] = date_str

    return jsonify(response_data)


if __name__ == "__main__":
    # 캐시 디렉토리가 없으면 생성
    if not os.path.exists(config.CACHE_DIR):
        os.makedirs(config.CACHE_DIR)
    app.run(debug=config.DEBUG)