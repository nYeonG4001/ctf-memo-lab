import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, abort, g, redirect, request, session, url_for
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"

DATABASE = "memo.db"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin1234"
ADMIN_MEMO_TITLE = "관리자 메모"
ADMIN_MEMO_CONTENT = "SBOB{w3lc0me_4dm1n_p4n3l}"

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
    .links a {
        flex: 1;
        text-align: center;
        padding: 10px;
        border-radius: 6px;
        border: 1px solid #e0e0e0;
    }
    .links a.primary {
        background: #2f80ed;
        border-color: #2f80ed;
        color: #ffffff;
    }
    .links a.primary:hover {
        background: #2569c4;
    }
    .links a:not(.primary):hover {
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
        <h1>환영합니다, {session['username']}님</h1>
        <div class="links">
            <a href="{url_for('memo_list')}" class="primary">메모 목록</a>
            <a href="{url_for('logout')}">로그아웃</a>
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

        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
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

    body = """
    <h1>회원가입</h1>
    <form method="post">
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

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password"], password):
            body = """
            <h1>로그인</h1>
            <p class="msg">아이디 또는 비밀번호가 올바르지 않습니다.</p>
            <a href="/login">다시 시도</a>
            """
            return render_page("로그인", body)

        session["username"] = user["username"]
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        return redirect(url_for("index"))

    body = """
    <h1>로그인</h1>
    <form method="post">
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


@app.route("/logout")
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

    body = """
    <h1>새 메모</h1>
    <form method="post">
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


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5001)


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
