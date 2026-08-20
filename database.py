import sqlite3
from flask import g
from werkzeug.security import generate_password_hash
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
    """데이터베이스 테이블을 초기화하고 기본 관리자 계정을 생성합니다."""
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
    cur.execute("INSERT OR IGNORE INTO site_info (info_key, content, updated_at) VALUES (?, ?, ?)",
                ("purpose", "", datetime.now().isoformat()))
    cur.execute("INSERT OR IGNORE INTO site_info (info_key, content, updated_at) VALUES (?, ?, ?)",
                ("team", "", datetime.now().isoformat()))
    cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_grade_classroom ON posts (grade, classroom)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_author_id ON posts (author_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_custom_timetable_user ON custom_timetable (user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_base_timetable_class ON class_base_timetable (grade, classroom)")
    # 기본 관리자 계정 (admin/1234)이 없으면 생성
    cur.execute("SELECT id FROM users WHERE userid = ?", ("admin",))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (userid, name, password, created_at) VALUES (?, ?, ?, ?)",
            ("admin", "관리자", generate_password_hash("1234"), datetime.now().isoformat())
        )
    db.commit()
    db.close()

def init_app(app):
    """Flask 앱에 DB 초기화 및 teardown 컨텍스트를 등록합니다."""
    app.teardown_appcontext(close_db)
    # 앱 시작 시 DB 파일과 테이블이 없는 경우를 대비해 초기화
    with app.app_context():
        init_db()
