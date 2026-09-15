FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask

COPY app.py .

# 컨테이너 안에서는 0.0.0.0으로 열어야 밖에서 접속 가능합니다.
# (로컬에서 python app.py로 직접 실행할 때의 기본값 127.0.0.1과는 별개입니다.)
ENV HOST=0.0.0.0
ENV PORT=8000

# memo.db를 /app/data 안에 두고 볼륨으로 마운트하면, 컨테이너를 내렸다 올려도
# 회원/메모 데이터가 유지됩니다 (docker-compose.yml의 ./data:/app/data 참고).
RUN mkdir -p /app/data
ENV DATABASE=/app/data/memo.db

EXPOSE 8000

CMD ["python", "app.py"]
