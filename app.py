import sqlite3
from flask import Flask, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-me"

DATABASE = "memo.db"


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
        return f"<h1>환영합니다, {session['username']}님</h1><a href='{url_for('logout')}'>로그아웃</a>"
    return f"<a href='{url_for('login')}'>로그인</a> | <a href='{url_for('signup')}'>회원가입</a>"


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if not username or not password:
            return "아이디와 비밀번호를 모두 입력해주세요. <a href='/signup'>다시 시도</a>"

        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing is not None:
            return "이미 존재하는 아이디입니다. <a href='/signup'>다시 시도</a>"

        hashed_password = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hashed_password),
        )
        db.commit()
        return redirect(url_for("login"))

    return """
    <h1>회원가입</h1>
    <form method="post">
        아이디: <input type="text" name="username"><br>
        비밀번호: <input type="password" name="password"><br>
        <input type="submit" value="가입하기">
    </form>
    """


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
            return "아이디 또는 비밀번호가 올바르지 않습니다. <a href='/login'>다시 시도</a>"

        session["username"] = user["username"]
        return redirect(url_for("index"))

    return """
    <h1>로그인</h1>
    <form method="post">
        아이디: <input type="text" name="username"><br>
        비밀번호: <input type="password" name="password"><br>
        <input type="submit" value="로그인">
    </form>
    """


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)


# 실행 방법:
# 1. (최초 1회) 가상환경을 만들고 Flask를 설치합니다.
#    python3 -m venv .venv
#    ./.venv/bin/pip install flask
# 2. 아래 명령어로 서버를 실행합니다.
#    ./.venv/bin/python app.py
# 3. 브라우저에서 http://127.0.0.1:5000 으로 접속합니다.
#    - 실행 시 memo.db (SQLite) 파일이 현재 폴더에 자동으로 생성됩니다.
#    - macOS(Homebrew Python)는 시스템에 pip로 직접 설치가 막혀있어(PEP 668),
#      가상환경(.venv) 사용을 권장합니다. python/pip 명령이 없다면 python3/pip3를 사용하세요.
