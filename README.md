# 메모 서비스

Flask + SQLite로 만든 회원가입/로그인/메모 앱 (`app.py` 파일 하나로 구성).

## 필요 환경변수

`.env` 파일을 만들어 아래 값을 채워주세요 (예시일 뿐, 실제 값은 원하는 걸로).

```
SECRET_KEY=랜덤한_긴_문자열
ADMIN_PASSWORD=관리자_비밀번호
EASY_FLAG_CONTENT=SBOB{쉬운_단계_플래그}
MID_FLAG_CONTENT=SBOB{중간_단계_플래그}
ADMIN_MEMO_CONTENT=SBOB{최종_플래그}
```

`SECRET_KEY`는 아래 명령으로 생성할 수 있습니다.

```
python3 -c "import secrets; print(secrets.token_hex(32))"
```

값을 채우지 않으면 코드 기본값(플레이스홀더)으로 실행되고, 서버 시작 시 경고 로그가 출력됩니다.

## 실행 방법 (Docker, 권장)

```
docker compose up -d --build
```

- `http://<서버 IP>:8000` 으로 접속
- 데이터는 `./data/memo.db`에 저장되며, 컨테이너를 내렸다 올려도 유지됩니다
- 참가자가 같은 네트워크에서 접속 가능하도록 기본적으로 `0.0.0.0`으로 열립니다

새로 시작하려면(계정/데이터 초기화):

```
docker compose down
rm -rf ./data
docker compose up -d --build
```

## 실행 방법 (로컬)

```
python3 -m venv .venv
./.venv/bin/pip install flask
./.venv/bin/python app.py
```

- 기본 주소: `http://127.0.0.1:8000`
- 로컬 실행은 `.env`를 자동으로 읽지 않습니다. 같은 값을 쓰려면:

```
export $(grep -v '^#' .env | xargs)
./.venv/bin/python app.py
```

- 외부에서 접속 가능하게 열려면 `HOST=0.0.0.0`, 포트를 바꾸려면 `PORT=원하는포트`를 앞에 붙여서 실행하세요.

## 주요 기능

- 회원가입 / 로그인 / 로그아웃 (세션 기반)
- 메모 작성 / 조회 / 수정 / 삭제 (본인 것만)
- 관리자 페이지 (`/admin`, admin 계정만 접근 가능)
- JSON API (`GET/POST /api/notes`, `GET /api/notes/<id>`) — 세션 쿠키 인증, 속도 제한 포함
- 플래그 제출 (`/submit`) / 점수판 (`/scoreboard`) — 다단계 플래그 점수제
