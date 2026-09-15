import os
import re
import secrets
import sqlite3
import time
from datetime import datetime
from functools import wraps

from flask import Flask, abort, g, redirect, request, session, url_for
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
# SECRET_KEY 환경변수를 설정하지 않으면 프로세스 시작마다 랜덤 키를 사용합니다.
# (하드코딩된 고정 키는 알려지면 세션 쿠키를 위조해 관리자 권한을 탈취당할 수 있습니다.)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

DATABASE = "memo.db"

# !!! 아래 기본값은 전부 플레이스홀더입니다. 실제 게임에 쓰면 안 됩니다 !!!
# 반드시 SECRET_KEY, ADMIN_PASSWORD, ADMIN_MEMO_CONTENT 환경변수로 덮어써서 실행하세요.
# (게임 운영 시에는 이 값들을 코드에 그대로 두지 마세요 — git 저장소에 커밋된 채로 두면
#  참가자가 해킹 없이 소스만 읽고 정답을 알 수 있습니다.)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme_before_game")
ADMIN_MEMO_TITLE = "관리자 메모"
ADMIN_MEMO_CONTENT = os.environ.get("ADMIN_MEMO_CONTENT", "SBOB{replace_this_before_game}")

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60
_login_attempts = {}


def _login_attempt_key(username):
    # IP + 아이디로 묶어서, 공격자가 아이디만 알아도 진짜 사용자를 잠그지 못하게 합니다.
    return (request.remote_addr, username)


def is_login_locked(username):
    key = _login_attempt_key(username)
    now = time.time()
    attempts = [t for t in _login_attempts.get(key, []) if now - t < LOGIN_LOCKOUT_SECONDS]
    if attempts:
        _login_attempts[key] = attempts
    else:
        _login_attempts.pop(key, None)
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def record_failed_login(username):
    key = _login_attempt_key(username)
    _login_attempts.setdefault(key, []).append(time.time())


def clear_login_attempts(username):
    _login_attempts.pop(_login_attempt_key(username), None)


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["csrf_token"] = token
    return token


def csrf_field():
    return f'<input type="hidden" name="csrf_token" value="{get_csrf_token()}">'


@app.before_request
def check_csrf():
    if request.method == "POST":
        token = session.get("csrf_token")
        submitted = request.form.get("csrf_token")
        if not token or not submitted or not secrets.compare_digest(token, submitted):
            abort(400)


@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


PAGE_STYLE = """
<style>
    * { box-sizing: border-box; }
    body {
        margin: 0;
        padding: 60px 16px;
        background: #f7f7f5;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #37352f;
        display: flex;
        justify-content: center;
    }
    .card {
        background: #ffffff;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        padding: 40px 32px;
        width: 100%;
        max-width: 360px;
    }
    h1 {
        font-size: 20px;
        font-weight: 600;
        margin: 0 0 24px;
    }
    label {
        display: block;
        font-size: 13px;
        color: #6b6b6b;
        margin-bottom: 6px;
    }
    .field {
        margin-bottom: 16px;
    }
    input[type="text"],
    input[type="password"] {
        width: 100%;
        padding: 8px 10px;
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        font-size: 14px;
        font-family: inherit;
    }
    input[type="text"]:focus,
    input[type="password"]:focus {
        outline: none;
        border-color: #2f80ed;
    }
    input[type="submit"] {
        width: 100%;
        padding: 10px;
        background: #2f80ed;
        color: #ffffff;
        border: none;
        border-radius: 6px;
        font-size: 14px;
        margin-top: 8px;
        cursor: pointer;
    }
    input[type="submit"]:hover {
        background: #2569c4;
    }
    a {
        color: #2f80ed;
        text-decoration: none;
        font-size: 14px;
    }
    a:hover {
        text-decoration: underline;
    }
    p.msg {
        font-size: 14px;
        color: #6b6b6b;
        margin: 0 0 16px;
    }
    .links {
        display: flex;
        gap: 12px;
    }
    .links a,
    .links form {
        flex: 1;
    }
    .links a,
    .links button {
        display: block;
        width: 100%;
        text-align: center;
        padding: 10px;
        border-radius: 6px;
        border: 1px solid #e0e0e0;
        background: #ffffff;
        color: #37352f;
        font-size: 14px;
        font-family: inherit;
        cursor: pointer;
        text-decoration: none;
    }
    .links a.primary,
    .links button.primary {
        background: #2f80ed;
        border-color: #2f80ed;
        color: #ffffff;
    }
    .links a.primary:hover,
    .links button.primary:hover {
        background: #2569c4;
    }
    .links a:not(.primary):hover,
    .links button:not(.primary):hover {
        border-color: #2f80ed;
        text-decoration: none;
    }
    .card.wide {
        max-width: 640px;
    }
    form {
        margin: 0;
    }
    textarea {
        width: 100%;
        min-height: 160px;
        padding: 8px 10px;
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        font-size: 14px;
        font-family: inherit;
        resize: vertical;
    }
    textarea:focus {
        outline: none;
        border-color: #2f80ed;
    }
    .toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
    }
    .toolbar h1 {
        margin: 0;
    }
    .memo-list {
        list-style: none;
        margin: 0;
        padding: 0;
    }
    .memo-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid #ededec;
    }
    .memo-item:last-child {
        border-bottom: none;
    }
    .memo-item a {
        color: #37352f;
        font-size: 15px;
    }
    .memo-item a:hover {
        color: #2f80ed;
        text-decoration: none;
    }
    .memo-date {
        font-size: 12px;
        color: #9b9a97;
    }
    .memo-content {
        font-size: 14px;
        line-height: 1.6;
        white-space: pre-wrap;
        margin: 16px 0 24px;
    }
    .btn-row {
        display: flex;
        gap: 12px;
        margin-top: 8px;
    }
    .btn-row a,
    .btn-row form {
        flex: 1;
    }
    .btn-row a,
    .btn-row button {
        display: block;
        width: 100%;
        padding: 10px;
        border-radius: 6px;
        border: 1px solid #e0e0e0;
        background: #ffffff;
        color: #37352f;
        font-size: 14px;
        font-family: inherit;
        text-align: center;
        text-decoration: none;
        cursor: pointer;
    }
    .btn-row a:hover,
    .btn-row button:hover {
        border-color: #2f80ed;
        text-decoration: none;
    }
</style>
"""


def render_page(title, body, wide=False):
    card_class = "card wide" if wide else "card"
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title}</title>
{PAGE_STYLE}
</head>
<body>
<div class="{card_class}">
{body}
</div>
</body>
</html>"""


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def ensure_column(db, table, column, definition):
    existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db():
    with app.app_context():
        db = get_db()
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS memos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        ensure_column(db, "users", "role", "role TEXT NOT NULL DEFAULT 'user'")
        ensure_column(db, "users", "created_at", "created_at TEXT")
        db.commit()

        admin = db.execute(
            "SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)
        ).fetchone()
        if admin is None:
            db.execute(
                "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
                (
                    ADMIN_USERNAME,
                    generate_password_hash(ADMIN_PASSWORD),
                    "admin",
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            db.commit()

            admin_id = db.execute(
                "SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)
            ).fetchone()["id"]
            db.execute(
                "INSERT INTO memos (user_id, title, content, created_at) VALUES (?, ?, ?, ?)",
                (
                    admin_id,
                    ADMIN_MEMO_TITLE,
                    ADMIN_MEMO_CONTENT,
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            db.commit()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapped


def get_own_memo(memo_id):
    db = get_db()
    memo = db.execute(
        "SELECT * FROM memos WHERE id = ? AND user_id = ?",
        (memo_id, session["user_id"]),
    ).fetchone()
    if memo is None:
        abort(404)
    return memo


@app.route("/")
def index():
    if "username" in session:
        admin_link = (
            f'<a href="{url_for("admin_dashboard")}">관리자 페이지</a>'
            if session.get("role") == "admin"
            else ""
        )
        body = f"""
        <h1>환영합니다, {escape(session['username'])}님</h1>
        <div class="links">
            <a href="{url_for('memo_list')}" class="primary">메모 목록</a>
            <form method="post" action="{url_for('logout')}">
                {csrf_field()}
                <button type="submit">로그아웃</button>
            </form>
        </div>
        {admin_link}
        """
        return render_page("메모 서비스", body)

    body = f"""
    <h1>메모 서비스</h1>
    <div class="links">
        <a href="{url_for('login')}">로그인</a>
        <a href="{url_for('signup')}" class="primary">회원가입</a>
    </div>
    """
    return render_page("메모 서비스", body)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if not username or not password:
            body = """
            <h1>회원가입</h1>
            <p class="msg">아이디와 비밀번호를 모두 입력해주세요.</p>
            <a href="/signup">다시 시도</a>
            """
            return render_page("회원가입", body)

        if not USERNAME_PATTERN.fullmatch(username):
            body = """
            <h1>회원가입</h1>
            <p class="msg">아이디는 영문/숫자/밑줄(_) 3~20자여야 합니다.</p>
            <a href="/signup">다시 시도</a>
            """
            return render_page("회원가입", body)

        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if existing is not None:
            body = """
            <h1>회원가입</h1>
            <p class="msg">이미 존재하는 아이디입니다.</p>
            <a href="/signup">다시 시도</a>
            """
            return render_page("회원가입", body)

        hashed_password = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
            (username, hashed_password, "user", datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        db.commit()
        return redirect(url_for("login"))

    body = f"""
    <h1>회원가입</h1>
    <form method="post">
        {csrf_field()}
        <div class="field">
            <label for="username">아이디</label>
            <input type="text" id="username" name="username">
        </div>
        <div class="field">
            <label for="password">비밀번호</label>
            <input type="password" id="password" name="password">
        </div>
        <input type="submit" value="가입하기">
    </form>
    """
    return render_page("회원가입", body)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if is_login_locked(username):
            body = """
            <h1>로그인</h1>
            <p class="msg">로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.</p>
            <a href="/login">다시 시도</a>
            """
            return render_page("로그인", body)

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password"], password):
            record_failed_login(username)
            body = """
            <h1>로그인</h1>
            <p class="msg">아이디 또는 비밀번호가 올바르지 않습니다.</p>
            <a href="/login">다시 시도</a>
            """
            return render_page("로그인", body)

        clear_login_attempts(username)
        session.clear()
        session["username"] = user["username"]
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        return redirect(url_for("index"))

    body = f"""
    <h1>로그인</h1>
    <form method="post">
        {csrf_field()}
        <div class="field">
            <label for="username">아이디</label>
            <input type="text" id="username" name="username">
        </div>
        <div class="field">
            <label for="password">비밀번호</label>
            <input type="password" id="password" name="password">
        </div>
        <input type="submit" value="로그인">
    </form>
    """
    return render_page("로그인", body)


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("username", None)
    session.pop("user_id", None)
    session.pop("role", None)
    return redirect(url_for("index"))


@app.route("/memos")
@login_required
def memo_list():
    db = get_db()
    memos = db.execute(
        "SELECT id, title, created_at FROM memos WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],),
    ).fetchall()

    if memos:
        items = "".join(
            f"""
            <li class="memo-item">
                <a href="{url_for('memo_detail', memo_id=memo['id'])}">{escape(memo['title'])}</a>
                <span class="memo-date">{memo['created_at']}</span>
            </li>
            """
            for memo in memos
        )
        list_html = f'<ul class="memo-list">{items}</ul>'
    else:
        list_html = '<p class="msg">작성한 메모가 없습니다.</p>'

    body = f"""
    <div class="toolbar">
        <h1>내 메모</h1>
        <a href="{url_for('memo_new')}">새 메모</a>
    </div>
    {list_html}
    <a href="{url_for('index')}">홈으로</a>
    """
    return render_page("내 메모", body, wide=True)


@app.route("/memos/new", methods=["GET", "POST"])
@login_required
def memo_new():
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]

        if not title or not content:
            body = f"""
            <h1>새 메모</h1>
            <p class="msg">제목과 내용을 모두 입력해주세요.</p>
            <form method="post">
                {csrf_field()}
                <div class="field">
                    <label for="title">제목</label>
                    <input type="text" id="title" name="title" value="{escape(title)}">
                </div>
                <div class="field">
                    <label for="content">내용</label>
                    <textarea id="content" name="content">{escape(content)}</textarea>
                </div>
                <input type="submit" value="저장">
            </form>
            """
            return render_page("새 메모", body, wide=True)

        db = get_db()
        db.execute(
            "INSERT INTO memos (user_id, title, content, created_at) VALUES (?, ?, ?, ?)",
            (
                session["user_id"],
                title,
                content,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )
        db.commit()
        return redirect(url_for("memo_list"))

    body = f"""
    <h1>새 메모</h1>
    <form method="post">
        {csrf_field()}
        <div class="field">
            <label for="title">제목</label>
            <input type="text" id="title" name="title">
        </div>
        <div class="field">
            <label for="content">내용</label>
            <textarea id="content" name="content"></textarea>
        </div>
        <input type="submit" value="저장">
    </form>
    """
    return render_page("새 메모", body, wide=True)


@app.route("/memos/<int:memo_id>")
@login_required
def memo_detail(memo_id):
    memo = get_own_memo(memo_id)

    body = f"""
    <div class="toolbar">
        <h1>{escape(memo['title'])}</h1>
    </div>
    <p class="memo-date">{memo['created_at']}</p>
    <div class="memo-content">{escape(memo['content'])}</div>
    <div class="btn-row">
        <a href="{url_for('memo_edit', memo_id=memo['id'])}">수정</a>
        <form method="post" action="{url_for('memo_delete', memo_id=memo['id'])}">
            {csrf_field()}
            <button type="submit">삭제</button>
        </form>
    </div>
    <a href="{url_for('memo_list')}">목록으로</a>
    """
    return render_page(str(escape(memo["title"])), body, wide=True)


@app.route("/memos/<int:memo_id>/edit", methods=["GET", "POST"])
@login_required
def memo_edit(memo_id):
    memo = get_own_memo(memo_id)

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]

        if not title or not content:
            body = f"""
            <h1>메모 수정</h1>
            <p class="msg">제목과 내용을 모두 입력해주세요.</p>
            <form method="post">
                {csrf_field()}
                <div class="field">
                    <label for="title">제목</label>
                    <input type="text" id="title" name="title" value="{escape(title)}">
                </div>
                <div class="field">
                    <label for="content">내용</label>
                    <textarea id="content" name="content">{escape(content)}</textarea>
                </div>
                <input type="submit" value="수정 완료">
            </form>
            """
            return render_page("메모 수정", body, wide=True)

        db = get_db()
        db.execute(
            "UPDATE memos SET title = ?, content = ? WHERE id = ? AND user_id = ?",
            (title, content, memo_id, session["user_id"]),
        )
        db.commit()
        return redirect(url_for("memo_detail", memo_id=memo_id))

    body = f"""
    <h1>메모 수정</h1>
    <form method="post">
        {csrf_field()}
        <div class="field">
            <label for="title">제목</label>
            <input type="text" id="title" name="title" value="{escape(memo['title'])}">
        </div>
        <div class="field">
            <label for="content">내용</label>
            <textarea id="content" name="content">{escape(memo['content'])}</textarea>
        </div>
        <input type="submit" value="수정 완료">
    </form>
    """
    return render_page("메모 수정", body, wide=True)


@app.route("/memos/<int:memo_id>/delete", methods=["POST"])
@login_required
def memo_delete(memo_id):
    get_own_memo(memo_id)
    db = get_db()
    db.execute(
        "DELETE FROM memos WHERE id = ? AND user_id = ?",
        (memo_id, session["user_id"]),
    )
    db.commit()
    return redirect(url_for("memo_list"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    users = db.execute(
        "SELECT username, role, created_at FROM users ORDER BY id"
    ).fetchall()

    rows = "".join(
        f"""
        <li class="memo-item">
            <span>{escape(u['username'])}{' (admin)' if u['role'] == 'admin' else ''}</span>
            <span class="memo-date">{u['created_at'] or '-'}</span>
        </li>
        """
        for u in users
    )

    body = f"""
    <div class="toolbar">
        <h1>회원 목록</h1>
        <a href="{url_for('index')}">홈으로</a>
    </div>
    <ul class="memo-list">{rows}</ul>
    """
    return render_page("관리자", body, wide=True)


def warn_if_config_stale():
    if ADMIN_PASSWORD == "changeme_before_game":
        print(f"[경고] ADMIN_PASSWORD가 기본 플레이스홀더({ADMIN_PASSWORD!r})입니다. "
              "게임 전 환경변수로 반드시 바꿔주세요.")
    if ADMIN_MEMO_CONTENT == "SBOB{replace_this_before_game}":
        print(f"[경고] ADMIN_MEMO_CONTENT(플래그)가 기본 플레이스홀더({ADMIN_MEMO_CONTENT!r})입니다. "
              "게임 전 환경변수로 반드시 바꿔주세요.")

    if not os.path.exists(DATABASE):
        return
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT password FROM users WHERE username = ? COLLATE NOCASE", (ADMIN_USERNAME,)
    ).fetchone()
    conn.close()
    if row is not None and not check_password_hash(row["password"], ADMIN_PASSWORD):
        print(f"[경고] 기존 {DATABASE}의 '{ADMIN_USERNAME}' 계정 비밀번호가 지금 설정한 "
              "ADMIN_PASSWORD와 다릅니다 (admin 계정은 최초 생성 시에만 비밀번호가 저장됩니다). "
              f"새 값을 적용하려면 {DATABASE} 파일을 삭제한 뒤 다시 실행하세요.")


if __name__ == "__main__":
    init_db()
    warn_if_config_stale()
    # 개발 중 디버거가 필요하면 FLASK_DEBUG=1로 실행하세요.
    # (debug=True는 Werkzeug 인터랙티브 디버거를 열어 RCE 위험이 있어 기본값은 False입니다.)
    debug_mode = os.environ.get("FLASK_DEBUG") == "1"
    # 게임 서버로 열 때는 HOST=0.0.0.0으로 실행하세요 (기본값 127.0.0.1은 외부 접속 불가).
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(debug=debug_mode, host=host, port=5001)


# 실행 방법:
# 1. (최초 1회) 가상환경을 만들고 Flask를 설치합니다.
#    python3 -m venv .venv
#    ./.venv/bin/pip install flask
# 2. 아래 명령어로 서버를 실행합니다.
#    ./.venv/bin/python app.py
# 3. 브라우저에서 http://127.0.0.1:5001 으로 접속합니다.
#    - 실행 시 memo.db (SQLite) 파일이 현재 폴더에 자동으로 생성됩니다.
#    - macOS(Homebrew Python)는 시스템에 pip로 직접 설치가 막혀있어(PEP 668),
#      가상환경(.venv) 사용을 권장합니다. python/pip 명령이 없다면 python3/pip3를 사용하세요.
#    - 포트는 5000 대신 5001을 사용합니다. macOS의 AirPlay Receiver(제어센터)가
#      기본적으로 5000번 포트를 점유해 127.0.0.1:5000 접속 시 403 오류가 날 수 있습니다.
#
# 모의해킹 게임 운영 시 보안 체크리스트:
#    - !!! 필수 !!! SECRET_KEY, ADMIN_PASSWORD, ADMIN_MEMO_CONTENT 환경변수를
#      게임 시작 전 반드시 실제 값으로 설정하세요.
#      코드 상단의 기본값(changeme_before_game, SBOB{replace_this_before_game} 등)은
#      전부 플레이스홀더이며, 이미 공개 저장소에 커밋되어 있어 그대로 쓰면 안 됩니다.
#      예) SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
#          ADMIN_PASSWORD="원하는_관리자_비번" \
#          ADMIN_MEMO_CONTENT="SBOB{실제_플래그}" \
#          ./.venv/bin/python app.py
#    - FLASK_DEBUG는 게임 중에는 설정하지 마세요 (기본값 False가 안전합니다).
#    - 게임 시작 전 기존 memo.db를 삭제하고 새로 시작하면 admin 계정/플래그가 새 값으로 재생성됩니다.
#      (admin 계정은 최초 1회만 생성되므로, memo.db를 안 지우면 환경변수를 바꿔도 무시됩니다.
#       실행 시 기존 비밀번호와 다르면 경고 메시지가 출력됩니다.)
#    - 기본값은 HOST=127.0.0.1(로컬에서만 접속 가능)입니다. 참가자들이 접속할 수 있는
#      게임 서버로 열려면 HOST=0.0.0.0 으로 실행하세요.
