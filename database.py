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
    # 기본 관리자 계정 (admin/1234)이 없으면 생성
    cur.execute("SELECT id FROM users WHERE userid = ?", ("admin",))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (userid, password, created_at) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("1234"), datetime.now().isoformat())
        )
    db.commit()
    db.close()

def init_app(app):
    """Flask 앱에 DB 초기화 및 teardown 컨텍스트를 등록합니다."""
    app.teardown_appcontext(close_db)
    # 앱 시작 시 DB 파일과 테이블이 없는 경우를 대비해 초기화
    with app.app_context():
        init_db()
