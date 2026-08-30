import sqlite3
from flask import g
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

import config

def get_db():
    """Application context에 DB 연결이 없으면 생성하고, 있으면 기존 연결을 반환합니다."""
    if "db" not in g:
        g.db = sqlite3.connect(config.DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(exc=None):
    """Application context가 teardown될 때 DB 연결을 닫습니다."""
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    """데이터베이스 테이블을 초기화하고 환경변수 기반 관리자 계정을 보장합니다."""
    db = sqlite3.connect(config.DATABASE_PATH)
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        userid TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        grade TEXT,
        classroom TEXT,
        student_no TEXT,
        is_teacher INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        grade TEXT NOT NULL,
        classroom TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id),
        UNIQUE(user_id, grade, classroom)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grade INTEGER NOT NULL,
        classroom INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        author_id INTEGER NOT NULL, -- users 테이블의 id를 참조
        is_pinned INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (author_id) REFERENCES users (id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS custom_timetable (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 4),
        period INTEGER NOT NULL CHECK(period BETWEEN 1 AND 7),
        subject TEXT NOT NULL DEFAULT '',
        color TEXT NOT NULL DEFAULT '#ffffff',
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id),
        UNIQUE(user_id, day_of_week, period)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS timetable_profiles (
        user_id INTEGER PRIMARY KEY,
        grade INTEGER NOT NULL CHECK(grade BETWEEN 1 AND 2),
        classroom INTEGER NOT NULL CHECK(classroom BETWEEN 1 AND 10),
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS class_base_timetable (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grade INTEGER NOT NULL CHECK(grade BETWEEN 1 AND 2),
        classroom INTEGER NOT NULL CHECK(classroom BETWEEN 1 AND 10),
        day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 4),
        period INTEGER NOT NULL CHECK(period BETWEEN 1 AND 7),
        subject TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        UNIQUE(grade, classroom, day_of_week, period)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS site_info (
        info_key TEXT PRIMARY KEY,
        content TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS post_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        storage_path TEXT NOT NULL UNIQUE,
        public_url TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (post_id) REFERENCES posts (id) ON DELETE CASCADE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS post_reads (
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        read_at TEXT NOT NULL,
        PRIMARY KEY (user_id, post_id),
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (post_id) REFERENCES posts (id) ON DELETE CASCADE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        author_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (post_id) REFERENCES posts (id) ON DELETE CASCADE,
        FOREIGN KEY (author_id) REFERENCES users (id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT NOT NULL,
        userid TEXT NOT NULL DEFAULT '',
        failed_count INTEGER NOT NULL DEFAULT 0,
        first_failed_at TEXT NOT NULL,
        last_failed_at TEXT NOT NULL,
        locked_until TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        userid TEXT,
        student_no_hash TEXT,
        ip TEXT NOT NULL,
        path TEXT NOT NULL,
        method TEXT NOT NULL,
        event_type TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blacklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        userid TEXT,
        student_no_hash TEXT,
        ip TEXT,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER,
        actor_userid TEXT NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT NOT NULL DEFAULT '',
        target_id TEXT,
        details TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("INSERT OR IGNORE INTO site_info (info_key, content, updated_at) VALUES (?, ?, ?)",
                ("purpose", "", datetime.now().isoformat()))
    cur.execute("INSERT OR IGNORE INTO site_info (info_key, content, updated_at) VALUES (?, ?, ?)",
                ("team", "", datetime.now().isoformat()))
    # 기존 DB를 보존하면서 권한/고정 기능용 컬럼만 자동 마이그레이션합니다.
    user_columns = {row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    if "is_teacher" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN is_teacher INTEGER NOT NULL DEFAULT 0")

    blacklist_columns = {row[1] for row in cur.execute("PRAGMA table_info(blacklist)").fetchall()}
    if "userid" not in blacklist_columns:
        cur.execute("ALTER TABLE blacklist ADD COLUMN userid TEXT")

    post_columns = {row[1] for row in cur.execute("PRAGMA table_info(posts)").fetchall()}
    if "is_pinned" not in post_columns:
        cur.execute("ALTER TABLE posts ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0")
    if "updated_at" not in post_columns:
        cur.execute("ALTER TABLE posts ADD COLUMN updated_at TEXT")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_grade_classroom ON posts (grade, classroom)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_author_id ON posts (author_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_post_images_post ON post_images (post_id, sort_order)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_post_reads_user ON post_reads (user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_post_reads_post ON post_reads (post_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_post ON comments (post_id, id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_author ON comments (author_id, id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_key ON login_attempts (ip, userid)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_security_events_created ON security_events (created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_security_events_user ON security_events (user_id, created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_user ON blacklist (user_id, active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_userid ON blacklist (userid, active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_student ON blacklist (student_no_hash, active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_ip ON blacklist (ip, active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs (created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_custom_timetable_user ON custom_timetable (user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_base_timetable_class ON class_base_timetable (grade, classroom)")
    # 관리자 ID/비밀번호는 배포 환경변수를 단일 기준으로 사용합니다.
    # 기존 DB에서도 ADMIN_PASSWORD를 변경하면 다음 앱 시작 시 관리자 비밀번호가 갱신됩니다.
    cur.execute("SELECT id, password FROM users WHERE userid = ?", (config.ADMIN_ID,))
    admin = cur.fetchone()
    if admin is None:
        cur.execute(
            "INSERT INTO users (userid, name, password, grade, classroom, student_no, is_teacher, created_at) "
            "VALUES (?, ?, ?, NULL, NULL, NULL, 0, ?)",
            (config.ADMIN_ID, "관리자", generate_password_hash(config.ADMIN_PASSWORD), datetime.now().isoformat())
        )
    elif not check_password_hash(admin[1], config.ADMIN_PASSWORD):
        cur.execute(
            "UPDATE users SET password = ?, name = ?, grade = NULL, classroom = NULL, "
            "student_no = NULL, is_teacher = 0 WHERE id = ?",
            (generate_password_hash(config.ADMIN_PASSWORD), "관리자", admin[0])
        )
    db.commit()
    db.close()

def init_app(app):
    """Flask 앱에 DB 초기화 및 teardown 컨텍스트를 등록합니다."""
    app.teardown_appcontext(close_db)
    # 앱 시작 시 DB 파일과 테이블이 없는 경우를 대비해 초기화
    with app.app_context():
        init_db()
