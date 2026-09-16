import os
import random
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, Response, abort, g, redirect, request, session, url_for
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

DATABASE = os.environ.get("DATABASE", "memo.db")

# !!! 아래 기본값은 전부 플레이스홀더입니다. 실제 게임에 쓰면 안 됩니다 !!!
# 반드시 SECRET_KEY, ADMIN_PASSWORD, ADMIN_MEMO_CONTENT 환경변수로 덮어써서 실행하세요.
# (게임 운영 시에는 이 값들을 코드에 그대로 두지 마세요 — git 저장소에 커밋된 채로 두면
#  참가자가 해킹 없이 소스만 읽고 정답을 알 수 있습니다.)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme_before_game")
# 제목만 보고 플래그 메모를 특정할 수 없도록 평범한 제목을 씁니다 ("관리자 메모" 같은 티 나는 제목 지양).
ADMIN_MEMO_TITLE = "인수인계"
ADMIN_MEMO_CONTENT = os.environ.get("ADMIN_MEMO_CONTENT", "SBOB{replace_this_before_game}")

# admin 계정 최초 생성 시 플래그 메모와 함께 만들어지는 미끼 메모들.
# 플래그 메모가 목록에서 튀지 않도록 섞는 용도이니, 평범한 업무/일상 메모 톤으로 자유롭게 수정하세요.
DECOY_MEMOS = [
    ("회의 메모", "다음 주 배포 일정 논의 필요"),
    ("임시 저장", "작성 중..."),
    ("서버 점검 기록", "9/15 새벽 점검 완료, 특이사항 없음"),
    ("장보기", "우유, 계란, 식빵"),
    ("TODO", "리뷰 남기기, 문서 정리, 백업 확인"),
    ("회의록", "스프린트 회고 - 다음 스프린트 목표 정리"),
    ("휴가 계획", "다음 달 초 3일 휴가 예정"),
    ("비밀번호 힌트", "까먹을 때 대비용 메모 (실제로는 안 씀)"),
]

# 검증 없이 아무거나 제출하는 참가자를 거르기 위한 가짜 플래그.
# 진짜 플래그(ADMIN_MEMO_CONTENT)와 형식만 같고 값은 다릅니다.
# FAKE_FLAG_CONTENT: 가짜 관리자 계정(DECOY_ADMIN_ACCOUNTS)에 항상 심어지는 기본 가짜 플래그.
# FAKE_FLAG_CONTENT_2/3: DECOY_MEMOS 풀에 섞여서 admin 본인 메모함/가짜 관리자 계정 미끼에 랜덤 등장.
FAKE_FLAG_CONTENT = "SBOB{n0t_th3_r34l_fl4g}"
FAKE_FLAG_CONTENT_2 = "SBOB{4lm0st_g0t_1t}"
FAKE_FLAG_CONTENT_3 = "SBOB{w40n9_4cc0unt_bud}"

# /submit에서 오답 감점(-10점) 판정에 쓰는 가짜 플래그 전체 목록.
# 지금까지 심어둔 가짜 플래그를 전부 등록해두세요 (여러 개면 콤마로 추가).
FAKE_FLAGS = [FAKE_FLAG_CONTENT, FAKE_FLAG_CONTENT_2, FAKE_FLAG_CONTENT_3]

# DECOY_MEMOS 풀에 가짜 플래그 2개를 평범한 제목으로 섞어 넣습니다.
# (admin 본인 메모함에는 항상 포함되고, 가짜 관리자 계정 미끼에는 랜덤으로 섞여 들어갑니다.)
DECOY_MEMOS += [
    ("백업 메모", FAKE_FLAG_CONTENT_2),
    ("예전 설정값", FAKE_FLAG_CONTENT_3),
]

# "administrator", "superadmin" 처럼 관리자스러운 이름을 쓰지만 실제 role은 "user"인 가짜 관리자
# 계정입니다. 진짜 admin 권한은 없고, 착각을 유도하는 용도입니다. (비밀번호는 자유롭게 변경하세요.)
DECOY_ADMIN_ACCOUNTS = [
    ("administrator", "adm1n_d3c0y_pw1"),
    ("superadmin", "adm1n_d3c0y_pw2"),
]

# park_intern 계정: /internal/notes 힌트("이름+연도" 규칙)로 유추 가능한 비밀번호를 씁니다.
# 힌트 문구와 반드시 짝이 맞아야 하므로, 비번을 직접 바꾸려면 internal_notes()의 안내 문구도 같이 수정하세요.
PARK_INTERN_USERNAME = "park_intern"
PARK_INTERN_PASSWORD = f"park{datetime.now().year}"

# 평범한 일반 유저 계정입니다. 계정을 탈취해도 진짜/가짜 플래그 없이 순수 미끼용 메모만 들어있습니다.
DECOY_NORMAL_ACCOUNTS = [
    ("kim_dev", "kim_pw_1234"),
    (PARK_INTERN_USERNAME, PARK_INTERN_PASSWORD),
    ("lee_designer", "lee_pw_1234"),
]

# DECOY_NORMAL_ACCOUNTS 계정들의 메모함에 들어가는 순수 미끼 메모 (플래그 없음).
DECOY_NORMAL_MEMOS = [
    ("점심 메뉴", "김치찌개 vs 파스타 고민중"),
    ("코드 리뷰", "PR #42 리뷰 남기기"),
    ("readme 수정", "설치 방법 오타 고치기"),
    ("일정", "다음 주 화요일 오후 미팅"),
]

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
        background: #f7f7f5;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #37352f;
    }
    .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 14px 24px;
        background: #ffffff;
        border-bottom: 1px solid #ededec;
    }
    .topbar-brand {
        font-weight: 600;
        font-size: 14px;
        color: #37352f;
        text-decoration: none;
    }
    .topbar-right {
        display: flex;
        align-items: center;
        gap: 16px;
        font-size: 14px;
    }
    .topbar-right a {
        font-size: 14px;
    }
    .topbar-user {
        color: #6b6b6b;
    }
    .page {
        padding: 60px 16px;
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
    .form-footer {
        font-size: 14px;
        color: #6b6b6b;
        margin: 20px 0 0;
    }
    .links {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        gap: 12px;
    }
    .links + .links {
        margin-top: 12px;
    }
    .links:has(a.hero) + .links {
        margin-top: 24px;
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
        white-space: nowrap;
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
    .links a.hero {
        padding: 14px;
        font-size: 16px;
        font-weight: 600;
    }
    .links a.admin-link {
        border-style: dashed;
        color: #6b6b6b;
    }
    .links a.admin-link:hover {
        border-color: #37352f;
        color: #37352f;
    }
    .link-button {
        background: none;
        border: none;
        padding: 0;
        color: #2f80ed;
        font-size: 13px;
        font-family: inherit;
        cursor: pointer;
        text-decoration: none;
    }
    .link-button:hover {
        text-decoration: underline;
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
    .memo-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 12px;
    }
    .memo-card {
        display: block;
        background: #ffffff;
        border: 1px solid #ededec;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
        color: #37352f;
        text-decoration: none;
    }
    .memo-card:hover {
        border-color: #2f80ed;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
        text-decoration: none;
    }
    .memo-card-title {
        font-size: 15px;
        font-weight: 600;
        margin-bottom: 8px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .memo-card-date {
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
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        background: #2f80ed;
        color: #ffffff;
        font-size: 11px;
        margin-left: 6px;
    }
    .rank-number {
        display: inline-block;
        min-width: 20px;
        margin-right: 8px;
        color: #9b9a97;
    }
    .memo-item.rank-top {
        font-weight: 700;
    }
    .memo-item.rank-top .rank-number {
        color: #37352f;
    }
    .rank-number.rank-first {
        color: #2f80ed;
    }
</style>
"""


def render_page(title, body, wide=False):
    card_class = "card wide" if wide else "card"
    topbar_html = ""
    if "username" in session:
        topbar_right = f'<span class="topbar-user">{escape(session["username"])}</span>'
        topbar_html = f"""<div class="topbar">
    <a href="{url_for('index')}" class="topbar-brand">메모</a>
    <div class="topbar-right">{topbar_right}</div>
</div>
"""
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🧈</text></svg>">
{PAGE_STYLE}
</head>
<body>
{topbar_html}<div class="page">
<div class="{card_class}">
{body}
</div>
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


def random_recent_timestamp(min_days_ago=1, max_days_ago=21):
    # 시드 데이터가 전부 같은 시각에 생성된 티가 나지 않도록, 최근 며칠~몇 주 사이로 흩뿌립니다.
    total_minutes = random.randint(min_days_ago * 24 * 60, max_days_ago * 24 * 60)
    dt = datetime.now() - timedelta(minutes=total_minutes)
    return dt.strftime("%Y-%m-%d %H:%M")


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
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                submitted_flag TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
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

            # 플래그 메모가 목록 맨 위/아래에 고정되지 않도록, 미끼 메모들과 섞어서 저장합니다.
            # 작성일도 전부 같은 시각이 아니라 각각 랜덤하게 흩뿌립니다.
            admin_seed_memos = [(ADMIN_MEMO_TITLE, ADMIN_MEMO_CONTENT)] + list(DECOY_MEMOS)
            random.shuffle(admin_seed_memos)

            for title, content in admin_seed_memos:
                db.execute(
                    "INSERT INTO memos (user_id, title, content, created_at) VALUES (?, ?, ?, ?)",
                    (admin_id, title, content, random_recent_timestamp()),
                )
            db.commit()

            # 가짜 관리자 계정: 이름만 그럴듯하고 role은 "user"라 실제 admin 권한은 없습니다.
            # 진짜 admin 메모와 같은 제목("인수인계")으로 가짜 플래그를 심어서 더 헷갈리게 합니다.
            for username, password in DECOY_ADMIN_ACCOUNTS:
                db.execute(
                    "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
                    (
                        username,
                        generate_password_hash(password),
                        "user",
                        random_recent_timestamp(),
                    ),
                )
                db.commit()

                user_id = db.execute(
                    "SELECT id FROM users WHERE username = ?", (username,)
                ).fetchone()["id"]

                fake_admin_memos = [(ADMIN_MEMO_TITLE, FAKE_FLAG_CONTENT)] + random.sample(
                    DECOY_MEMOS, k=min(2, len(DECOY_MEMOS))
                )
                random.shuffle(fake_admin_memos)
                for title, content in fake_admin_memos:
                    db.execute(
                        "INSERT INTO memos (user_id, title, content, created_at) VALUES (?, ?, ?, ?)",
                        (user_id, title, content, random_recent_timestamp()),
                    )
                db.commit()

            # 순수 미끼 계정: 계정을 탈취해도 진짜/가짜 플래그 없이 평범한 메모만 나옵니다.
            for username, password in DECOY_NORMAL_ACCOUNTS:
                db.execute(
                    "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
                    (
                        username,
                        generate_password_hash(password),
                        "user",
                        random_recent_timestamp(),
                    ),
                )
                db.commit()

                user_id = db.execute(
                    "SELECT id FROM users WHERE username = ?", (username,)
                ).fetchone()["id"]

                for title, content in DECOY_NORMAL_MEMOS:
                    db.execute(
                        "INSERT INTO memos (user_id, title, content, created_at) VALUES (?, ?, ?, ?)",
                        (user_id, title, content, random_recent_timestamp()),
                    )

                # park_intern 계정에는 진짜 admin 비밀번호로 이어지는 단서를 하나 더 심습니다.
                # ADMIN_PASSWORD를 그대로 참조하므로, 운영자가 환경변수를 바꾸면 자동으로 최신 값이 반영됩니다.
                if username == PARK_INTERN_USERNAME:
                    db.execute(
                        "INSERT INTO memos (user_id, title, content, created_at) VALUES (?, ?, ?, ?)",
                        (
                            user_id,
                            "메모",
                            f"관리자 계정 비번 기억 안 나서 메모: {ADMIN_PASSWORD}",
                            random_recent_timestamp(),
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


def compute_scores(db):
    # 제출 이력이 한 번도 없는 계정(아직 발견/탈취되지 않은 시드 계정 포함)은 목록에서 제외합니다.
    # 그래야 로그인만 하면 관리자스러운 계정 이름들이 점수판에서 미리 다 보이는 걸 막을 수 있습니다.
    users = db.execute(
        """
        SELECT DISTINCT u.id, u.username
        FROM users u
        JOIN submissions s ON s.user_id = u.id
        ORDER BY u.id
        """
    ).fetchall()

    first_blood_row = db.execute(
        "SELECT user_id FROM submissions WHERE is_correct = 1 ORDER BY id ASC LIMIT 1"
    ).fetchone()
    first_blood_user_id = first_blood_row["user_id"] if first_blood_row else None

    correct_user_ids = {
        row["user_id"]
        for row in db.execute("SELECT DISTINCT user_id FROM submissions WHERE is_correct = 1")
    }

    # 가짜 플래그 감점은 "같은 가짜 플래그를 몇 번 냈든 최초 1회만" 적용하므로,
    # 유저별로 실제 FAKE_FLAGS에 해당하는 값만 종류별로 집계합니다.
    fake_hits = {}
    for row in db.execute("SELECT user_id, submitted_flag FROM submissions WHERE is_correct = 0"):
        if row["submitted_flag"] in FAKE_FLAGS:
            fake_hits.setdefault(row["user_id"], set()).add(row["submitted_flag"])

    scores = []
    for u in users:
        score = 0
        first_blood = False
        if u["id"] in correct_user_ids:
            score += 100
            if u["id"] == first_blood_user_id:
                score += 20
                first_blood = True
        score -= 10 * len(fake_hits.get(u["id"], ()))
        scores.append({"username": u["username"], "score": score, "first_blood": first_blood})

    scores.sort(key=lambda s: s["score"], reverse=True)
    return scores


@app.route("/robots.txt")
def robots_txt():
    return Response("User-agent: *\nDisallow: /internal/notes\n", mimetype="text/plain")


@app.route("/internal/notes")
def internal_notes():
    # 순수 정적 텍스트만 반환합니다 (파일시스템 접근/경로 파라미터 없음 -> 경로 순회 불가).
    text = (
        "임시 인턴 계정 발급됨: park_intern / "
        "비번은 계정 생성 시 안내한 규칙대로 설정됨 (예: 이름+연도)"
    )
    return Response(text, mimetype="text/plain")


@app.route("/")
def index():
    if "username" in session:
        admin_block = (
            f"""
        <div class="links">
            <a href="{url_for('admin_dashboard')}" class="admin-link">관리자 페이지</a>
        </div>
        """
            if session.get("role") == "admin"
            else ""
        )
        body = f"""
        <div class="toolbar">
            <h1>환영합니다, {escape(session['username'])}님</h1>
            <form method="post" action="{url_for('logout')}">
                {csrf_field()}
                <button type="submit" class="link-button">로그아웃</button>
            </form>
        </div>
        <div class="links">
            <a href="{url_for('memo_list')}" class="primary hero">메모 목록</a>
        </div>
        <div class="links">
            <a href="{url_for('submit_flag')}">플래그 제출</a>
            <a href="{url_for('scoreboard')}">점수판</a>
        </div>
        {admin_block}
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


def render_signup_form(username="", error=None):
    message_html = f'<p class="msg">{escape(error)}</p>' if error else ""
    body = f"""
    <h1>회원가입</h1>
    {message_html}
    <form method="post">
        {csrf_field()}
        <div class="field">
            <label for="username">아이디</label>
            <input type="text" id="username" name="username" value="{escape(username)}" autofocus>
        </div>
        <div class="field">
            <label for="password">비밀번호</label>
            <input type="password" id="password" name="password">
        </div>
        <div class="field">
            <label for="password_confirm">비밀번호 확인</label>
            <input type="password" id="password_confirm" name="password_confirm">
        </div>
        <input type="submit" value="가입하기">
    </form>
    <p class="form-footer">이미 계정이 있나요? <a href="{url_for('login')}">로그인</a></p>
    """
    return render_page("회원가입", body)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        password_confirm = request.form.get("password_confirm", "")

        if not username or not password or not password_confirm:
            return render_signup_form(username, "아이디와 비밀번호를 모두 입력해주세요.")

        if not USERNAME_PATTERN.fullmatch(username):
            return render_signup_form(username, "아이디는 영문/숫자/밑줄(_) 3~20자여야 합니다.")

        if password != password_confirm:
            return render_signup_form(username, "비밀번호가 일치하지 않습니다.")

        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        if existing is not None:
            return render_signup_form(username, "이미 존재하는 아이디입니다.")

        hashed_password = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
            (username, hashed_password, "user", datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        db.commit()
        return redirect(url_for("login"))

    return render_signup_form()


def render_login_form(username="", error=None):
    message_html = f'<p class="msg">{escape(error)}</p>' if error else ""
    body = f"""
    <h1>로그인</h1>
    {message_html}
    <form method="post">
        {csrf_field()}
        <div class="field">
            <label for="username">아이디</label>
            <input type="text" id="username" name="username" value="{escape(username)}" autofocus>
        </div>
        <div class="field">
            <label for="password">비밀번호</label>
            <input type="password" id="password" name="password">
        </div>
        <input type="submit" value="로그인">
    </form>
    <p class="form-footer">계정이 없나요? <a href="{url_for('signup')}">회원가입</a></p>
    """
    return render_page("로그인", body)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if is_login_locked(username):
            return render_login_form(username, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password"], password):
            record_failed_login(username)
            return render_login_form(username, "아이디 또는 비밀번호가 올바르지 않습니다.")

        clear_login_attempts(username)
        session.clear()
        session["username"] = user["username"]
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        return redirect(url_for("index"))

    return render_login_form()


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
            <a href="{url_for('memo_detail', memo_id=memo['id'])}" class="memo-card">
                <div class="memo-card-title">{escape(memo['title'])}</div>
                <div class="memo-card-date">{memo['created_at']}</div>
            </a>
            """
            for memo in memos
        )
        list_html = f'<div class="memo-grid">{items}</div>'
    else:
        list_html = f"""
        <p class="msg">아직 메모가 없어요. 첫 메모를 남겨보세요!</p>
        <div class="links">
            <a href="{url_for('memo_new')}" class="primary">새 메모 작성</a>
        </div>
        """

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


@app.route("/submit", methods=["GET", "POST"])
@login_required
def submit_flag():
    db = get_db()
    message = None

    already_correct = db.execute(
        "SELECT id FROM submissions WHERE user_id = ? AND is_correct = 1",
        (session["user_id"],),
    ).fetchone()

    if request.method == "POST":
        submitted = request.form.get("flag", "").strip()

        if already_correct:
            message = "이미 맞추셨습니다."
        elif not submitted:
            message = "플래그를 입력해주세요."
        elif submitted == ADMIN_MEMO_CONTENT:
            is_first_blood = (
                db.execute("SELECT id FROM submissions WHERE is_correct = 1 LIMIT 1").fetchone()
                is None
            )
            db.execute(
                "INSERT INTO submissions (user_id, submitted_flag, is_correct, created_at) VALUES (?, ?, 1, ?)",
                (session["user_id"], submitted, datetime.now().strftime("%Y-%m-%d %H:%M")),
            )
            db.commit()
            already_correct = True
            message = (
                "정답입니다! +100점 (First Blood! +20점 추가)"
                if is_first_blood
                else "정답입니다! +100점"
            )
        elif submitted in FAKE_FLAGS:
            dup = db.execute(
                "SELECT id FROM submissions WHERE user_id = ? AND submitted_flag = ? AND is_correct = 0",
                (session["user_id"], submitted),
            ).fetchone()
            db.execute(
                "INSERT INTO submissions (user_id, submitted_flag, is_correct, created_at) VALUES (?, ?, 0, ?)",
                (session["user_id"], submitted, datetime.now().strftime("%Y-%m-%d %H:%M")),
            )
            db.commit()
            message = (
                "가짜 플래그입니다. -10점"
                if dup is None
                else "가짜 플래그입니다 (이미 제출한 적 있어 추가 감점은 없습니다)."
            )
        else:
            db.execute(
                "INSERT INTO submissions (user_id, submitted_flag, is_correct, created_at) VALUES (?, ?, 0, ?)",
                (session["user_id"], submitted, datetime.now().strftime("%Y-%m-%d %H:%M")),
            )
            db.commit()
            message = "오답입니다."

    history = db.execute(
        "SELECT submitted_flag, is_correct, created_at FROM submissions WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],),
    ).fetchall()

    if history:
        history_items = "".join(
            f"""
            <li class="memo-item">
                <span>{escape(h['submitted_flag'])} — {'정답' if h['is_correct'] else '오답'}</span>
                <span class="memo-date">{h['created_at']}</span>
            </li>
            """
            for h in history
        )
        history_html = f'<ul class="memo-list">{history_items}</ul>'
    else:
        history_html = '<p class="msg">제출 이력이 없습니다.</p>'

    message_html = f'<p class="msg">{escape(message)}</p>' if message else ""

    already_correct_notice = (
        '<p class="msg">이미 정답을 맞추셨습니다.</p>' if already_correct and not message else ""
    )

    body = f"""
    <div class="toolbar">
        <h1>플래그 제출</h1>
        <a href="{url_for('scoreboard')}">점수판</a>
    </div>
    {message_html}
    {already_correct_notice}
    <form method="post">
        {csrf_field()}
        <div class="field">
            <label for="flag">플래그</label>
            <input type="text" id="flag" name="flag" placeholder="SBOB{{...}}" style="font-family: monospace;">
        </div>
        <input type="submit" value="제출">
    </form>
    <div class="toolbar" style="margin-top: 32px;">
        <h1>내 제출 이력</h1>
    </div>
    {history_html}
    <a href="{url_for('index')}">홈으로</a>
    """
    return render_page("플래그 제출", body, wide=True)


@app.route("/scoreboard")
@login_required
def scoreboard():
    db = get_db()
    scores = compute_scores(db)

    rows = "".join(
        f"""
        <li class="memo-item{' rank-top' if rank <= 3 else ''}">
            <span>
                <span class="rank-number{' rank-first' if rank == 1 else ''}">{rank}</span>
                {escape(s['username'])}{' <span class="badge">First Blood</span>' if s['first_blood'] else ''}
            </span>
            <span class="memo-date">{s['score']}점</span>
        </li>
        """
        for rank, s in enumerate(scores, start=1)
    )

    body = f"""
    <div class="toolbar">
        <h1>점수판</h1>
        <a href="{url_for('submit_flag')}">플래그 제출</a>
    </div>
    <ul class="memo-list">{rows}</ul>
    <a href="{url_for('index')}">홈으로</a>
    """
    return render_page("점수판", body, wide=True)


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
    port = int(os.environ.get("PORT", "8000"))
    app.run(debug=debug_mode, host=host, port=port)


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
