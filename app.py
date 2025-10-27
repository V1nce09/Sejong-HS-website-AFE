from flask import Flask, render_template, request, redirect, url_for, jsonify, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import time # time 모듈 추가

import config
import database
import neis
import crypto_utils

app = Flask(__name__)
app.config.from_object(config) # config.py에서 설정 로드

# 캐시 디렉토리가 없으면 생성 (PythonAnywhere 같은 WSGI 서버 환경을 위함)
if not os.path.exists(config.CACHE_DIR):
    os.makedirs(config.CACHE_DIR)

# 데이터베이스 초기화 및 teardown 등록
database.init_app(app)

@app.before_request
def load_logged_in_user_and_session():
    # 세션 ID 관리 (로그인 여부와 관계없이)
    if 'session_id' not in session:
        session['session_id'] = os.urandom(24).hex() # 고유한 세션 ID 생성
    g.session_id = session['session_id']

    # 로그인된 사용자 정보 로드
    user_id = session.get("user")
    if user_id is None:
        g.user = None
    else:
        db = database.get_db()
        g.user = db.execute(
            "SELECT id, userid, password, grade, classroom, student_no FROM users WHERE userid = ?", (user_id,)
        ).fetchone()

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

# 📌 로그인 (DB 연동)
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
    grade = grade if grade is not None else "1"
    classroom = classroom if classroom is not None else "1"

    return render_template(
        "main.html",
        grade=grade,
        classroom=classroom,
        date=date_str,
        cache_buster=int(time.time()) # cache_buster 추가
    )

# 로그아웃 라우트
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main")) # 로그아웃 후 메인 페이지로 이동

# 📌 클래스 상세 페이지
@app.route("/class/<grade>-<classroom>")
def class_detail(grade, classroom):
    grade = grade if grade is not None else "1"
    classroom = classroom if classroom is not None else "1"

    db = database.get_db()
    posts = db.execute(
        "SELECT p.id, p.title, p.created_at, u.userid as author_userid "
        "FROM posts p JOIN users u ON p.author_id = u.id "
        "WHERE p.grade = ? AND p.classroom = ? "
        "ORDER BY p.created_at DESC",
        (grade, classroom)
    ).fetchall()

    return render_template(
        "class_detail.html",
        grade=grade,
        classroom=classroom,
        posts=posts, # 게시글 목록 전달
        cache_buster=int(time.time()) # cache_buster 추가
    )

# 📌 글쓰기 페이지
@app.route("/class/<grade>-<classroom>/write", methods=["GET", "POST"])
def write_post(grade, classroom):
    if g.user is None: # 로그인하지 않은 사용자는 글쓰기 불가
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")

        if not title or not content:
            # TODO: 에러 메시지를 템플릿으로 전달하여 표시
            return render_template("write.html", grade=grade, classroom=classroom, error="제목과 내용을 모두 입력해주세요.")

        db = database.get_db()
        db.execute(
            "INSERT INTO posts (grade, classroom, title, content, author_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (grade, classroom, title, content, g.user["id"], datetime.now().isoformat())
        )
        db.commit()
        return redirect(url_for("class_detail", grade=grade, classroom=classroom))

    return render_template(
        "write.html",
        grade=grade,
        classroom=classroom,
        cache_buster=int(time.time()) # cache_buster 추가
    )

# 📌 게시물 상세 페이지
@app.route("/class/<grade>-<classroom>/post/<int:post_id>")
def post_detail(grade, classroom, post_id):
    db = database.get_db()
    post = db.execute(
        "SELECT p.id, p.title, p.content, p.created_at, u.userid as author_userid "
        "FROM posts p JOIN users u ON p.author_id = u.id "
        "WHERE p.id = ?",
        (post_id,)
    ).fetchone()

    if post is None:
        return "게시물을 찾을 수 없습니다.", 404

    return render_template(
        "post_detail.html",
        grade=grade,
        classroom=classroom,
        post=post,
        cache_buster=int(time.time())
    )

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

        # NEIS API가 주의 시작일(월요일 등)부터 조회하면 데이터를 못가져오는 경우가 있어, 
        # 요청 날짜로부터 4일 이전부터 조회하여 API 제약을 우회합니다.
        start_date_for_api = (base_date - timedelta(days=4)).strftime("%Y%m%d")
        end_date_for_api = (base_date + timedelta(days=13)).strftime("%Y%m%d")

        all_timetable_data = neis.get_timetable_range(grade, classroom, start_date_for_api, end_date_for_api)
        
        # API로부터 받은 데이터에서, 사용자가 실제로 요청한 날짜부터 10일치(주중)만 필터링합니다.
        filtered_timetable = []
        fetched_count = 0
        for item in all_timetable_data:
            current_item_date = datetime.strptime(item['date'], "%Y%m%d")
            # 요청된 날짜(base_date) 이후이고, 주중(weekday < 5)인 경우에만 추가
            if current_item_date >= base_date and current_item_date.weekday() < 5:
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

# 📌 내 클래스 추가 API
@app.route("/api/add_class", methods=["POST"])
def add_class():
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    grade = request.json.get("grade")
    classroom = request.json.get("classroom")

    if not grade or not classroom:
        return jsonify({"success": False, "message": "학년과 반 정보를 입력해주세요."}), 400

    db = database.get_db()
    try:
        db.execute(
            "INSERT INTO classes (user_id, grade, classroom, created_at) VALUES (?, ?, ?, ?)",
            (g.user["id"], grade, classroom, datetime.now().isoformat())
        )
        db.commit()
        return jsonify({"success": True, "message": "클래스가 성공적으로 추가되었습니다."})
    except database.sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "이미 추가된 클래스입니다."}), 409
    except Exception as e:
        print(f"클래스 추가 중 오류 발생: {e}")
        return jsonify({"success": False, "message": "클래스 추가 중 오류가 발생했습니다."}), 500

# 📌 내 클래스 목록 조회 API
@app.route("/api/my_classes", methods=["GET"])
def get_my_classes():
    if g.user is None:
        return jsonify({"success": True, "classes": []}) # 로그인 안 했으면 빈 목록 반환

    db = database.get_db()
    classes = db.execute(
        "SELECT grade, classroom FROM classes WHERE user_id = ?",
        (g.user["id"],)
    ).fetchall()

    # Row 객체를 딕셔너리 리스트로 변환
    my_classes = [{"grade": c["grade"], "classroom": c["classroom"]} for c in classes]

    return jsonify({"success": True, "classes": my_classes})

if __name__ == "__main__":
    app.run(debug=config.DEBUG)