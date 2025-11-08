from flask import Flask, render_template, request, redirect, url_for, jsonify, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
<<<<<<< HEAD
import time
=======
import time # time 모듈 추가
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
import hashlib
import bleach

import config
import database
import neis
import crypto_utils

app = Flask(__name__)
app.config.from_object(config)

<<<<<<< HEAD
# 캐시 디렉토리가 없으면 생성
if not os.path.exists(config.CACHE_DIR):
    os.makedirs(config.CACHE_DIR)

# 데이터베이스 초기화
=======
# 캐시 디렉토리가 없으면 생성 (PythonAnywhere 같은 WSGI 서버 환경을 위함)
if not os.path.exists(config.CACHE_DIR):
    os.makedirs(config.CACHE_DIR)

# 데이터베이스 초기화 및 teardown 등록
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
database.init_app(app)

@app.before_request
def load_logged_in_user_and_session():
    if 'session_id' not in session:
        session['session_id'] = os.urandom(24).hex()
    g.session_id = session['session_id']

    user_id = session.get("user")
    if user_id is None:
        g.user = None
    else:
        db = database.get_db()
        g.user = db.execute(
<<<<<<< HEAD
            "SELECT id, userid, password, name, grade, classroom, student_no FROM users WHERE userid = ?",
            (user_id,)
=======
            "SELECT id, userid, password, name, grade, classroom, student_no FROM users WHERE userid = ?", (user_id,)
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
        ).fetchone()

# --- 헬퍼 ---
def pw_class_count(password):
    cnt = 0
    if any(c.islower() for c in password): cnt += 1
    if any(c.isupper() for c in password): cnt += 1
    if any(c.isdigit() for c in password): cnt += 1
    if any(not c.isalnum() for c in password): cnt += 1
    return cnt

def generate_invite_code(grade, classroom):
<<<<<<< HEAD
    secret = app.config.get("SECRET_KEY", "default-secret") or "default-secret-for-testing"
    data = f"{secret}-{grade}-{classroom}"
    return hashlib.sha256(data.encode()).hexdigest()[:6].upper()

# --- 라우트 ---
=======
    """학년, 반, 비밀키를 조합하여 고유한 초대 코드를 생성합니다."""
    secret = app.config.get("SECRET_KEY", "default-secret")
    # SECRET_KEY가 None일 경우를 대비하여 기본값 제공
    if not secret:
        secret = "default-secret-for-testing"
    data = f"{secret}-{grade}-{classroom}"
    return hashlib.sha256(data.encode()).hexdigest()[:6].upper()

# --- 라우트 정의 ---
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6

@app.route("/")
def index():
    return redirect(url_for("main"))

# 회원가입
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
        if len(password) < 8:
            return render_template("register.html", error="비밀번호는 8자 이상이어야 합니다.")
        if pw_class_count(password) < 3:
            return render_template("register.html", error="비밀번호는 소문자·대문자·숫자·특수문자 중 3가지 이상을 포함해야 합니다.")

        if student_no:
            if not (student_no.isdigit() and len(student_no) == 5):
                return render_template("register.html", error="학번은 정확히 5자리 숫자여야 합니다.")
            grade = student_no[0]
            classroom = str(int(student_no[1:3]))
        else:
            grade = None
            classroom = None

        enc_sn = crypto_utils.aesgcm_encrypt(student_no.encode()) if student_no else None

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

# 로그인
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        userid = request.form["userid"]
        password = request.form["password"]
        db = database.get_db()
        user = db.execute("SELECT * FROM users WHERE userid = ?", (userid,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session["user"] = userid
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

# 메인
@app.route("/main")
def main():
    today = datetime.now()
    date_str = today.strftime("%Y%m%d")

    grade = request.args.get("grade")
    classroom = request.args.get("classroom")

<<<<<<< HEAD
=======
    # URL 인자로 특정 학급이 명시된 경우, 권한 검사를 수행
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
    if grade and classroom:
        try:
            grade_num, class_num = int(grade), int(classroom)
            if not (1 <= grade_num <= 3 and 1 <= class_num <= 10):
                flash("존재하지 않는 학급입니다.")
<<<<<<< HEAD
                return redirect(url_for("main"))
=======
                return redirect(url_for("main")) # 인자 없이 메인으로
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
        except ValueError:
            flash("유효하지 않은 학급 정보입니다.")
            return redirect(url_for("main"))

<<<<<<< HEAD
        unlocked_classes = session.get('unlocked_classes', [])
        class_identifier = f"{grade}-{classroom}"
        is_admin = g.user and g.user['userid'] == 'admin'
        if not is_admin and class_identifier not in unlocked_classes:
            return redirect(url_for('unlock_class', grade=grade, classroom=classroom))
=======
        # 초대 코드 검사
        unlocked_classes = session.get('unlocked_classes', [])
        class_identifier = f"{grade}-{classroom}"
        is_admin = g.user and g.user['userid'] == 'admin'

        if not is_admin and class_identifier not in unlocked_classes:
            return redirect(url_for('unlock_class', grade=grade, classroom=classroom))
        # 권한이 있으면, 해당 학급으로 페이지를 렌더링

    # URL 인자가 없으면, 기존의 기본값 로직을 따름
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
    else:
        if session.get("student_no") and request.args.get("guest") != "1":
            sn = session.get("student_no", "")
            if sn and sn.isdigit() and len(sn) >= 5:
                grade = grade or sn[0]
                classroom = classroom or str(int(sn[1:3]))
<<<<<<< HEAD
=======
        
        # 기본값 설정
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
        grade = grade if grade is not None else "1"
        classroom = classroom if classroom is not None else "1"

    return render_template(
        "main.html",
        grade=grade,
        classroom=classroom,
        date=date_str,
        cache_buster=int(time.time())
    )

# 로그아웃
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main"))

# 클래스 상세
@app.route("/class/<grade>-<classroom>")
def class_detail(grade, classroom):
    try:
        grade_num = int(grade)
        class_num = int(classroom)
        if not (1 <= grade_num <= 3 and 1 <= class_num <= 10):
            flash("존재하지 않는 학급입니다.")
            return redirect(url_for("main"))
    except ValueError:
        flash("유효하지 않은 학급 경로입니다.")
        return redirect(url_for("main"))

<<<<<<< HEAD
    unlocked_classes = session.get('unlocked_classes', [])
    class_identifier = f"{grade}-{classroom}"

    if g.user and g.user['userid'] != 'admin' and class_identifier not in unlocked_classes:
        return redirect(url_for('unlock_class', grade=grade, classroom=classroom))
    elif not g.user and class_identifier not in unlocked_classes:
        return redirect(url_for('unlock_class', grade=grade, classroom=classroom))

    if g.user and g.user['userid'] == 'admin':
        correct_code = generate_invite_code(grade, classroom)
        flash(f'{grade}학년 {classroom}반의 초대 코드는 \'{correct_code}\'입니다. 학생들에게 이 코드를 알려주세요.', 'info')

    db = database.get_db()
    posts = db.execute(
        "SELECT p.id, p.title, p.created_at, p.is_pinned, p.pinned_at, u.name as author_name "
=======
    # 초대 코드 검사
    unlocked_classes = session.get('unlocked_classes', [])
    class_identifier = f"{grade}-{classroom}"

    # 관리자가 아니고, 아직 잠금 해제되지 않은 클래스인 경우
    if g.user and g.user['userid'] != 'admin' and class_identifier not in unlocked_classes:
        return redirect(url_for('unlock_class', grade=grade, classroom=classroom))
    # 비로그인 사용자는 무조건 잠금 해제 페이지로
    elif not g.user and class_identifier not in unlocked_classes:
        return redirect(url_for('unlock_class', grade=grade, classroom=classroom))

    # 관리자에게는 현재 클래스의 초대 코드를 항상 보여줌
    if g.user and g.user['userid'] == 'admin':
        correct_code = generate_invite_code(grade, classroom)
        flash(f'{grade}학년 {classroom}반의 초대 코드는 \'{correct_code}\'입니다. 학생들에게 이 코드를 알려주세요.', 'info')

    db = database.get_db()

    db = database.get_db()
    posts = db.execute(
        "SELECT p.id, p.title, p.created_at, u.name as author_name "
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
        "FROM posts p JOIN users u ON p.author_id = u.id "
        "WHERE p.grade = ? AND p.classroom = ? "
        "ORDER BY p.is_pinned DESC, COALESCE(p.pinned_at, p.created_at) DESC, p.created_at DESC",
        (grade, classroom)
    ).fetchall()

    return render_template(
        "class_detail.html",
        grade=grade,
        classroom=classroom,
        posts=posts,
        cache_buster=int(time.time())
    )

# 글쓰기
@app.route("/class/<grade>-<classroom>/write", methods=["GET", "POST"])
def write_post(grade, classroom):
    try:
        grade_num = int(grade)
        class_num = int(classroom)
        if not (1 <= grade_num <= 3 and 1 <= class_num <= 10):
            flash("존재하지 않는 학급입니다.")
            return redirect(url_for("main"))
    except ValueError:
        flash("유효하지 않은 학급 경로입니다.")
        return redirect(url_for("main"))

<<<<<<< HEAD
=======
    # 초대 코드 검사 (class_detail과 동일)
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
    unlocked_classes = session.get('unlocked_classes', [])
    class_identifier = f"{grade}-{classroom}"
    is_admin = g.user and g.user['userid'] == 'admin'

    if not is_admin and class_identifier not in unlocked_classes:
<<<<<<< HEAD
        return redirect(url_for('unlock_class', grade=grade, classroom=classroom))

    if g.user is None:
=======
        # 글쓰기는 로그인 사용자만 가능하므로, 비로그인 경우는 class_detail에서 이미 처리됨
        return redirect(url_for('unlock_class', grade=grade, classroom=classroom))

    if g.user is None: # 로그인하지 않은 사용자는 글쓰기 불가
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        if not title or not content:
            return render_template("write.html", grade=grade, classroom=classroom, error="제목과 내용을 모두 입력해주세요.")
        db = database.get_db()
        db.execute(
            "INSERT INTO posts (grade, classroom, title, content, author_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (grade, classroom, title, content, g.user["id"], datetime.now().isoformat())
        )
        db.commit()
        return redirect(url_for("class_detail", grade=grade, classroom=classroom))

    return render_template("write.html", grade=grade, classroom=classroom, cache_buster=int(time.time()))

# 게시물 상세
@app.route("/class/<grade>-<classroom>/post/<int:post_id>")
def post_detail(grade, classroom, post_id):
    try:
        grade_num = int(grade)
        class_num = int(classroom)
        if not (1 <= grade_num <= 3 and 1 <= class_num <= 10):
            flash("존재하지 않는 학급입니다.")
            return redirect(url_for("main"))
    except ValueError:
        flash("유효하지 않은 학급 경로입니다.")
        return redirect(url_for("main"))

<<<<<<< HEAD
=======
    # 초대 코드 검사 (class_detail과 동일)
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
    unlocked_classes = session.get('unlocked_classes', [])
    class_identifier = f"{grade}-{classroom}"
    is_admin = g.user and g.user['userid'] == 'admin'

    if not is_admin and class_identifier not in unlocked_classes:
        return redirect(url_for('unlock_class', grade=grade, classroom=classroom))

    db = database.get_db()
    post = db.execute(
<<<<<<< HEAD
        "SELECT p.id, p.title, p.content, p.created_at, p.is_pinned, p.pinned_at, u.name as author_name "
=======
        "SELECT p.id, p.title, p.content, p.created_at, u.name as author_name "
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
        "FROM posts p JOIN users u ON p.author_id = u.id "
        "WHERE p.id = ?",
        (post_id,)
    ).fetchone()

    if post is None:
        return "게시물을 찾을 수 없습니다.", 404

<<<<<<< HEAD
=======
    # XSS 방지를 위해 bleach로 content를 소독하고, 줄바꿈을 <br>로 변환
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
    sanitized_content = bleach.clean(post['content'])
    formatted_content = sanitized_content.replace('\n', '<br>')

    return render_template(
        "post_detail.html",
        grade=grade,
        classroom=classroom,
        post=post,
<<<<<<< HEAD
        formatted_content=formatted_content,
        cache_buster=int(time.time())
    )

# ★ 게시글 고정/해제 토글
@app.route("/class/<grade>-<classroom>/post/<int:post_id>/pin", methods=["POST"])
def toggle_pin_post(grade, classroom, post_id):
    # 권한 체크: 관리자만 허용 (필요 시 작성자 허용으로 변경 가능)
    if not g.user or g.user['userid'] != 'admin':
        flash("게시글 고정은 관리자만 가능합니다.")
        return redirect(url_for("class_detail", grade=grade, classroom=classroom))

    action = request.form.get("action", "toggle")
    db = database.get_db()
    row = db.execute(
        "SELECT is_pinned FROM posts WHERE id = ? AND grade = ? AND classroom = ?",
        (post_id, grade, classroom)
    ).fetchone()
    if not row:
        flash("게시글을 찾을 수 없습니다.")
        return redirect(url_for("class_detail", grade=grade, classroom=classroom))

    is_pinned = int(row["is_pinned"]) if row["is_pinned"] is not None else 0

    if action == "pin":
        is_pinned = 1
        pinned_at = datetime.now().isoformat()
    elif action == "unpin":
        is_pinned = 0
        pinned_at = None
    else:  # toggle
        if is_pinned:
            is_pinned = 0
            pinned_at = None
        else:
            is_pinned = 1
            pinned_at = datetime.now().isoformat()

    db.execute(
        "UPDATE posts SET is_pinned = ?, pinned_at = ? WHERE id = ?",
        (is_pinned, pinned_at, post_id)
    )
    db.commit()

    msg = "게시글을 상단에 고정했습니다." if is_pinned else "게시글 고정을 해제했습니다."
    flash(msg, "info")
    # 원래 페이지로 리디렉트 (상세/목록 둘 중에서 보낼 수도 있음)
    next_url = request.form.get("next") or url_for("class_detail", grade=grade, classroom=classroom)
    return redirect(next_url)

# 초대 코드 잠금 해제
=======
        formatted_content=formatted_content, # 소독된 내용을 전달
        cache_buster=int(time.time())
    )

# 📌 초대 코드로 클래스 잠금 해제
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
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
<<<<<<< HEAD
            return redirect(url_for("class_detail", grade=grade, classroom=classroom))
        else:
            flash("초대 코드가 올바르지 않습니다.")

    return render_template("unlock_class.html", grade=grade, classroom=classroom)

# API: 급식/시간표
=======

            return redirect(url_for("class_detail", grade=grade, classroom=classroom))
        else:
            flash("초대 코드가 올바르지 않습니다.")
    
    # GET 요청이거나 POST에서 코드가 틀렸을 경우
    return render_template("unlock_class.html", grade=grade, classroom=classroom)

# 📌 API 데이터 요청
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
@app.route("/api/data", methods=["GET"])
def api_data():
    date_str = request.args.get("date", datetime.now().strftime("%Y%m%d"))
    grade = request.args.get("grade", "1")
    classroom = request.args.get("classroom", "1")

    response_data = {}
    meal_data = neis.get_meal(date_str)
    response_data["meal"] = meal_data

    try:
        base_date = datetime.strptime(date_str, "%Y%m%d")
        start_date_for_api = (base_date - timedelta(days=4)).strftime("%Y%m%d")
        end_date_for_api = (base_date + timedelta(days=13)).strftime("%Y%m%d")
        all_timetable_data = neis.get_timetable_range(grade, classroom, start_date_for_api, end_date_for_api)

        filtered_timetable = []
        fetched_count = 0
        for item in all_timetable_data:
            current_item_date = datetime.strptime(item['date'], "%Y%m%d")
            if current_item_date >= base_date and current_item_date.weekday() < 5:
                filtered_timetable.append(item)
                fetched_count += 1
            if fetched_count >= 10:
                break
        response_data["timetable"] = filtered_timetable
    except Exception as e:
        print(f"시간표 데이터 처리 중 오류 발생 ({date_str}): {e}")
        response_data["timetable"] = []

    response_data["grade"] = grade
    response_data["classroom"] = classroom
    response_data["date"] = date_str
    return jsonify(response_data)

<<<<<<< HEAD
# [NEW] 초대 코드로 내 클래스 추가
@app.route("/api/add_class_by_code", methods=["POST"])
def add_class_by_code():
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    submitted_code = request.json.get("invite_code", "").upper()
    if not submitted_code or len(submitted_code) != 6:
        return jsonify({"success": False, "message": "초대 코드는 6자리여야 합니다."}), 400

    found_class = None
    for grade_num in range(1, 4):
        for class_num in range(1, 11):
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
=======

>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6

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
<<<<<<< HEAD
=======

        # 2. 세션에 "잠금 해제" 상태 추가
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
        unlocked_classes = session.get('unlocked_classes', [])
        class_identifier = f"{found_class['grade']}-{found_class['classroom']}"
        if class_identifier not in unlocked_classes:
            unlocked_classes.append(class_identifier)
            session['unlocked_classes'] = unlocked_classes
<<<<<<< HEAD
=======

>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
        return jsonify({"success": True, "message": "클래스가 성공적으로 추가되었습니다."})

    except database.sqlite3.IntegrityError:
<<<<<<< HEAD
=======
        # 이미 "내 클래스"에 있는 경우, 잠금 해제만 처리
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
        unlocked_classes = session.get('unlocked_classes', [])
        class_identifier = f"{found_class['grade']}-{found_class['classroom']}"
        if class_identifier not in unlocked_classes:
            unlocked_classes.append(class_identifier)
            session['unlocked_classes'] = unlocked_classes
        return jsonify({"success": True, "message": "이미 추가된 클래스입니다."})
    except Exception as e:
        print(f"클래스 추가 중 오류 발생: {e}")
        return jsonify({"success": False, "message": "클래스 추가 중 오류가 발생했습니다."}), 500

# 내 클래스 목록
@app.route("/api/my_classes", methods=["GET"])
def get_my_classes():
    if g.user is None:
<<<<<<< HEAD
        return jsonify({"success": True, "classes": []})

=======
        return jsonify({"success": True, "classes": []}) # 로그인 안 했으면 빈 목록 반환

    # 관리자에게는 모든 클래스 목록을 반환
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
    if g.user['userid'] == 'admin':
        all_classes = []
        for grade_num in range(1, 4):
            for class_num in range(1, 11):
                all_classes.append({"grade": str(grade_num), "classroom": str(class_num)})
        return jsonify({"success": True, "classes": all_classes})

<<<<<<< HEAD
=======
    # 일반 사용자는 DB에서 조회
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
    db = database.get_db()
    classes = db.execute(
        "SELECT grade, classroom FROM classes WHERE user_id = ?",
        (g.user["id"],)
    ).fetchall()
    my_classes = [{"grade": c["grade"], "classroom": c["classroom"]} for c in classes]
    return jsonify({"success": True, "classes": my_classes})

if __name__ == "__main__":
<<<<<<< HEAD
    app.run(debug=config.DEBUG)
=======
    app.run(debug=config.DEBUG)
>>>>>>> b6d107aab70b91aa4833b663fb4982a0e52ac1b6
