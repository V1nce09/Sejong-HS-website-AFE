from flask import Flask, render_template, request, redirect, url_for, jsonify, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import time # time 모듈 추가
import hashlib
import bleach

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
            "SELECT id, userid, password, name, grade, classroom, student_no FROM users WHERE userid = ?", (user_id,)
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

def generate_invite_code(grade, classroom):
    """학년, 반, 비밀키를 조합하여 고유한 초대 코드를 생성합니다."""
    secret = app.config.get("SECRET_KEY", "default-secret")
    # SECRET_KEY가 None일 경우를 대비하여 기본값 제공
    if not secret:
        secret = "default-secret-for-testing"
    data = f"{secret}-{grade}-{classroom}"
    return hashlib.sha256(data.encode()).hexdigest()[:6].upper()

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
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        student_no = request.form.get("student_no", "").strip()

        if not userid or not password or not name:
            return render_template("register.html", error="아이디, 이름, 비밀번호를 모두 입력하세요.")
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
                "INSERT INTO users (userid, name, password, grade, classroom, student_no, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (userid, name, generate_password_hash(password), grade, classroom, enc_sn, datetime.now().isoformat())
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
            session["display_name"] = user["name"]
            return redirect(url_for("main"))
        return render_template("login.html", error="아이디 또는 비밀번호가 올바르지 않습니다.")
    return render_template("login.html")

# --- main route: 로그인한 학생이면 자동으로 오늘 학급 시간표/급식 미리 로드 ---
@app.route("/main")
def main():
    # 오늘 날짜 문자열
    today = datetime.now()
    date_str = today.strftime("%Y%m%d")

    grade = request.args.get("grade")
    classroom = request.args.get("classroom")

    # URL 인자로 특정 학급이 명시된 경우, 권한 검사를 수행
    if grade and classroom:
        try:
            grade_num, class_num = int(grade), int(classroom)
            if not (1 <= grade_num <= 3 and 1 <= class_num <= 10):
                flash("존재하지 않는 학급입니다.")
                return redirect(url_for("main")) # 인자 없이 메인으로
        except ValueError:
            flash("유효하지 않은 학급 정보입니다.")
            return redirect(url_for("main"))

        # 초대 코드 검사
        unlocked_classes = session.get('unlocked_classes', [])
        class_identifier = f"{grade}-{classroom}"
        is_admin = g.user and g.user['userid'] == 'admin'

        if not is_admin and class_identifier not in unlocked_classes:
            return redirect(url_for('unlock_class', grade=grade, classroom=classroom))
        # 권한이 있으면, 해당 학급으로 페이지를 렌더링

    # URL 인자가 없으면, 기존의 기본값 로직을 따름
    else:
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
@app.route("/class/<grade>/<classroom>")
def class_detail(grade, classroom):
    # 공통 변수
    db = database.get_db()
    posts = []
    is_authorized = False
    class_identifier = f"{grade}-{classroom}"
    is_admin = g.user and g.user['userid'] == 'admin'

    # 1. 관리자 전용 클래스
    if grade == 'admin' and classroom == 'general':
        if is_admin:
            is_authorized = True
            posts = db.execute(
                "SELECT p.id, p.title, p.created_at, u.name as author_name "
                "FROM posts p JOIN users u ON p.author_id = u.id "
                "WHERE p.grade = 0 AND p.classroom = 0 "
                "ORDER BY p.created_at DESC"
            ).fetchall()
        else:
            flash("관리자만 접근할 수 있습니다.")
            return redirect(url_for("main"))

    # 2. 학년 통합 클래스
    elif classroom == 'combined':
        try:
            grade_num = int(grade)
            if not (1 <= grade_num <= 3):
                flash("존재하지 않는 학년입니다.")
                return redirect(url_for("main"))
        except ValueError:
            flash("유효하지 않은 학년 정보입니다.")
            return redirect(url_for("main"))

        # 관리자이거나 해당 학년 학생이면 접근 가능
        if is_admin or (g.user and g.user['grade'] == grade):
            is_authorized = True
            posts = db.execute(
                "SELECT p.id, p.title, p.created_at, u.name as author_name "
                "FROM posts p JOIN users u ON p.author_id = u.id "
                "WHERE p.grade = ? AND p.classroom = 0 "
                "ORDER BY p.created_at DESC",
                (grade,)
            ).fetchall()
        else:
            flash(f"{grade}학년 학생만 접근할 수 있습니다.")
            return redirect(url_for("main"))

    # 3. 일반 학급
    else:
        try:
            grade_num, class_num = int(grade), int(classroom)
            if not (1 <= grade_num <= 3 and 1 <= class_num <= 10):
                flash("존재하지 않는 학급입니다.")
                return redirect(url_for("main"))
        except ValueError:
            flash("유효하지 않은 학급 정보입니다.")
            return redirect(url_for("main"))

        unlocked_classes = session.get('unlocked_classes', [])
        if is_admin or class_identifier in unlocked_classes:
            is_authorized = True
            posts = db.execute(
                "SELECT p.id, p.title, p.created_at, u.name as author_name "
                "FROM posts p JOIN users u ON p.author_id = u.id "
                "WHERE p.grade = ? AND p.classroom = ? "
                "ORDER BY p.created_at DESC",
                (grade, classroom)
            ).fetchall()
        else:
            # 잠금 해제되지 않았으면 잠금 해제 페이지로
            return redirect(url_for('unlock_class', grade=grade, classroom=classroom))

    # 관리자에게는 현재 클래스의 초대 코드를 항상 보여줌 (일반 학급만)
    if is_admin and classroom != 'combined' and grade != 'admin':
        correct_code = generate_invite_code(grade, classroom)
        flash(f'{grade}학년 {classroom}반의 초대 코드는 \'{correct_code}\'입니다. 학생들에게 이 코드를 알려주세요.', 'info')

    return render_template(
        "class_detail.html",
        grade=grade,
        classroom=classroom,
        posts=posts,
        cache_buster=int(time.time())
    )

# 📌 글쓰기 페이지
@app.route("/class/<grade>/<classroom>/write", methods=["GET", "POST"])
def write_post(grade, classroom):
    is_authorized = False
    is_admin = g.user and g.user['userid'] == 'admin'

    if g.user is None: # 로그인하지 않은 사용자는 글쓰기 불가
        flash("글을 작성하려면 로그인이 필요합니다.")
        return redirect(url_for("login"))

    # 1. 관리자 전용 클래스
    if grade == 'admin' and classroom == 'general':
        if is_admin:
            is_authorized = True
        else:
            flash("관리자만 글을 작성할 수 있습니다.")
            return redirect(url_for("main"))
    # 2. 학년 통합 클래스
    elif classroom == 'combined':
        if is_admin or (g.user and g.user['grade'] == grade):
            is_authorized = True
        else:
            flash(f"{grade}학년 학생만 글을 작성할 수 있습니다.")
            return redirect(url_for("main"))
    # 3. 일반 학급
    else:
        unlocked_classes = session.get('unlocked_classes', [])
        class_identifier = f"{grade}-{classroom}"
        if is_admin or class_identifier in unlocked_classes:
            is_authorized = True
        else:
            # 잠금 해제되지 않은 경우, class_detail로 보내면 거기서 unlock_class로 리다이렉트됨
            flash("글을 작성할 권한이 없는 학급입니다.")
            return redirect(url_for("class_detail", grade=grade, classroom=classroom))

    if not is_authorized:
        # 이중 안전장치
        flash("글을 작성할 권한이 없습니다.")
        return redirect(url_for("main"))

    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")

        if not title or not content:
            flash("제목과 내용을 모두 입력해주세요.", "error")
            return render_template("write.html", grade=grade, classroom=classroom)

        # DB에 저장할 grade, classroom 결정
        post_grade, post_classroom = grade, classroom
        if grade == 'admin':
            post_grade, post_classroom = 0, 0
        elif classroom == 'combined':
            post_classroom = 0
        
        db = database.get_db()
        db.execute(
            "INSERT INTO posts (grade, classroom, title, content, author_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (post_grade, post_classroom, title, content, g.user["id"], datetime.now().isoformat())
        )
        db.commit()
        return redirect(url_for("class_detail", grade=grade, classroom=classroom))

    return render_template(
        "write.html",
        grade=grade,
        classroom=classroom,
        cache_buster=int(time.time())
    )

# 📌 게시물 상세 페이지
@app.route("/class/<grade>/<classroom>/post/<int:post_id>")
def post_detail(grade, classroom, post_id):
    is_authorized = False
    is_admin = g.user and g.user['userid'] == 'admin'

    # 1. 관리자 전용 클래스
    if grade == 'admin' and classroom == 'general':
        if is_admin:
            is_authorized = True
        else:
            flash("관리자만 접근할 수 있습니다.")
            return redirect(url_for("main"))
    # 2. 학년 통합 클래스
    elif classroom == 'combined':
        # 관리자이거나 해당 학년 학생이면 접근 가능
        if is_admin or (g.user and g.user['grade'] == grade):
            is_authorized = True
        else:
            flash(f"{grade}학년 학생만 접근할 수 있습니다.")
            return redirect(url_for("main"))
    # 3. 일반 학급
    else:
        unlocked_classes = session.get('unlocked_classes', [])
        class_identifier = f"{grade}-{classroom}"
        if is_admin or class_identifier in unlocked_classes:
            is_authorized = True
        else:
            return redirect(url_for('unlock_class', grade=grade, classroom=classroom))
    
    if not is_authorized:
        flash("게시물을 볼 권한이 없습니다.")
        return redirect(url_for("main"))

    db = database.get_db()
    post = db.execute(
        "SELECT p.id, p.title, p.content, p.created_at, u.name as author_name "
        "FROM posts p JOIN users u ON p.author_id = u.id "
        "WHERE p.id = ?",
        (post_id,)
    ).fetchone()

    if post is None:
        return "게시물을 찾을 수 없습니다.", 404

    # XSS 방지를 위해 bleach로 content를 소독하고, 줄바꿈을 <br>로 변환
    sanitized_content = bleach.clean(post['content'])
    formatted_content = sanitized_content.replace('\n', '<br>')

    return render_template(
        "post_detail.html",
        grade=grade,
        classroom=classroom,
        post=post,
        formatted_content=formatted_content,
        cache_buster=int(time.time())
    )

# 📌 초대 코드로 클래스 잠금 해제
@app.route("/class/unlock", methods=["GET", "POST"])
def unlock_class():
    grade = request.args.get("grade")
    classroom = request.args.get("classroom")

    if not grade or not classroom:
        flash("잘못된 접근입니다.")
        return redirect(url_for("main"))

    if request.method == "POST":
        submitted_code = request.form.get("invite_code", "").upper()
        correct_code = generate_invite_code(grade, classroom)

        if submitted_code == correct_code:
            unlocked_classes = session.get('unlocked_classes', [])
            class_identifier = f"{grade}-{classroom}"
            if class_identifier not in unlocked_classes:
                unlocked_classes.append(class_identifier)
                session['unlocked_classes'] = unlocked_classes

            return redirect(url_for("class_detail", grade=grade, classroom=classroom))
        else:
            flash("초대 코드가 올바르지 않습니다.")
    
    # GET 요청이거나 POST에서 코드가 틀렸을 경우
    return render_template("unlock_class.html", grade=grade, classroom=classroom)

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



# 📌 [NEW] 초대 코드로 내 클래스 추가 API
@app.route("/api/add_class_by_code", methods=["POST"])
def add_class_by_code():
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    submitted_code = request.json.get("invite_code", "").upper()
    if not submitted_code or len(submitted_code) != 6:
        return jsonify({"success": False, "message": "초대 코드는 6자리여야 합니다."}), 400

    # 모든 유효한 학급에 대해 코드를 생성하여 일치하는 것을 찾음
    found_class = None
    for grade_num in range(1, 4):
        for class_num in range(1, 11):
            # 유효성 검사 (1-3학년, 1-10반)
            if not (1 <= grade_num <= 3 and 1 <= class_num <= 10):
                 continue

            grade_str = str(grade_num)
            class_str = str(class_num)
            correct_code = generate_invite_code(grade_str, class_str)
            if correct_code == submitted_code:
                found_class = {"grade": grade_str, "classroom": class_str}
                break
        if found_class:
            break

    if not found_class:
        return jsonify({"success": False, "message": "초대 코드가 올바르지 않습니다."}), 404

    # 찾았으면 DB에 추가 및 세션 업데이트
    db = database.get_db()
    try:
        # 1. DB에 "내 클래스"로 추가
        db.execute(
            "INSERT INTO classes (user_id, grade, classroom, created_at) VALUES (?, ?, ?, ?)",
            (g.user["id"], found_class["grade"], found_class["classroom"], datetime.now().isoformat())
        )
        db.commit()

        # 2. 세션에 "잠금 해제" 상태 추가
        unlocked_classes = session.get('unlocked_classes', [])
        class_identifier = f"{found_class['grade']}-{found_class['classroom']}"
        if class_identifier not in unlocked_classes:
            unlocked_classes.append(class_identifier)
            session['unlocked_classes'] = unlocked_classes

        return jsonify({"success": True, "message": "클래스가 성공적으로 추가되었습니다."})

    except database.sqlite3.IntegrityError:
        # 이미 "내 클래스"에 있는 경우, 잠금 해제만 처리
        unlocked_classes = session.get('unlocked_classes', [])
        class_identifier = f"{found_class['grade']}-{found_class['classroom']}"
        if class_identifier not in unlocked_classes:
            unlocked_classes.append(class_identifier)
            session['unlocked_classes'] = unlocked_classes
        return jsonify({"success": True, "message": "이미 추가된 클래스입니다."})
    except Exception as e:
        print(f"클래스 추가 중 오류 발생: {e}")
        return jsonify({"success": False, "message": "클래스 추가 중 오류가 발생했습니다."}), 500

# 📌 내 클래스 목록 조회 API
@app.route("/api/my_classes", methods=["GET"])
def get_my_classes():
    if g.user is None:
        return jsonify({"success": True, "classes": []}) # 로그인 안 했으면 빈 목록 반환

    my_classes = []

    # 관리자에게는 모든 클래스 목록과 관리자 전용 클래스를 반환
    if g.user['userid'] == 'admin':
        # 관리자 전용 클래스 추가
        my_classes.append({"grade": "admin", "classroom": "general", "display_name": "관리자 전용"})
        # 각 학년 통합 클래스 추가
        for grade_num in range(1, 4):
            my_classes.append({"grade": str(grade_num), "classroom": "combined", "display_name": f"{grade_num}학년 통합"})
        # 모든 일반 학급 추가
        for grade_num in range(1, 4):
            for class_num in range(1, 11):
                 # 2학년은 10반까지, 나머지는 9반까지 있다고 가정
                if grade_num == 2 and class_num > 10: continue
                if grade_num != 2 and class_num > 9: continue
                my_classes.append({"grade": str(grade_num), "classroom": str(class_num), "display_name": f"{grade_num}학년 {class_num}반"})
        
        return jsonify({"success": True, "classes": my_classes})

    # 일반 사용자는 DB에서 '내 클래스' 조회
    db = database.get_db()
    classes_from_db = db.execute(
        "SELECT grade, classroom FROM classes WHERE user_id = ?",
        (g.user["id"],)
    ).fetchall()

    # Row 객체를 딕셔너리 리스트로 변환
    my_classes.extend([{"grade": c["grade"], "classroom": c["classroom"], "display_name": f'{c["grade"]}학년 {c["classroom"]}반'} for c in classes_from_db])

    # 사용자의 학년 통합 클래스 추가
    if g.user and g.user['grade']:
        user_grade = g.user['grade']
        # 중복 추가 방지
        if not any(c['grade'] == user_grade and c['classroom'] == 'combined' for c in my_classes):
            my_classes.insert(0, {"grade": user_grade, "classroom": "combined", "display_name": f"{user_grade}학년 통합"})

    return jsonify({"success": True, "classes": my_classes})

if __name__ == "__main__":
    app.run(debug=config.DEBUG)