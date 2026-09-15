import sqlite3
from flask import Flask, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"

DATABASE = "memo.db"

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
</style>
"""


def render_page(title, body):
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title}</title>
{PAGE_STYLE}
</head>
<body>
<div class="card">
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


def init_db():
    with app.app_context():
        db = get_db()
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
            """
        )
        db.commit()


@app.route("/")
def index():
    if "username" in session:
        body = f"""
        <h1>환영합니다, {session['username']}님</h1>
        <a href="{url_for('logout')}">로그아웃</a>
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
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hashed_password),
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
    return redirect(url_for("index"))


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
