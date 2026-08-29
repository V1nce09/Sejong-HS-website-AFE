from flask import Flask, render_template, request, redirect, url_for, jsonify, session, g, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import time # time 모듈 추가
import hashlib
import re
import secrets
import string
import bleach
from collections import defaultdict, deque

import config
import database
import neis
import weather
import crypto_utils
import post_images

SCHOOL_TZ = ZoneInfo("Asia/Seoul")

app = Flask(__name__)
app.config.from_object(config) # config.py에서 설정 로드


@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory(app.static_folder, "service-worker.js", mimetype="application/javascript", max_age=0)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


# --- 보안 계층 ---
_RATE_BUCKETS = defaultdict(deque)
_RATE_BLOCKED = {}
_RATE_PRUNE_LOCK = None

def _client_ip():
    # Cloudflare 프록시를 명시적으로 활성화한 경우에만 CF-Connecting-IP를 신뢰합니다.
    if config.TRUST_CLOUDFLARE:
        return (request.headers.get("CF-Connecting-IP") or request.remote_addr or "unknown")[:100]
    return (request.remote_addr or "unknown")[:100]

def _student_no_hash(plain):
    if not plain:
        return ""
    return hashlib.sha256(str(plain).strip().encode("utf-8")).hexdigest()

def _blacklist_match(db, user=None, ip=None):
    ip = ip or _client_ip()
    if ip and db.execute("SELECT 1 FROM blacklist WHERE ip = ? AND active = 1 LIMIT 1", (ip,)).fetchone():
        return True
    if user is not None:
        if db.execute("SELECT 1 FROM blacklist WHERE user_id = ? AND active = 1 LIMIT 1", (int(user["id"]),)).fetchone():
            return True
        if db.execute("SELECT 1 FROM blacklist WHERE userid = ? AND active = 1 LIMIT 1", (str(user["userid"]),)).fetchone():
            return True
        plain = _decrypt_student_no(user["student_no"])
        h = _student_no_hash(plain)
        if h and db.execute("SELECT 1 FROM blacklist WHERE student_no_hash = ? AND active = 1 LIMIT 1", (h,)).fetchone():
            return True
    return False

def _record_security_event(db, event_type, details="", user=None, ip=None):
    ip = ip or _client_ip()
    uid = int(user["id"]) if user is not None else None
    userid = str(user["userid"]) if user is not None else None
    sn_hash = _student_no_hash(_decrypt_student_no(user["student_no"])) if user is not None else ""
    db.execute(
        "INSERT INTO security_events (user_id, userid, student_no_hash, ip, path, method, event_type, details, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, userid, sn_hash, ip, request.path[:500], request.method[:10], str(event_type)[:80], str(details)[:500], datetime.now().isoformat()),
    )
    db.commit()
    if user is not None and not _is_admin(user):
        cutoff = (datetime.now() - timedelta(seconds=config.SECURITY_EVENT_WINDOW_SECONDS)).isoformat()
        row = db.execute(
            "SELECT COUNT(*) AS cnt FROM security_events WHERE user_id = ? AND created_at >= ? AND event_type IN ('invalid_csrf','rate_limit','unauthorized_admin','blocked_method')",
            (int(user["id"]), cutoff),
        ).fetchone()
        if row and int(row["cnt"]) >= config.SECURITY_EVENT_BLACKLIST_THRESHOLD:
            reason = "반복적인 비정상 요청"
            db.execute("INSERT INTO blacklist (user_id, userid, student_no_hash, ip, reason, created_at, active) VALUES (?, ?, ?, ?, ?, ?, 1)", (uid, userid, sn_hash or None, None, reason, datetime.now().isoformat()))
            db.commit()
            return True
    return False

def _rate_limit_allowed(key, limit, window=60):
    now = time.monotonic()
    blocked_until = _RATE_BLOCKED.get(key, 0)
    if blocked_until > now:
        return False
    q = _RATE_BUCKETS[key]
    cutoff = now - window
    while q and q[0] <= cutoff:
        q.popleft()
    q.append(now)
    if len(q) > limit:
        _RATE_BLOCKED[key] = now + config.RATE_BLOCK_SECONDS
        return False
    return True

def _login_lock_status(db, ip, userid):
    row = db.execute("SELECT locked_until FROM login_attempts WHERE ip = ? AND userid = ?", (ip, userid)).fetchone()
    if not row or not row["locked_until"]:
        return None
    try:
        until = datetime.fromisoformat(row["locked_until"])
    except ValueError:
        return None
    if until > datetime.now():
        return until
    return None

def _record_login_failure(db, ip, userid):
    now = datetime.now()
    row = db.execute("SELECT id, failed_count, first_failed_at FROM login_attempts WHERE ip = ? AND userid = ?", (ip, userid)).fetchone()
    if row:
        try: first = datetime.fromisoformat(row["first_failed_at"])
        except ValueError: first = now
        if (now-first).total_seconds() > config.LOGIN_FAIL_WINDOW_SECONDS:
            count = 1; first = now
        else:
            count = int(row["failed_count"]) + 1
        locked = None
        if count >= config.LOGIN_FAIL_LONG_LIMIT:
            locked = (now + timedelta(seconds=config.LOGIN_LONG_LOCK_SECONDS)).isoformat()
        elif count >= config.LOGIN_FAIL_LIMIT:
            locked = (now + timedelta(seconds=config.LOGIN_FAIL_WINDOW_SECONDS)).isoformat()
        db.execute("UPDATE login_attempts SET failed_count=?, first_failed_at=?, last_failed_at=?, locked_until=? WHERE id=?", (count, first.isoformat(), now.isoformat(), locked, row["id"]))
    else:
        db.execute("INSERT INTO login_attempts (ip, userid, failed_count, first_failed_at, last_failed_at, locked_until) VALUES (?, ?, 1, ?, ?, NULL)", (ip, userid, now.isoformat(), now.isoformat()))
    db.commit()
    row = db.execute("SELECT failed_count, locked_until FROM login_attempts WHERE ip = ? AND userid = ?", (ip, userid)).fetchone()
    return int(row["failed_count"]), row["locked_until"] if row else None

def _clear_login_failures(db, ip, userid):
    db.execute("DELETE FROM login_attempts WHERE ip = ? AND userid = ?", (ip, userid))
    db.commit()

def _csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token

@app.context_processor
def inject_security_context():
    return {"csrf_token": _csrf_token()}

# 캐시 디렉토리가 없으면 생성 (PythonAnywhere 같은 WSGI 서버 환경을 위함)
if not os.path.exists(config.CACHE_DIR):
    os.makedirs(config.CACHE_DIR)

# 데이터베이스 초기화 및 teardown 등록
database.init_app(app)

@app.errorhandler(413)
def request_too_large(_error):
    return "첨부 파일 용량이 너무 큽니다. 사진은 최대 3장, 원본 한 장당 8MB 이하로 첨부해주세요.", 413

@app.before_request
def load_logged_in_user_and_session():
    if 'session_id' not in session:
        session['session_id'] = os.urandom(24).hex()
    g.session_id = session['session_id']
    user_id = session.get("user")
    db = database.get_db()
    g.user = None
    if user_id is not None:
        if not session.permanent:
            session.permanent = True
        g.user = db.execute("SELECT id, userid, password, name, grade, classroom, student_no, is_teacher FROM users WHERE userid = ?", (user_id,)).fetchone()
        if g.user is None:
            session.clear(); session["session_id"] = os.urandom(24).hex(); g.session_id = session["session_id"]
        elif _is_admin(g.user):
            session.permanent = False
    # 블랙리스트 계정/IP는 정적 리소스까지 막지 않고 애플리케이션 요청만 차단합니다.
    if request.path.startswith('/static/') or request.path == '/service-worker.js':
        return None
    if _blacklist_match(db, g.user, _client_ip()):
        session.clear()
        return jsonify({"success": False, "message": "보안 정책에 의해 접근이 제한된 계정 또는 접속 환경입니다."}), 403
    ip = _client_ip()
    # 비로그인 사용자의 과도한 새로고침/API 호출도 IP 단위로 제한합니다.
    if request.path.startswith('/api/'):
        limit = config.API_REQUESTS_PER_MINUTE if request.method == 'GET' else config.POSTS_PER_MINUTE
    else:
        limit = config.REQUESTS_PER_MINUTE if request.method == 'GET' else config.POSTS_PER_MINUTE
    if not _rate_limit_allowed(f"ip:{ip}:all", limit):
        if g.user is not None:
            _record_security_event(db, 'rate_limit', f'{request.method} {request.path}', g.user, ip)
        return jsonify({"success": False, "message": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."}), 429
    # CSRF는 모든 상태 변경 요청에서 검증합니다.
    if request.method in ('POST','PUT','PATCH','DELETE'):
        supplied = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
        if not supplied or not secrets.compare_digest(str(supplied), str(_csrf_token())):
            if g.user is not None:
                locked = _record_security_event(db, 'invalid_csrf', f'{request.method} {request.path}', g.user, _client_ip())
                if locked:
                    session.clear()
                    g.user = None
            return jsonify({"success": False, "message": "보안 토큰이 유효하지 않습니다. 페이지를 새로고침한 후 다시 시도해주세요."}), 403
        # 관리자가 계정을 삭제한 경우 다른 기기에 남아 있던 서명 세션도 다음 요청에서 즉시 무효화합니다.
        if g.user is None:
            session.clear()
            session["session_id"] = os.urandom(24).hex()
            g.session_id = session["session_id"]

@app.after_request
def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.supabase.co; connect-src 'self' https://*.supabase.co; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'")
    if response.status_code in (401,403,429) and getattr(g, 'user', None) is not None:
        db = database.get_db()
        event_type = 'rate_limit' if response.status_code == 429 else 'unauthorized_admin' if request.path.startswith('/api/admin') else 'blocked_method'
        locked = _record_security_event(db, event_type, f'{response.status_code} {request.path}', g.user, _client_ip())
        if locked:
            session.clear()
            g.user = None
    return response

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
    secret = app.config["SECRET_KEY"]
    data = f"{secret}-{grade}-{classroom}"
    return hashlib.sha256(data.encode()).hexdigest()[:6].upper()


def _is_admin(user):
    return bool(user and user["userid"] == config.ADMIN_ID)


def _is_teacher(user):
    return bool(user and "is_teacher" in user.keys() and int(user["is_teacher"] or 0) == 1)


def _is_staff(user):
    return _is_admin(user) or _is_teacher(user)


def _audit_admin_action(db, action, target_type="", target_id=None, details=""):
    """관리자 계정이 수행한 주요 변경 작업만 감사 로그에 남깁니다."""
    if not _is_admin(g.user):
        return
    db.execute(
        "INSERT INTO audit_logs (actor_id, actor_userid, action, target_type, target_id, details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            g.user["id"],
            g.user["userid"],
            str(action),
            str(target_type or ""),
            None if target_id is None else str(target_id),
            str(details or ""),
            datetime.now().isoformat(),
        ),
    )


def _generate_temporary_password(length=12):
    """대문자/소문자/숫자/특수문자를 모두 포함하는 일회성 전달용 비밀번호를 생성합니다."""
    length = max(10, int(length))
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    chars = required + [secrets.choice(alphabet) for _ in range(length - len(required))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _notice_unread_count(db, user_id, grade):
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM posts p "
        "WHERE p.grade = ? AND p.classroom = -1 AND p.author_id != ? "
        "AND NOT EXISTS (SELECT 1 FROM post_reads r WHERE r.user_id = ? AND r.post_id = p.id)",
        (int(grade), int(user_id), int(user_id)),
    ).fetchone()
    return int(row["cnt"] if row else 0)


def _attach_notice_unread_counts(db, user_id, classes):
    for item in classes:
        if str(item.get("classroom")) == "notice" and str(item.get("grade", "")).isdigit():
            item["unread_count"] = _notice_unread_count(db, user_id, int(item["grade"]))
        else:
            item["unread_count"] = 0
    return classes


def _decrypt_student_no(token):
    if not token:
        return ""
    try:
        return crypto_utils.aesgcm_decrypt(token).decode()
    except Exception:
        return ""


def _post_board_route(grade, classroom):
    grade = int(grade)
    classroom = int(classroom)
    if grade == 0 and classroom == 0:
        return "admin", "general", "관리자 전용"
    if classroom == -1:
        return str(grade), "notice", f"{grade}학년 공지"
    if classroom == 0:
        return str(grade), "combined", f"{grade}학년 통합반"
    return str(grade), str(classroom), f"{grade}학년 {classroom}반"


def _find_users_by_student_no(db, student_no):
    matches = []
    rows = db.execute(
        "SELECT id, userid, name, grade, classroom, student_no, is_teacher FROM users ORDER BY id"
    ).fetchall()
    for row in rows:
        if _decrypt_student_no(row["student_no"]) == student_no:
            matches.append(row)
    return matches


def _has_class_membership(db, user_id, grade, classroom):
    if not user_id:
        return False
    return db.execute(
        "SELECT 1 FROM classes WHERE user_id = ? AND grade = ? AND classroom = ? LIMIT 1",
        (user_id, str(grade), str(classroom)),
    ).fetchone() is not None


def _is_own_student_class(user, grade, classroom):
    """일반 학생은 학번에서 저장된 학년/반을 기본 소속 학급으로 인정합니다."""
    if user is None or _is_admin(user) or _is_teacher(user):
        return False
    try:
        return (
            int(user["grade"] or 0) == int(grade)
            and int(user["classroom"] or 0) == int(classroom)
            and _is_valid_school_class(grade, classroom)
        )
    except (TypeError, ValueError):
        return False


def _has_regular_class_access(db, user, grade, classroom):
    if user is None:
        return False
    if _is_admin(user) or _is_own_student_class(user, grade, classroom):
        return True
    return (
        f"{grade}-{classroom}" in session.get("unlocked_classes", [])
        or _has_class_membership(db, user["id"], grade, classroom)
    )


def _can_access_stored_board(db, user, grade, classroom):
    if user is None:
        return False
    if _is_admin(user):
        return True
    grade = int(grade)
    classroom = int(classroom)
    if grade == 0 and classroom == 0:
        return False
    if classroom == -1:
        return _is_teacher(user) or str(user["grade"] or "") == str(grade)
    if classroom == 0:
        return str(user["grade"] or "") == str(grade)
    return _has_regular_class_access(db, user, grade, classroom)


def _get_post_images(db, post_id):
    return db.execute(
        "SELECT id, post_id, storage_path, public_url, sort_order, created_at "
        "FROM post_images WHERE post_id = ? ORDER BY sort_order, id",
        (int(post_id),),
    ).fetchall()


def _request_image_files():
    return [f for f in request.files.getlist("images") if f and getattr(f, "filename", "")]


def _cleanup_storage_paths(paths):
    """DB 작업 이후 Storage 객체를 best-effort로 정리합니다."""
    if not paths:
        return
    try:
        post_images.delete(list(paths))
    except Exception as exc:
        # DB에는 더 이상 연결되지 않은 객체이므로 사용자 요청을 실패시키지 않고 서버 로그로 남깁니다.
        print(f"Supabase Storage 정리 오류: {exc}")


def _normalize_subject_name(subject):
    return re.sub(r"\s+", " ", str(subject or "").strip())


def _subjects_equivalent_for_change_detection(base_subject, actual_subject):
    """변경 알림에서만 서로 같은 수업으로 취급할 표기 차이를 판정합니다."""
    base = _normalize_subject_name(base_subject)
    actual = _normalize_subject_name(actual_subject)
    if base == actual:
        return True
    return (base, actual) in TIMETABLE_SUBJECT_EQUIVALENTS


def _load_grade2_elective_room_map(db):
    """2학년 기준표의 선택교시 과목 -> 진행 반 목록을 한 번에 만듭니다."""
    rows = db.execute(
        "SELECT classroom, day_of_week, period, subject FROM class_base_timetable "
        "WHERE grade = 2 AND subject != '' ORDER BY classroom"
    ).fetchall()
    room_map = {}
    for row in rows:
        key = (int(row["day_of_week"]), int(row["period"]))
        if key not in GRADE2_ELECTIVE_SLOTS:
            continue
        subject = _normalize_subject_name(row["subject"])
        if not subject:
            continue
        room_map.setdefault((key[0], key[1], subject), []).append(int(row["classroom"]))
    return room_map


# --- 개인 시간표 설정 ---
WEEKDAY_NAMES = ["월", "화", "수", "목", "금"]
GRADE_DAILY_PERIODS = {
    1: [7, 7, 6, 7, 7],
    2: [7, 7, 6, 7, 5],
}
GRADE_MAX_CLASSROOM = {1: 10, 2: 9, 3: 10}
GRADE2_ELECTIVE_SLOTS = {
    (0, 1), (0, 2), (0, 5), (0, 6),
    (1, 2), (1, 5),
    (2, 2), (2, 3), (2, 5),
    (3, 1), (3, 2), (3, 3),
    (4, 1), (4, 2), (4, 4),
}
# 기준 시간표의 생활/창의적 체험활동 표기와 NEIS 표기를 같은 수업으로 취급합니다.
# 교시 자체를 예외 처리하지 않으므로, 아래 조합 이외의 실제 변경은 정상적으로 알립니다.
TIMETABLE_SUBJECT_EQUIVALENTS = {
    ("동아리", "자율·자치활동"),
    ("동아리", "동아리활동"),
    ("동아리", "동아리 활동"),
    ("창체", "자율·자치활동"),
}
ELECTIVE_SUBJECT_GROUPS = {
    "humanities": [
        "윤리와 사상", "법과 사회", "한국지리 탐구", "경제", "일본어 회화",
        "사회 문제 탐구", "동아시아 역사 기행",
    ],
    "science": [
        "역학과 에너지", "물질과 에너지", "세포와 물질대사", "지구시스템과학",
        "융합과학 탐구", "인공지능 기초", "지식 재산 일반", "인공지능 수학",
    ],
}
ALLOWED_ELECTIVE_SUBJECTS = {
    subject for subjects in ELECTIVE_SUBJECT_GROUPS.values() for subject in subjects
}

def _is_valid_school_class(grade, classroom):
    try:
        grade = int(grade)
        classroom = int(classroom)
    except (TypeError, ValueError):
        return False
    return grade in GRADE_MAX_CLASSROOM and 1 <= classroom <= GRADE_MAX_CLASSROOM[grade]


def _is_supported_timetable_class(grade, classroom):
    return (
        grade in GRADE_DAILY_PERIODS
        and _is_valid_school_class(grade, classroom)
    )

def _active_period(grade, day, period):
    periods = GRADE_DAILY_PERIODS.get(grade)
    return bool(periods and 0 <= day <= 4 and 1 <= period <= periods[day])

def _load_base_timetable(db, grade, classroom):
    rows = db.execute(
        "SELECT day_of_week, period, subject FROM class_base_timetable "
        "WHERE grade = ? AND classroom = ? ORDER BY day_of_week, period",
        (grade, classroom),
    ).fetchall()
    return {(row["day_of_week"], row["period"]): row["subject"] for row in rows}

def _load_user_electives(db, user_id):
    rows = db.execute(
        "SELECT day_of_week, period, subject FROM custom_timetable "
        "WHERE user_id = ? ORDER BY day_of_week, period",
        (user_id,),
    ).fetchall()
    return {(row["day_of_week"], row["period"]): row["subject"] for row in rows}

def _get_timetable_profile(db, user_id):
    return db.execute(
        "SELECT grade, classroom, updated_at FROM timetable_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()

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

        # 학번 유효성 검사: 반드시 5자리 숫자 + 실제 학년/반 범위
        if student_no:
            if not (student_no.isdigit() and len(student_no) == 5):
                return render_template("register.html", error="학번은 정확히 5자리 숫자여야 합니다.")
            # 파싱: 첫자리=학년, 2-3자리=반, 4-5자리=번호
            grade_num = int(student_no[0])
            classroom_num = int(student_no[1:3])
            if not _is_valid_school_class(grade_num, classroom_num):
                return render_template("register.html", error="존재하지 않는 학년 또는 반입니다.")
            grade = str(grade_num)
            classroom = str(classroom_num)
        else:
            grade = None
            classroom = None

        db = database.get_db()

        # AES-GCM은 같은 학번도 매번 다른 암호문이 생성되므로, 기존 학번을 복호화해 중복을 검사한다.
        if student_no and _find_users_by_student_no(db, student_no):
            return render_template("register.html", error="이미 가입된 학번입니다.")

        # 학생번호 암호화 (있을 경우)
        if student_no:
            enc_sn = crypto_utils.aesgcm_encrypt(student_no.encode())
        else:
            enc_sn = None

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
        userid = request.form.get("userid", "").strip()[:80]
        password = request.form.get("password", "")
        db = database.get_db()
        ip = _client_ip()
        if not _rate_limit_allowed(f"login:{ip}", config.LOGIN_FAIL_LIMIT * 3):
            return render_template("login.html", error="로그인 요청이 너무 많습니다. 잠시 후 다시 시도해주세요."), 429
        locked = _login_lock_status(db, ip, userid)
        if locked:
            remaining = max(1, int((locked - datetime.now()).total_seconds() // 60))
            return render_template("login.html", error=f"로그인 시도가 제한되었습니다. 약 {remaining + 1}분 후 다시 시도해주세요."), 429
        user = db.execute("SELECT * FROM users WHERE userid = ?", (userid,)).fetchone()
        if user and not _blacklist_match(db, user, ip) and check_password_hash(user["password"], password):
            _clear_login_failures(db, ip, userid)
            session.permanent = False if user["userid"] == config.ADMIN_ID else True
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
        count, locked_until = _record_login_failure(db, ip, userid)
        if count >= config.LOGIN_FAIL_LIMIT:
            return render_template("login.html", error="로그인 시도가 제한되었습니다. 잠시 후 다시 시도해주세요."), 429
        return render_template("login.html", error="아이디 또는 비밀번호가 올바르지 않습니다.")
    return render_template("login.html")

# --- main route: 로그인한 학생이면 자동으로 오늘 학급 시간표/급식 미리 로드 ---
@app.route("/main")
def main():
    # 학교 기준 시각(Asia/Seoul). 20시 이후 메인 급식/시간표는 다음 날짜를 미리 보여줍니다.
    now = datetime.now(SCHOOL_TZ)
    date_str = now.strftime("%Y%m%d")
    display_date = now + timedelta(days=1) if now.hour >= 20 else now
    display_date_str = display_date.strftime("%Y%m%d")
    showing_tomorrow = now.hour >= 20
    # 페이지를 계속 열어 둬도 다음 20:00(KST)에 자동으로 표시 날짜를 갱신합니다.
    next_rollover = now.replace(hour=20, minute=0, second=0, microsecond=0)
    if now >= next_rollover:
        next_rollover += timedelta(days=1)
    next_rollover_ms = int(next_rollover.timestamp() * 1000)

    grade = request.args.get("grade")
    classroom = request.args.get("classroom")

    # URL 인자로 특정 학급이 명시된 경우, 권한 검사를 수행
    if grade and classroom:
        try:
            grade_num, class_num = int(grade), int(classroom)
            if not _is_valid_school_class(grade_num, class_num):
                flash("존재하지 않는 학급입니다.")
                return redirect(url_for("main")) # 인자 없이 메인으로
        except ValueError:
            flash("유효하지 않은 학급 정보입니다.")
            return redirect(url_for("main"))

        # 일반 학생의 자기 반, 초대코드로 해제한 반, DB에 가입된 반을 모두 허용합니다.
        db = database.get_db()
        if not _has_regular_class_access(db, g.user, grade_num, class_num):
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
        display_date=display_date_str,
        showing_tomorrow=showing_tomorrow,
        next_rollover_ms=next_rollover_ms,
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
    db = database.get_db()
    posts = []
    class_identifier = f"{grade}-{classroom}"
    is_admin = _is_admin(g.user)
    is_teacher = _is_teacher(g.user)
    is_staff = is_admin or is_teacher
    can_write = False

    # 1. 관리자 전용 게시판
    if grade == "admin" and classroom == "general":
        if not is_admin:
            flash("관리자만 접근할 수 있습니다.")
            return redirect(url_for("main"))
        can_write = True
        post_grade, post_classroom = 0, 0

    # 2. 학년별 공지 게시판: 학생은 자기 학년 조회만, 교사/관리자는 전 학년 조회·작성
    elif classroom == "notice":
        try:
            grade_num = int(grade)
            if not (1 <= grade_num <= 3):
                raise ValueError
        except ValueError:
            flash("존재하지 않는 학년입니다.")
            return redirect(url_for("main"))
        if g.user is None:
            flash("로그인이 필요합니다.")
            return redirect(url_for("login"))
        if not is_staff and str(g.user["grade"] or "") != str(grade):
            flash(f"{grade}학년 공지는 해당 학년 학생만 조회할 수 있습니다.")
            return redirect(url_for("main"))
        can_write = is_staff
        post_grade, post_classroom = grade_num, -1

    # 3. 학년 통합 게시판
    elif classroom == "combined":
        try:
            grade_num = int(grade)
            if not (1 <= grade_num <= 3):
                raise ValueError
        except ValueError:
            flash("존재하지 않는 학년입니다.")
            return redirect(url_for("main"))
        if not (is_admin or (g.user and str(g.user["grade"] or "") == str(grade))):
            flash(f"{grade}학년 학생만 접근할 수 있습니다.")
            return redirect(url_for("main"))
        can_write = bool(g.user)
        post_grade, post_classroom = grade_num, 0

    # 4. 일반 학급 게시판
    else:
        try:
            grade_num, class_num = int(grade), int(classroom)
            if not _is_valid_school_class(grade_num, class_num):
                raise ValueError
        except ValueError:
            flash("유효하지 않은 학급 정보입니다.")
            return redirect(url_for("main"))

        if not _has_regular_class_access(db, g.user, grade_num, class_num):
            return redirect(url_for("unlock_class", grade=grade, classroom=classroom))
        can_write = bool(g.user)
        post_grade, post_classroom = grade_num, class_num

    search_query = request.args.get("q", "").strip()[:100]
    user_id_for_read = int(g.user["id"]) if g.user is not None else -1
    sql = (
        "SELECT p.id, p.title, p.created_at, p.is_pinned, p.author_id, u.name AS author_name, "
        "COALESCE(u.is_teacher, 0) AS author_is_teacher, "
        "CASE WHEN p.author_id = ? OR r.post_id IS NOT NULL THEN 1 ELSE 0 END AS is_read "
        "FROM posts p JOIN users u ON p.author_id = u.id "
        "LEFT JOIN post_reads r ON r.post_id = p.id AND r.user_id = ? "
        "WHERE p.grade = ? AND p.classroom = ? "
    )
    params = [user_id_for_read, user_id_for_read, post_grade, post_classroom]
    if search_query:
        pattern = f"%{search_query}%"
        sql += "AND (p.title LIKE ? OR p.content LIKE ? OR u.name LIKE ?) "
        params.extend([pattern, pattern, pattern])
    sql += "ORDER BY p.is_pinned DESC, p.created_at DESC"
    posts = db.execute(sql, params).fetchall()

    if is_admin and classroom not in {"combined", "notice"} and grade != "admin":
        correct_code = generate_invite_code(grade, classroom)
        flash(f"{grade}학년 {classroom}반의 초대 코드는 '{correct_code}'입니다. 학생들에게 이 코드를 알려주세요.", "info")

    return render_template(
        "class_detail.html",
        grade=grade,
        classroom=classroom,
        posts=posts,
        can_write=can_write,
        can_pin=is_staff,
        is_teacher=is_teacher,
        is_notice=(classroom == "notice"),
        search_query=search_query,
        cache_buster=int(time.time()),
    )

# 📌 글쓰기 페이지
@app.route("/class/<grade>/<classroom>/write", methods=["GET", "POST"])
def write_post(grade, classroom):
    if g.user is None:
        flash("글을 작성하려면 로그인이 필요합니다.")
        return redirect(url_for("login"))

    is_admin = _is_admin(g.user)
    is_staff = _is_staff(g.user)
    post_grade = post_classroom = None

    if grade == "admin" and classroom == "general":
        if not is_admin:
            flash("관리자만 글을 작성할 수 있습니다.")
            return redirect(url_for("main"))
        post_grade, post_classroom = 0, 0
    elif classroom == "notice":
        try:
            grade_num = int(grade)
            if not (1 <= grade_num <= 3):
                raise ValueError
        except ValueError:
            flash("존재하지 않는 학년입니다.")
            return redirect(url_for("main"))
        if not is_staff:
            flash("학년별 공지는 선생님 계정만 작성할 수 있습니다.")
            return redirect(url_for("class_detail", grade=grade, classroom=classroom))
        post_grade, post_classroom = grade_num, -1
    elif classroom == "combined":
        try:
            grade_num = int(grade)
        except ValueError:
            return redirect(url_for("main"))
        if not (is_admin or str(g.user["grade"] or "") == str(grade)):
            flash(f"{grade}학년 학생만 글을 작성할 수 있습니다.")
            return redirect(url_for("main"))
        post_grade, post_classroom = grade_num, 0
    else:
        try:
            post_grade, post_classroom = int(grade), int(classroom)
            if not _is_valid_school_class(post_grade, post_classroom):
                raise ValueError
        except ValueError:
            return redirect(url_for("main"))
        db = database.get_db()
        if not _has_regular_class_access(db, g.user, post_grade, post_classroom):
            flash("글을 작성할 권한이 없는 학급입니다.")
            return redirect(url_for("class_detail", grade=grade, classroom=classroom))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        image_files = _request_image_files()
        if not title or not content:
            flash("제목과 내용을 모두 입력해주세요.", "error")
            return render_template("write.html", grade=grade, classroom=classroom, edit_mode=False, post=None, existing_images=[], cache_buster=int(time.time()))
        if len(title) > 200 or len(content) > 20000:
            flash("제목은 200자, 내용은 20000자 이하로 작성해주세요.", "error")
            return render_template("write.html", grade=grade, classroom=classroom, edit_mode=False, post=None, existing_images=[], cache_buster=int(time.time()))
        if len(image_files) > config.POST_IMAGE_MAX_COUNT:
            flash(f"사진은 게시글당 최대 {config.POST_IMAGE_MAX_COUNT}장까지 첨부할 수 있습니다.", "error")
            return render_template("write.html", grade=grade, classroom=classroom, edit_mode=False, post=None, existing_images=[], cache_buster=int(time.time()))

        now = datetime.now().isoformat()
        db = database.get_db()
        uploaded_paths = []
        try:
            cur = db.execute(
                "INSERT INTO posts (grade, classroom, title, content, author_id, is_pinned, updated_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (post_grade, post_classroom, title, content, g.user["id"], now, now),
            )
            post_id = int(cur.lastrowid)
            for sort_order, image_file in enumerate(image_files):
                storage_path, image_url = post_images.upload(post_id, image_file)
                uploaded_paths.append(storage_path)
                db.execute(
                    "INSERT INTO post_images (post_id, storage_path, public_url, sort_order, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (post_id, storage_path, image_url, sort_order, now),
                )
            # 학년 공지는 작성자 본인에게는 처음부터 읽은 글로 처리합니다.
            if post_classroom == -1:
                db.execute(
                    "INSERT INTO post_reads (user_id, post_id, read_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, post_id) DO UPDATE SET read_at = excluded.read_at",
                    (g.user["id"], post_id, now),
                )
            db.commit()
        except post_images.PostImageError as exc:
            db.rollback()
            _cleanup_storage_paths(uploaded_paths)
            flash(str(exc), "error")
            return render_template("write.html", grade=grade, classroom=classroom, edit_mode=False, post=None, existing_images=[], cache_buster=int(time.time()))
        except Exception as exc:
            db.rollback()
            _cleanup_storage_paths(uploaded_paths)
            print(f"게시글 저장 오류: {exc}")
            flash("게시글 저장 중 오류가 발생했습니다.", "error")
            return render_template("write.html", grade=grade, classroom=classroom, edit_mode=False, post=None, existing_images=[], cache_buster=int(time.time()))
        return redirect(url_for("class_detail", grade=grade, classroom=classroom))

    return render_template(
        "write.html",
        grade=grade,
        classroom=classroom,
        edit_mode=False,
        post=None,
        existing_images=[],
        cache_buster=int(time.time()),
    )


@app.route("/class/<grade>/<classroom>/post/<int:post_id>/edit", methods=["GET", "POST"])
def edit_post(grade, classroom, post_id):
    if g.user is None:
        flash("로그인이 필요합니다.")
        return redirect(url_for("login"))

    db = database.get_db()
    post = db.execute(
        "SELECT id, title, content, grade, classroom, author_id FROM posts WHERE id = ?",
        (post_id,),
    ).fetchone()
    if post is None:
        return "게시물을 찾을 수 없습니다.", 404

    route_grade, route_classroom, _ = _post_board_route(post["grade"], post["classroom"])
    if str(grade) != route_grade or str(classroom) != route_classroom:
        return "게시물을 찾을 수 없습니다.", 404
    if not _can_access_stored_board(db, g.user, post["grade"], post["classroom"]):
        flash("이 게시물을 수정할 권한이 없습니다.")
        return redirect(url_for("main"))

    is_author = int(post["author_id"]) == int(g.user["id"])
    can_edit = _is_admin(g.user) or is_author or (int(post["classroom"]) == -1 and _is_teacher(g.user))
    if not can_edit:
        flash("본인이 작성한 글만 수정할 수 있습니다.")
        return redirect(url_for("post_detail", grade=grade, classroom=classroom, post_id=post_id))

    existing_images = _get_post_images(db, post_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        requested_remove_ids = {
            int(value) for value in request.form.getlist("remove_images") if str(value).isdigit()
        }
        removable = [row for row in existing_images if int(row["id"]) in requested_remove_ids]
        keep_count = len(existing_images) - len(removable)
        new_files = _request_image_files()

        if not title or not content:
            flash("제목과 내용을 모두 입력해주세요.", "error")
        elif len(title) > 200 or len(content) > 20000:
            flash("제목은 200자, 내용은 20000자 이하로 작성해주세요.", "error")
        elif keep_count + len(new_files) > config.POST_IMAGE_MAX_COUNT:
            flash(f"사진은 게시글당 최대 {config.POST_IMAGE_MAX_COUNT}장까지 첨부할 수 있습니다.", "error")
        else:
            uploaded_paths = []
            remove_paths = [row["storage_path"] for row in removable]
            try:
                now = datetime.now().isoformat()
                db.execute(
                    "UPDATE posts SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                    (title, content, now, post_id),
                )
                if removable:
                    placeholders = ",".join("?" for _ in removable)
                    db.execute(
                        f"DELETE FROM post_images WHERE post_id = ? AND id IN ({placeholders})",
                        [post_id] + [int(row["id"]) for row in removable],
                    )
                next_sort = keep_count
                for image_file in new_files:
                    storage_path, image_url = post_images.upload(post_id, image_file)
                    uploaded_paths.append(storage_path)
                    db.execute(
                        "INSERT INTO post_images (post_id, storage_path, public_url, sort_order, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (post_id, storage_path, image_url, next_sort, now),
                    )
                    next_sort += 1
                # 남아 있는 이미지의 순서를 다시 0부터 정리합니다.
                current_rows = db.execute(
                    "SELECT id FROM post_images WHERE post_id = ? ORDER BY sort_order, id", (post_id,)
                ).fetchall()
                for idx, row in enumerate(current_rows):
                    db.execute("UPDATE post_images SET sort_order = ? WHERE id = ?", (idx, row["id"]))
                if _is_admin(g.user):
                    _audit_admin_action(
                        db, "게시글 수정", "post", post_id,
                        f"{route_grade}/{route_classroom} · {title}",
                    )
                db.commit()
                _cleanup_storage_paths(remove_paths)
                return redirect(url_for("post_detail", grade=grade, classroom=classroom, post_id=post_id))
            except post_images.PostImageError as exc:
                db.rollback()
                _cleanup_storage_paths(uploaded_paths)
                flash(str(exc), "error")
            except Exception as exc:
                db.rollback()
                _cleanup_storage_paths(uploaded_paths)
                print(f"게시글 수정 오류: {exc}")
                flash("게시글 수정 중 오류가 발생했습니다.", "error")

    # 실패 후에도 현재 DB 기준 첨부 목록을 다시 읽습니다.
    existing_images = _get_post_images(db, post_id)
    return render_template(
        "write.html",
        grade=grade,
        classroom=classroom,
        edit_mode=True,
        post=post,
        existing_images=existing_images,
        cache_buster=int(time.time()),
    )

# 📌 게시물 상세 페이지
@app.route("/class/<grade>/<classroom>/post/<int:post_id>")
def post_detail(grade, classroom, post_id):
    is_admin = _is_admin(g.user)
    is_staff = _is_staff(g.user)

    if grade == "admin" and classroom == "general":
        if not is_admin:
            flash("관리자만 접근할 수 있습니다.")
            return redirect(url_for("main"))
        expected_grade, expected_classroom = 0, 0
    elif classroom == "notice":
        try:
            grade_num = int(grade)
            if not (1 <= grade_num <= 3):
                raise ValueError
        except ValueError:
            return redirect(url_for("main"))
        if g.user is None:
            return redirect(url_for("login"))
        if not is_staff and str(g.user["grade"] or "") != str(grade):
            flash(f"{grade}학년 공지는 해당 학년 학생만 조회할 수 있습니다.")
            return redirect(url_for("main"))
        expected_grade, expected_classroom = grade_num, -1
    elif classroom == "combined":
        try:
            grade_num = int(grade)
        except ValueError:
            return redirect(url_for("main"))
        if not (is_admin or (g.user and str(g.user["grade"] or "") == str(grade))):
            flash(f"{grade}학년 학생만 접근할 수 있습니다.")
            return redirect(url_for("main"))
        expected_grade, expected_classroom = grade_num, 0
    else:
        try:
            expected_grade, expected_classroom = int(grade), int(classroom)
        except ValueError:
            return redirect(url_for("main"))
        db = database.get_db()
        if not _has_regular_class_access(db, g.user, expected_grade, expected_classroom):
            return redirect(url_for("unlock_class", grade=grade, classroom=classroom))

    db = database.get_db()
    post = db.execute(
        "SELECT p.id, p.title, p.content, p.created_at, p.updated_at, p.is_pinned, p.author_id, "
        "u.name AS author_name, COALESCE(u.is_teacher, 0) AS author_is_teacher "
        "FROM posts p JOIN users u ON p.author_id = u.id "
        "WHERE p.id = ? AND p.grade = ? AND p.classroom = ?",
        (post_id, expected_grade, expected_classroom),
    ).fetchone()
    if post is None:
        return "게시물을 찾을 수 없습니다.", 404

    # 학년별 공지는 실제 상세 글을 열었을 때 읽음으로 기록합니다.
    if g.user is not None and expected_classroom == -1:
        db.execute(
            "INSERT INTO post_reads (user_id, post_id, read_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, post_id) DO UPDATE SET read_at = excluded.read_at",
            (g.user["id"], post_id, datetime.now().isoformat()),
        )
        db.commit()

    sanitized_content = bleach.clean(post["content"])
    formatted_content = sanitized_content.replace("\n", "<br>")
    attached_images = _get_post_images(db, post_id)
    can_edit = bool(
        g.user and (
            _is_admin(g.user)
            or int(post["author_id"]) == int(g.user["id"])
            or (expected_classroom == -1 and _is_teacher(g.user))
        )
    )

    return render_template(
        "post_detail.html",
        grade=grade,
        classroom=classroom,
        post=post,
        formatted_content=formatted_content,
        attached_images=attached_images,
        can_pin=is_staff,
        can_edit=can_edit,
        can_delete=bool(g.user and (_is_admin(g.user) or int(post["author_id"]) == int(g.user["id"]))),
        cache_buster=int(time.time()),
    )


@app.route("/api/posts/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    db = database.get_db()
    post = db.execute(
        "SELECT id, grade, classroom, author_id, title FROM posts WHERE id = ?",
        (post_id,),
    ).fetchone()
    if post is None:
        return jsonify({"success": False, "message": "게시물을 찾을 수 없습니다."}), 404

    # 관리자는 모든 글을 삭제할 수 있고, 그 외 계정은 본인이 작성한 글만 삭제할 수 있습니다.
    if not (_is_admin(g.user) or int(post["author_id"]) == int(g.user["id"])):
        return jsonify({"success": False, "message": "이 게시물을 삭제할 권한이 없습니다."}), 403

    route_grade, route_classroom, _ = _post_board_route(post["grade"], post["classroom"])
    image_rows = _get_post_images(db, post_id)
    image_paths = [row["storage_path"] for row in image_rows]
    if _is_admin(g.user):
        _audit_admin_action(
            db, "게시글 삭제", "post", post_id,
            f"{route_grade}/{route_classroom} · {post['title']}",
        )
    db.execute("DELETE FROM post_reads WHERE post_id = ?", (post_id,))
    db.execute("DELETE FROM post_images WHERE post_id = ?", (post_id,))
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    _cleanup_storage_paths(image_paths)

    return jsonify({
        "success": True,
        "message": "게시물이 삭제되었습니다.",
        "redirect_url": url_for("class_detail", grade=route_grade, classroom=route_classroom),
    })


@app.route("/api/posts/<int:post_id>/pin", methods=["POST"])
def toggle_post_pin(post_id):
    if g.user is None or not _is_staff(g.user):
        return jsonify({"success": False, "message": "선생님 권한이 필요합니다."}), 403
    db = database.get_db()
    post = db.execute("SELECT id, grade, classroom, title, is_pinned FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        return jsonify({"success": False, "message": "게시물을 찾을 수 없습니다."}), 404
    if not _can_access_stored_board(db, g.user, post["grade"], post["classroom"]):
        return jsonify({"success": False, "message": "이 게시판의 글을 고정할 권한이 없습니다."}), 403
    new_value = 0 if int(post["is_pinned"] or 0) else 1
    db.execute("UPDATE posts SET is_pinned = ? WHERE id = ?", (new_value, post_id))
    if _is_admin(g.user):
        route_grade, route_classroom, _ = _post_board_route(post["grade"], post["classroom"])
        _audit_admin_action(
            db, "게시글 고정" if new_value else "게시글 고정 해제", "post", post_id,
            f"{route_grade}/{route_classroom} · {post['title']}",
        )
    db.commit()
    return jsonify({"success": True, "is_pinned": bool(new_value)})

# 📌 초대 코드로 클래스 잠금 해제
@app.route("/class/unlock", methods=["GET", "POST"])
def unlock_class():
    grade = request.args.get("grade")
    classroom = request.args.get("classroom")

    if not grade or not classroom:
        flash("잘못된 접근입니다.")
        return redirect(url_for("main"))
    if not _is_valid_school_class(grade, classroom):
        flash("존재하지 않는 학급입니다.")
        return redirect(url_for("main"))

    # 일반 학생의 자기 반은 초대 코드 없이 기본 접근합니다.
    if _is_own_student_class(g.user, grade, classroom):
        return redirect(url_for("class_detail", grade=grade, classroom=classroom))

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
    data_type = request.args.get("data_type", "all").lower()

    if data_type not in {"all", "meal", "timetable"}:
        return jsonify({"error": "invalid data_type"}), 400
    if data_type in {"all", "timetable"} and not _is_valid_school_class(grade, classroom):
        return jsonify({"error": "invalid school class"}), 400

    try:
        datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        return jsonify({"error": "date must be YYYYMMDD"}), 400

    response_data = {"grade": grade, "classroom": classroom, "date": date_str}

    # data_type을 실제로 반영하여 급식 요청 때 시간표 API를, 시간표 요청 때 급식 API를 호출하지 않습니다.
    if data_type in {"all", "meal"}:
        response_data["meal"] = neis.get_meal(date_str)

    if data_type in {"all", "timetable"}:
        try:
            base_date = datetime.strptime(date_str, "%Y%m%d")

            # 기존 조회 범위를 유지합니다. 이 함수 자체는 파일 캐시되어 같은 조건의 다중 사용자 요청을 공유합니다.
            start_date_for_api = (base_date - timedelta(days=4)).strftime("%Y%m%d")
            end_date_for_api = (base_date + timedelta(days=13)).strftime("%Y%m%d")
            all_timetable_data = neis.get_timetable_range(grade, classroom, start_date_for_api, end_date_for_api)

            filtered_timetable = []
            for item in all_timetable_data:
                current_item_date = datetime.strptime(item["date"], "%Y%m%d")
                if current_item_date >= base_date and current_item_date.weekday() < 5:
                    filtered_timetable.append(item)
                if len(filtered_timetable) >= 10:
                    break

            response_data["timetable"] = filtered_timetable
        except Exception as e:
            print(f"시간표 데이터 처리 중 오류 발생 ({date_str}): {e}")
            response_data["timetable"] = []

    response = jsonify(response_data)
    # 같은 브라우저에서 짧은 시간 내 새로고침/재방문 시 서버 요청 자체도 줄입니다.
    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=60"
    return response



# --- 포털 재구성 API ---
def _parse_yyyymmdd(value):
    return datetime.strptime(value, "%Y%m%d")


def _week_bounds(selected):
    """Return the Mon-Fri school days for a Sat-Fri display week.

    The visible timetable/meal week rolls over on Saturday instead of Monday:
    Saturday/Sunday belong to the upcoming Monday-Friday, while Monday-Friday
    belong to the current school week.
    """
    days_since_saturday = (selected.weekday() - 5) % 7
    saturday = selected - timedelta(days=days_since_saturday)
    monday = saturday + timedelta(days=2)
    friday = saturday + timedelta(days=6)
    return monday, friday


@app.route("/api/week_meals", methods=["GET"])
def week_meals():
    date_str = request.args.get("date", datetime.now().strftime("%Y%m%d"))
    try:
        selected = _parse_yyyymmdd(date_str)
    except ValueError:
        return jsonify({"success": False, "message": "date must be YYYYMMDD"}), 400
    monday, friday = _week_bounds(selected)
    data = neis.get_meal_range(monday.strftime("%Y%m%d"), friday.strftime("%Y%m%d"))
    if not isinstance(data, dict):
        data = {}
    days = []
    for offset in range(5):
        day = monday + timedelta(days=offset)
        key = day.strftime("%Y%m%d")
        days.append({"date": key, "day_name": WEEKDAY_NAMES[offset], "meals": data.get(key, [])})
    response = jsonify({"success": True, "week_start": monday.strftime("%Y%m%d"), "days": days})
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@app.route("/api/weather", methods=["GET"])
def current_weather():
    data = weather.get_current_weather()
    return jsonify({"success": bool(data), "weather": data})


@app.route("/api/school_schedule", methods=["GET"])
def school_schedule():
    date_str = request.args.get("date", datetime.now().strftime("%Y%m%d"))
    try:
        selected = _parse_yyyymmdd(date_str)
    except ValueError:
        return jsonify({"success": False, "message": "date must be YYYYMMDD"}), 400
    # 캐시 키가 매일 달라지지 않도록 토~금 주차에 대응하는 월요일 기준 고정 범위를 조회합니다.
    # 화면에는 선택일 기준 향후 45일만 필터링해서 보여줍니다.
    week_start, _ = _week_bounds(selected)
    cache_end = week_start + timedelta(days=55)
    cached_events = neis.get_school_schedule(week_start.strftime("%Y%m%d"), cache_end.strftime("%Y%m%d"))
    visible_end = selected + timedelta(days=44)
    events = [
        event for event in cached_events
        if selected.strftime("%Y%m%d") <= event.get("date", "") <= visible_end.strftime("%Y%m%d")
    ]
    response = jsonify({
        "success": True,
        "from": selected.strftime("%Y%m%d"),
        "to": visible_end.strftime("%Y%m%d"),
        "events": events,
    })
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@app.route("/api/user_profile", methods=["GET", "POST"])
def user_profile():
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    if request.method == "GET":
        student_no = session.get("student_no", "")
        return jsonify({
            "success": True,
            "user": {
                "userid": g.user["userid"],
                "name": g.user["name"],
                "student_no": student_no,
                "grade": g.user["grade"],
                "classroom": g.user["classroom"],
                "is_admin": _is_admin(g.user),
                "is_teacher": _is_teacher(g.user),
            },
        })

    if _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 계정 정보는 이 화면에서 수정하지 않습니다."}), 403

    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 30:
        return jsonify({"success": False, "message": "이름은 1~30자로 입력해주세요."}), 400

    # 일반 사용자는 학번/학년/반을 직접 바꿀 수 없다.
    db = database.get_db()
    db.execute("UPDATE users SET name = ? WHERE id = ?", (name, g.user["id"]))
    db.commit()
    session["display_name"] = name
    return jsonify({
        "success": True,
        "message": "이름을 변경했습니다.",
        "user": {"name": name, "student_no": session.get("student_no", "")},
    })


@app.route("/api/change_password", methods=["POST"])
def change_password():
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401
    if _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 비밀번호는 서버 환경변수 ADMIN_PASSWORD에서 변경해주세요."}), 403

    payload = request.get_json(silent=True) or {}
    current_password = str(payload.get("current_password", ""))
    new_password = str(payload.get("new_password", ""))
    new_password2 = str(payload.get("new_password2", ""))
    if not current_password or not new_password or not new_password2:
        return jsonify({"success": False, "message": "현재 비밀번호와 새 비밀번호를 모두 입력해주세요."}), 400
    if not check_password_hash(g.user["password"], current_password):
        return jsonify({"success": False, "message": "현재 비밀번호가 올바르지 않습니다."}), 400
    if new_password != new_password2:
        return jsonify({"success": False, "message": "새 비밀번호가 일치하지 않습니다."}), 400
    if len(new_password) < 8 or pw_class_count(new_password) < 3:
        return jsonify({"success": False, "message": "새 비밀번호는 8자 이상이며 소문자·대문자·숫자·특수문자 중 3가지 이상을 포함해야 합니다."}), 400
    if check_password_hash(g.user["password"], new_password):
        return jsonify({"success": False, "message": "현재 비밀번호와 다른 비밀번호를 사용해주세요."}), 400

    db = database.get_db()
    db.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(new_password), g.user["id"]))
    db.commit()
    return jsonify({"success": True, "message": "비밀번호를 변경했습니다."})


@app.route("/api/site_info", methods=["GET", "POST"])
def site_info():
    db = database.get_db()
    if request.method == "GET":
        rows = db.execute("SELECT info_key, content, updated_at FROM site_info").fetchall()
        info = {row["info_key"]: row["content"] for row in rows}
        return jsonify({"success": True, "purpose": info.get("purpose", ""), "team": info.get("team", "")})

    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403
    payload = request.get_json(silent=True) or {}
    purpose = str(payload.get("purpose", "")).strip()
    team = str(payload.get("team", "")).strip()
    if len(purpose) > 5000 or len(team) > 5000:
        return jsonify({"success": False, "message": "사이트 정보는 항목별 5000자 이하로 작성해주세요."}), 400
    now = datetime.now().isoformat()
    for key, value in (("purpose", purpose), ("team", team)):
        db.execute(
            "INSERT INTO site_info (info_key, content, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(info_key) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at",
            (key, value, now),
        )
    _audit_admin_action(db, "사이트 정보 수정", "site_info", "portal", "만든 취지/제작팀 정보 수정")
    db.commit()
    return jsonify({"success": True, "message": "사이트 정보를 저장했습니다."})


@app.route("/api/announcements", methods=["GET", "POST"])
def announcements():
    db = database.get_db()
    if request.method == "GET":
        rows = db.execute(
            "SELECT id, title, content, created_at, updated_at FROM announcements ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
        return jsonify({"success": True, "announcements": [dict(row) for row in rows]})

    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", "")).strip()
    if not title or len(title) > 100 or len(content) > 5000:
        return jsonify({"success": False, "message": "제목은 1~100자, 내용은 5000자 이하로 작성해주세요."}), 400
    now = datetime.now().isoformat()
    cur = db.execute(
        "INSERT INTO announcements (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (title, content, now, now),
    )
    _audit_admin_action(db, "학교 소식 공지 등록", "announcement", cur.lastrowid, title)
    db.commit()
    return jsonify({"success": True, "message": "공지를 등록했습니다.", "id": cur.lastrowid})


@app.route("/api/announcements/<int:announcement_id>", methods=["DELETE"])
def delete_announcement(announcement_id):
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403
    db = database.get_db()
    item = db.execute("SELECT id, title FROM announcements WHERE id = ?", (announcement_id,)).fetchone()
    if item is None:
        return jsonify({"success": False, "message": "공지를 찾을 수 없습니다."}), 404
    db.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))
    _audit_admin_action(db, "학교 소식 공지 삭제", "announcement", announcement_id, item["title"])
    db.commit()
    return jsonify({"success": True})


# 📌 시간표용 반 등록 API
@app.route("/api/timetable_profile", methods=["GET", "POST"])
def timetable_profile():
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    db = database.get_db()
    if request.method == "GET":
        profile = _get_timetable_profile(db, g.user["id"])
        suggested = None
        try:
            suggested_grade = int(g.user["grade"]) if g.user["grade"] is not None else None
            suggested_classroom = int(g.user["classroom"]) if g.user["classroom"] is not None else None
            if suggested_grade is not None and suggested_classroom is not None and _is_supported_timetable_class(suggested_grade, suggested_classroom):
                suggested = {"grade": suggested_grade, "classroom": suggested_classroom}
        except (TypeError, ValueError):
            pass

        return jsonify({
            "success": True,
            "profile": ({"grade": profile["grade"], "classroom": profile["classroom"]} if profile else None),
            "suggested": suggested,
            "elective_subjects": ELECTIVE_SUBJECT_GROUPS,
            "elective_slots": [
                {"day": day, "period": period} for day, period in sorted(GRADE2_ELECTIVE_SLOTS)
            ],
        })

    payload = request.get_json(silent=True) or {}
    try:
        grade = int(payload.get("grade"))
        classroom = int(payload.get("classroom"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "학년/반 값이 올바르지 않습니다."}), 400

    if not _is_supported_timetable_class(grade, classroom):
        return jsonify({"success": False, "message": "현재 개인 시간표는 1·2학년만 지원합니다."}), 400

    now = datetime.now().isoformat()
    db.execute(
        "INSERT INTO timetable_profiles (user_id, grade, classroom, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET grade = excluded.grade, classroom = excluded.classroom, updated_at = excluded.updated_at",
        (g.user["id"], grade, classroom, now),
    )
    # 1학년으로 변경하면 2학년용 선택과목 설정은 제거합니다.
    if grade != 2:
        db.execute("DELETE FROM custom_timetable WHERE user_id = ?", (g.user["id"],))
    db.commit()
    return jsonify({"success": True, "profile": {"grade": grade, "classroom": classroom}})


# 📌 2학년 선택과목 조회/저장 API
@app.route("/api/custom_timetable", methods=["GET", "POST"])
def custom_timetable():
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    db = database.get_db()
    profile = _get_timetable_profile(db, g.user["id"])
    if profile is None:
        return jsonify({"success": False, "message": "먼저 시간표 설정에서 반을 등록해주세요.", "needs_registration": True}), 409
    if int(profile["grade"]) != 2:
        return jsonify({
            "success": False,
            "message": "22개정 이슈로 커스텀 시간표는 올해 2학년부터 제공합니다.",
            "grade": int(profile["grade"]),
        }), 403

    if request.method == "GET":
        electives = _load_user_electives(db, g.user["id"])
        cells = [
            {"day": day, "period": period, "subject": electives.get((day, period), "")}
            for day, period in sorted(GRADE2_ELECTIVE_SLOTS)
        ]
        response = jsonify({
            "success": True,
            "cells": cells,
            "subject_groups": ELECTIVE_SUBJECT_GROUPS,
        })
        response.headers["Cache-Control"] = "private, no-store"
        return response

    payload = request.get_json(silent=True) or {}
    cells = payload.get("cells")
    if not isinstance(cells, list) or len(cells) > len(GRADE2_ELECTIVE_SLOTS):
        return jsonify({"success": False, "message": "선택과목 데이터 형식이 올바르지 않습니다."}), 400

    normalized = []
    seen = set()
    for cell in cells:
        if not isinstance(cell, dict):
            return jsonify({"success": False, "message": "선택과목 셀 형식이 올바르지 않습니다."}), 400
        try:
            day = int(cell.get("day"))
            period = int(cell.get("period"))
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "요일/교시 값이 올바르지 않습니다."}), 400
        key = (day, period)
        subject = str(cell.get("subject", "")).strip()
        if key not in GRADE2_ELECTIVE_SLOTS or key in seen:
            return jsonify({"success": False, "message": "선택과목을 설정할 수 없는 교시가 포함되어 있습니다."}), 400
        if subject and subject not in ALLOWED_ELECTIVE_SUBJECTS:
            return jsonify({"success": False, "message": f"개설되지 않은 선택과목입니다: {subject}"}), 400
        seen.add(key)
        normalized.append((day, period, subject))

    try:
        db.execute("DELETE FROM custom_timetable WHERE user_id = ?", (g.user["id"],))
        now = datetime.now().isoformat()
        db.executemany(
            "INSERT INTO custom_timetable (user_id, day_of_week, period, subject, color, updated_at) "
            "VALUES (?, ?, ?, ?, '#ffffff', ?)",
            [
                (g.user["id"], day, period, subject, now)
                for day, period, subject in normalized if subject
            ],
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"선택과목 저장 오류: {e}")
        return jsonify({"success": False, "message": "선택과목 저장 중 오류가 발생했습니다."}), 500

    return jsonify({"success": True, "message": "선택과목을 저장했습니다."})


# 📌 개인 시간표: 관리자 기준표 + NEIS 변경 감지 + 2학년 선택과목 병합
@app.route("/api/personal_timetable", methods=["GET"])
def personal_timetable():
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    date_str = request.args.get("date", datetime.now().strftime("%Y%m%d"))
    try:
        selected_date = datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        return jsonify({"success": False, "message": "date must be YYYYMMDD"}), 400

    db = database.get_db()
    profile = _get_timetable_profile(db, g.user["id"])
    if profile is None:
        return jsonify({"success": False, "message": "시간표 설정에서 먼저 반을 등록해주세요.", "needs_registration": True}), 409

    grade = int(profile["grade"])
    classroom = int(profile["classroom"])
    # 주간 판정은 토요일~금요일. 표 자체는 실제 수업일인 월~금만 표시합니다.
    monday, friday = _week_bounds(selected_date)

    # 개인 시간표는 토~금 주차를 기준으로 해당 주의 월~금 범위에 캐시 키를 고정합니다.
    neis_range_start = monday.strftime("%Y%m%d")
    neis_range_end = friday.strftime("%Y%m%d")
    neis_fetch_ok = True
    try:
        neis_days = neis.get_timetable_range(
            str(grade), str(classroom), neis_range_start, neis_range_end
        )
    except Exception as e:
        print(f"개인 시간표 NEIS 처리 오류: {e}")
        neis_days = []
        neis_fetch_ok = False

    actual = {}
    for day_data in neis_days:
        try:
            day_date = datetime.strptime(day_data["date"], "%Y%m%d")
        except (KeyError, ValueError):
            continue
        if not (monday.date() <= day_date.date() <= friday.date()):
            continue
        day_index = day_date.weekday()
        if not 0 <= day_index <= 4:
            continue
        period_map = day_data.get("period_map")
        if isinstance(period_map, dict) and period_map:
            for raw_period, subject in period_map.items():
                try:
                    period = int(raw_period)
                except (TypeError, ValueError):
                    continue
                actual[(day_index, period)] = str(subject).strip()
        else:
            # 이전 버전에서 생성된 캐시 파일과의 호환
            for period, subject in enumerate(day_data.get("timetable", []), start=1):
                actual[(day_index, period)] = str(subject).strip()

    base = _load_base_timetable(db, grade, classroom)
    electives = _load_user_electives(db, g.user["id"]) if grade == 2 else {}
    elective_room_map = _load_grade2_elective_room_map(db) if grade == 2 else {}
    alerts = []
    days = []

    for day in range(5):
        date_value = monday + timedelta(days=day)
        cells = []
        for period in range(1, 8):
            active = _active_period(grade, day, period)
            if not active:
                cells.append({"period": period, "active": False, "subject": "", "changed": False, "elective": False, "elective_room": ""})
                continue

            is_elective = grade == 2 and (day, period) in GRADE2_ELECTIVE_SLOTS
            base_subject = base.get((day, period), "")
            actual_subject = actual.get((day, period), "")
            changed = False

            change_type = ""
            elective_room_label = ""
            if is_elective:
                display_subject = electives.get((day, period), "") or "선택과목 미설정"
                if display_subject != "선택과목 미설정":
                    room_key = (day, period, _normalize_subject_name(display_subject))
                    matched_rooms = elective_room_map.get(room_key, [])
                    if matched_rooms:
                        elective_room_label = " · ".join(f"2-{room}" for room in matched_rooms)
            else:
                if (
                    base_subject
                    and neis_fetch_ok
                    and not _subjects_equivalent_for_change_detection(base_subject, actual_subject)
                ):
                    changed = True
                    if actual_subject:
                        display_subject = actual_subject
                        change_type = "changed"
                        alert_to = actual_subject
                    else:
                        # 기준 시간표에는 수업이 있지만 NEIS 현재 시간표에서 해당 교시가
                        # 사라진 경우도 변경사항으로 처리합니다. API 조회 자체가 실패한
                        # 경우(neis_fetch_ok=False)에는 전 과목 결강으로 오인하지 않습니다.
                        display_subject = "없어짐"
                        change_type = "removed"
                        alert_to = "없어짐"
                    alerts.append({
                        "day": day,
                        "day_name": WEEKDAY_NAMES[day],
                        "date": date_value.strftime("%Y%m%d"),
                        "period": period,
                        "from": base_subject,
                        "to": alert_to,
                        "type": change_type,
                    })
                else:
                    display_subject = actual_subject or base_subject or "—"

            cells.append({
                "period": period,
                "active": True,
                "subject": display_subject,
                "changed": changed,
                "change_type": change_type,
                "elective": is_elective,
                "elective_room": elective_room_label,
                "base_subject": base_subject,
                "actual_subject": actual_subject,
            })
        days.append({
            "day": day,
            "day_name": WEEKDAY_NAMES[day],
            "date": date_value.strftime("%Y%m%d"),
            "cells": cells,
        })

    required_common_slots = [
        (day, period)
        for day in range(5)
        for period in range(1, 8)
        if _active_period(grade, day, period)
        and not (grade == 2 and (day, period) in GRADE2_ELECTIVE_SLOTS)
    ]
    baseline_configured = all(bool(base.get(key, "").strip()) for key in required_common_slots)

    response = jsonify({
        "success": True,
        "profile": {"grade": grade, "classroom": classroom},
        "baseline_configured": baseline_configured,
        "alerts": alerts,
        "days": days,
        "elective_subjects": ELECTIVE_SUBJECT_GROUPS if grade == 2 else {},
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response


# 📌 관리자: 반별 기준(본래) 시간표 설정
@app.route("/api/admin/base_timetable", methods=["GET", "POST"])
def admin_base_timetable():
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403

    if request.method == "GET":
        try:
            grade = int(request.args.get("grade", ""))
            classroom = int(request.args.get("classroom", ""))
        except ValueError:
            return jsonify({"success": False, "message": "학년/반 값이 올바르지 않습니다."}), 400
    else:
        payload = request.get_json(silent=True) or {}
        try:
            grade = int(payload.get("grade"))
            classroom = int(payload.get("classroom"))
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "학년/반 값이 올바르지 않습니다."}), 400

    if not _is_supported_timetable_class(grade, classroom):
        return jsonify({"success": False, "message": "현재 기준 시간표 설정은 1·2학년만 지원합니다."}), 400

    db = database.get_db()
    if request.method == "GET":
        base = _load_base_timetable(db, grade, classroom)
        cells = [
            {"day": day, "period": period, "subject": base.get((day, period), "")}
            for day in range(5) for period in range(1, 8) if _active_period(grade, day, period)
        ]
        return jsonify({
            "success": True,
            "grade": grade,
            "classroom": classroom,
            "cells": cells,
            "daily_periods": GRADE_DAILY_PERIODS[grade],
            "elective_slots": ([{"day": d, "period": p} for d, p in sorted(GRADE2_ELECTIVE_SLOTS)] if grade == 2 else []),
        })

    cells = payload.get("cells")
    if not isinstance(cells, list) or len(cells) > 35:
        return jsonify({"success": False, "message": "기준 시간표 데이터 형식이 올바르지 않습니다."}), 400

    normalized = []
    seen = set()
    for cell in cells:
        if not isinstance(cell, dict):
            return jsonify({"success": False, "message": "시간표 셀 형식이 올바르지 않습니다."}), 400
        try:
            day = int(cell.get("day"))
            period = int(cell.get("period"))
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "요일/교시 값이 올바르지 않습니다."}), 400
        subject = str(cell.get("subject", "")).strip()
        key = (day, period)
        if key in seen or not _active_period(grade, day, period):
            return jsonify({"success": False, "message": "유효하지 않은 요일/교시가 포함되어 있습니다."}), 400
        if len(subject) > 40:
            return jsonify({"success": False, "message": "과목명은 40자 이하로 입력해주세요."}), 400
        seen.add(key)
        normalized.append((day, period, subject))

    try:
        db.execute("DELETE FROM class_base_timetable WHERE grade = ? AND classroom = ?", (grade, classroom))
        now = datetime.now().isoformat()
        db.executemany(
            "INSERT INTO class_base_timetable (grade, classroom, day_of_week, period, subject, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (grade, classroom, day, period, subject, now)
                for day, period, subject in normalized if subject
            ],
        )
        _audit_admin_action(
            db, "반별 기준 시간표 수정", "class_timetable", f"{grade}-{classroom}",
            f"{grade}학년 {classroom}반 기준 시간표 저장",
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"기준 시간표 저장 오류: {e}")
        return jsonify({"success": False, "message": "기준 시간표 저장 중 오류가 발생했습니다."}), 500

    return jsonify({"success": True, "message": f"{grade}학년 {classroom}반 기준 시간표를 저장했습니다."})


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
    for grade_num, max_class in GRADE_MAX_CLASSROOM.items():
        for class_num in range(1, max_class + 1):
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

# 📌 관리자 전용: 이름으로 계정 조회
@app.route("/api/admin/users", methods=["GET"])
def admin_user_search():
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403

    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"success": True, "users": []})

    db = database.get_db()
    rows = db.execute(
        "SELECT id, userid, name, grade, classroom, student_no, is_teacher "
        "FROM users WHERE name LIKE ? ORDER BY name, id LIMIT 20",
        (f"%{name}%",),
    ).fetchall()

    users = []
    for row in rows:
        post_rows = db.execute(
            "SELECT id, grade, classroom, title, created_at FROM posts "
            "WHERE author_id = ? ORDER BY created_at DESC LIMIT 50",
            (row["id"],),
        ).fetchall()
        posts = []
        for post in post_rows:
            route_grade, route_classroom, board_name = _post_board_route(post["grade"], post["classroom"])
            posts.append({
                "id": post["id"],
                "title": post["title"],
                "created_at": post["created_at"],
                "board_name": board_name,
                "url": url_for("post_detail", grade=route_grade, classroom=route_classroom, post_id=post["id"]),
            })
        users.append({
            "id": row["id"],
            "userid": row["userid"],
            "name": row["name"],
            "student_no": _decrypt_student_no(row["student_no"]),
            "is_teacher": bool(row["is_teacher"]),
            "is_admin": row["userid"] == config.ADMIN_ID,
            "posts": posts,
        })

    return jsonify({"success": True, "users": users})


@app.route("/api/admin/users/<int:user_id>/reset_password", methods=["POST"])
def admin_reset_password(user_id):
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403

    db = database.get_db()
    target = db.execute(
        "SELECT id, userid, name, student_no FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if target is None:
        return jsonify({"success": False, "message": "계정을 찾을 수 없습니다."}), 404
    if target["userid"] == config.ADMIN_ID:
        return jsonify({"success": False, "message": "관리자 비밀번호는 서버 환경변수에서 변경해주세요."}), 400

    temporary_password = _generate_temporary_password()
    db.execute(
        "UPDATE users SET password = ? WHERE id = ?",
        (generate_password_hash(temporary_password), user_id),
    )
    _audit_admin_action(
        db, "비밀번호 초기화", "user", user_id,
        f"{target['name']} ({target['userid']}) 계정의 비밀번호를 임시 비밀번호로 초기화",
    )
    db.commit()
    return jsonify({
        "success": True,
        "message": "임시 비밀번호를 생성했습니다. 이 화면에서 한 번만 전달해주세요.",
        "temporary_password": temporary_password,
    })


@app.route("/api/admin/users/<int:user_id>/delete", methods=["POST"])
def admin_delete_user(user_id):
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403

    db = database.get_db()
    target = db.execute(
        "SELECT id, userid, name, student_no, is_teacher FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if target is None:
        return jsonify({"success": False, "message": "계정을 찾을 수 없습니다."}), 404
    if target["userid"] == config.ADMIN_ID:
        return jsonify({"success": False, "message": "관리자 계정은 삭제할 수 없습니다."}), 400

    # 계정 삭제 시 작성자 없는 게시글이 남지 않도록 작성글과 그 부속 데이터도 함께 정리합니다.
    post_rows = db.execute(
        "SELECT id, title FROM posts WHERE author_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()
    post_ids = [int(row["id"]) for row in post_rows]
    image_paths = []
    if post_ids:
        placeholders = ",".join("?" for _ in post_ids)
        image_rows = db.execute(
            f"SELECT storage_path FROM post_images WHERE post_id IN ({placeholders})",
            post_ids,
        ).fetchall()
        image_paths = [row["storage_path"] for row in image_rows]

        # 읽음 기록은 삭제 대상 사용자의 기록뿐 아니라 삭제될 게시글을 가리키는 다른 사용자의 기록도 제거합니다.
        db.execute(f"DELETE FROM post_reads WHERE post_id IN ({placeholders})", post_ids)
        db.execute(f"DELETE FROM post_images WHERE post_id IN ({placeholders})", post_ids)
        db.execute(f"DELETE FROM posts WHERE id IN ({placeholders})", post_ids)

    db.execute("DELETE FROM post_reads WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM custom_timetable WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM timetable_profiles WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM classes WHERE user_id = ?", (user_id,))

    student_no = _decrypt_student_no(target["student_no"]) or "학번 미등록"
    _audit_admin_action(
        db, "계정 삭제", "user", user_id,
        f"{target['name']} ({target['userid']}, {student_no}) 계정 삭제 · 작성글 {len(post_ids)}개 함께 삭제",
    )
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()

    # DB 정합성을 우선 보장하고 외부 Storage 파일은 best-effort로 후처리합니다.
    _cleanup_storage_paths(image_paths)

    return jsonify({
        "success": True,
        "message": f"{target['name']} 계정과 작성글 {len(post_ids)}개를 삭제했습니다.",
        "deleted_posts": len(post_ids),
    })


@app.route("/api/admin/security/events", methods=["GET"])
def admin_security_events():
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403
    db = database.get_db()
    rows = db.execute(
        "SELECT id, userid, ip, path, method, event_type, details, created_at FROM security_events ORDER BY id DESC LIMIT 100"
    ).fetchall()
    return jsonify({"success": True, "events": [dict(r) for r in rows]})


@app.route("/api/admin/security/login_attempts", methods=["GET"])
def admin_login_attempts():
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403
    db = database.get_db()
    rows = db.execute(
        "SELECT ip, userid, failed_count, last_failed_at, locked_until FROM login_attempts ORDER BY last_failed_at DESC LIMIT 100"
    ).fetchall()
    return jsonify({"success": True, "attempts": [dict(r) for r in rows]})


def _blacklist_payload_target(db, kind, value):
    kind = str(kind or '').strip().lower()
    value = str(value or '').strip()
    if kind == 'user':
        try: uid = int(value)
        except ValueError: return None, None, None, '계정 ID가 올바르지 않습니다.', None
        row = db.execute("SELECT id, userid, name, student_no FROM users WHERE id = ?", (uid,)).fetchone()
        if row is None or row['userid'] == config.ADMIN_ID: return None, None, None, '차단할 계정을 찾을 수 없거나 관리자 계정입니다.', None
        return uid, _student_no_hash(_decrypt_student_no(row['student_no'])), None, '', row['userid']
    if kind == 'student_no':
        if not re.fullmatch(r'\d{5}', value): return None, None, None, '학번은 5자리 숫자여야 합니다.', None
        return None, _student_no_hash(value), None, '', None
    if kind == 'ip':
        if len(value) > 100 or any(c.isspace() for c in value): return None, None, None, 'IP 주소 형식이 올바르지 않습니다.', None
        return None, None, value, '', None
    return None, None, None, '차단 유형이 올바르지 않습니다.', None


@app.route("/api/admin/security/blacklist", methods=["GET", "POST"])
def admin_security_blacklist():
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403
    db = database.get_db()
    if request.method == 'GET':
        rows = db.execute(
            "SELECT b.id, b.user_id, u.userid, u.name, b.student_no_hash, b.ip, b.reason, b.created_at, b.active "
            "FROM blacklist b LEFT JOIN users u ON u.id = b.user_id WHERE b.active = 1 ORDER BY b.id DESC LIMIT 200"
        ).fetchall()
        items=[]
        for r in rows:
            label = r['userid'] or ('학번 블랙리스트' if r['student_no_hash'] else r['ip'] or '대상')
            items.append({"id":r['id'],"target":label,"name":r['name'] or '',"ip":r['ip'] or '',"reason":r['reason'],"created_at":r['created_at']})
        return jsonify({"success": True, "items": items})
    payload = request.get_json(silent=True) or {}
    uid, sn_hash, ip, err, target_userid = _blacklist_payload_target(db, payload.get('kind'), payload.get('value'))
    if err: return jsonify({"success":False,"message":err}),400
    reason = str(payload.get('reason') or '관리자에 의한 보안 차단').strip()[:200]
    exists = db.execute("SELECT id FROM blacklist WHERE active=1 AND ((user_id IS NOT NULL AND user_id=?) OR (userid IS NOT NULL AND userid=?) OR (student_no_hash IS NOT NULL AND student_no_hash=?) OR (ip IS NOT NULL AND ip=?)) LIMIT 1", (uid, target_userid, sn_hash, ip)).fetchone()
    if exists: return jsonify({"success":False,"message":"이미 활성화된 블랙리스트 항목입니다."}),409
    db.execute("INSERT INTO blacklist (user_id, userid, student_no_hash, ip, reason, created_at, active) VALUES (?, ?, ?, ?, ?, ?, 1)", (uid, target_userid, sn_hash or None, ip or None, reason, datetime.now().isoformat()))
    _audit_admin_action(db, '보안 블랙리스트 등록', 'security', None, f'{payload.get("kind")} 대상 차단: {reason}')
    db.commit()
    return jsonify({"success":True,"message":"블랙리스트에 등록했습니다."})


@app.route("/api/admin/security/blacklist/<int:item_id>", methods=["DELETE"])
def admin_security_blacklist_remove(item_id):
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403
    db=database.get_db()
    row=db.execute("SELECT id FROM blacklist WHERE id=? AND active=1",(item_id,)).fetchone()
    if row is None: return jsonify({"success":False,"message":"활성 블랙리스트를 찾을 수 없습니다."}),404
    db.execute("UPDATE blacklist SET active=0 WHERE id=?",(item_id,))
    _audit_admin_action(db,'보안 블랙리스트 해제','security',item_id,'관리자가 블랙리스트 항목을 해제')
    db.commit()
    return jsonify({"success":True,"message":"블랙리스트를 해제했습니다."})


@app.route("/api/admin/audit_logs", methods=["GET"])
def admin_audit_logs():
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403
    try:
        limit = min(100, max(1, int(request.args.get("limit", 50))))
    except ValueError:
        limit = 50
    db = database.get_db()
    rows = db.execute(
        "SELECT id, actor_userid, action, target_type, target_id, details, created_at "
        "FROM audit_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return jsonify({"success": True, "logs": [dict(row) for row in rows]})


# 📌 관리자 전용: 학번으로 선생님 계정 지정/해제
@app.route("/api/admin/teacher_role", methods=["POST"])
def admin_teacher_role():
    if g.user is None or not _is_admin(g.user):
        return jsonify({"success": False, "message": "관리자 권한이 필요합니다."}), 403

    payload = request.get_json(silent=True) or {}
    student_no = str(payload.get("student_no", "")).strip()
    make_teacher = bool(payload.get("is_teacher", True))
    if not (student_no.isdigit() and len(student_no) == 5):
        return jsonify({"success": False, "message": "학번은 정확히 5자리 숫자로 입력해주세요."}), 400

    db = database.get_db()
    matches = _find_users_by_student_no(db, student_no)
    if not matches:
        return jsonify({"success": False, "message": "해당 학번의 계정을 찾을 수 없습니다."}), 404
    if len(matches) > 1:
        return jsonify({"success": False, "message": "같은 학번을 사용하는 계정이 여러 개라 지정할 수 없습니다."}), 409

    target = matches[0]
    if target["userid"] == config.ADMIN_ID:
        return jsonify({"success": False, "message": "관리자 계정은 선생님 계정으로 변경하지 않습니다."}), 400

    db.execute("UPDATE users SET is_teacher = ? WHERE id = ?", (1 if make_teacher else 0, target["id"]))
    _audit_admin_action(
        db, "선생님 지정" if make_teacher else "선생님 지정 해제", "user", target["id"],
        f"{target['name']} ({target['userid']})",
    )
    db.commit()
    return jsonify({
        "success": True,
        "message": f"{target['name']} 계정을 {'선생님으로 지정했습니다.' if make_teacher else '일반 계정으로 변경했습니다.'}",
        "user": {"name": target["name"], "student_no": student_no, "is_teacher": make_teacher},
    })


# 📌 내가 작성한 게시글 목록 조회 API
@app.route("/api/my_posts", methods=["GET"])
def get_my_posts():
    if g.user is None:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    db = database.get_db()
    rows = db.execute(
        "SELECT id, grade, classroom, title, created_at FROM posts "
        "WHERE author_id = ? ORDER BY created_at DESC",
        (g.user["id"],),
    ).fetchall()

    posts = []
    for row in rows:
        route_grade, route_classroom, board_name = _post_board_route(row["grade"], row["classroom"])
        posts.append({
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "board_name": board_name,
            "url": url_for("post_detail", grade=route_grade, classroom=route_classroom, post_id=row["id"]),
        })

    return jsonify({"success": True, "posts": posts})

# 📌 내 클래스 목록 조회 API
@app.route("/api/my_classes", methods=["GET"])
def get_my_classes():
    if g.user is None:
        return jsonify({"success": True, "classes": []})

    my_classes = []
    is_admin = _is_admin(g.user)
    is_teacher = _is_teacher(g.user)
    db = database.get_db()

    # 관리자: 관리자 전용 + 전 학년 공지 + 모든 통합/학급 게시판
    if is_admin:
        my_classes.append({"grade": "admin", "classroom": "general", "display_name": "관리자 전용"})
        for grade_num in range(1, 4):
            my_classes.append({"grade": str(grade_num), "classroom": "notice", "display_name": f"{grade_num}학년 공지"})
        for grade_num in range(1, 4):
            my_classes.append({"grade": str(grade_num), "classroom": "combined", "display_name": f"{grade_num}학년 통합"})
        for grade_num in range(1, 4):
            max_class = GRADE_MAX_CLASSROOM[grade_num]
            for class_num in range(1, max_class + 1):
                my_classes.append({"grade": str(grade_num), "classroom": str(class_num), "display_name": f"{grade_num}학년 {class_num}반"})
        return jsonify({"success": True, "classes": _attach_notice_unread_counts(db, g.user["id"], my_classes)})

    # 선생님: 전 학년 공지는 자동 제공. 일반 학급은 기존처럼 초대코드로 가입한 것만 표시.
    if is_teacher:
        for grade_num in range(1, 4):
            my_classes.append({"grade": str(grade_num), "classroom": "notice", "display_name": f"{grade_num}학년 공지"})
    else:
        user_grade = str(g.user["grade"] or "")
        if user_grade in {"1", "2", "3"}:
            my_classes.append({"grade": user_grade, "classroom": "notice", "display_name": f"{user_grade}학년 공지"})

    # 일반 학생은 학번에서 확인된 자기 반 게시판을 초대 코드 없이 기본 제공합니다.
    if not is_teacher:
        user_grade = str(g.user["grade"] or "")
        user_classroom = str(g.user["classroom"] or "")
        if _is_valid_school_class(user_grade, user_classroom):
            my_classes.append({
                "grade": user_grade,
                "classroom": user_classroom,
                "display_name": f"{user_grade}학년 {user_classroom}반",
            })

    classes_from_db = db.execute(
        "SELECT grade, classroom FROM classes WHERE user_id = ? ORDER BY grade, classroom",
        (g.user["id"],),
    ).fetchall()
    for c in classes_from_db:
        entry = {"grade": c["grade"], "classroom": c["classroom"], "display_name": f'{c["grade"]}학년 {c["classroom"]}반'}
        if not any(x["grade"] == entry["grade"] and x["classroom"] == entry["classroom"] for x in my_classes):
            my_classes.append(entry)

    # 일반 학생은 자기 학년 통합 게시판 자동 제공. 선생님은 임의 학번으로 가입할 수 있으므로 자동 추가하지 않음.
    if not is_teacher:
        user_grade = str(g.user["grade"] or "")
        if user_grade in {"1", "2", "3"} and not any(c["grade"] == user_grade and c["classroom"] == "combined" for c in my_classes):
            my_classes.insert(1 if my_classes else 0, {"grade": user_grade, "classroom": "combined", "display_name": f"{user_grade}학년 통합"})

    return jsonify({"success": True, "classes": _attach_notice_unread_counts(db, g.user["id"], my_classes)})

if __name__ == "__main__":
    app.run(debug=config.DEBUG)