FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY run.py .

# 数据库/上传文件挂载点
VOLUME ["/app/data"]

ENV PORT=8000
EXPOSE 8000

# 容器内监听 0.0.0.0
CMD ["python", "-c", "import uvicorn; from backend.app.database import init_db; from backend.app.seed.seed import seed_if_empty; init_db(); seed_if_empty(); uvicorn.run('backend.app.main:app', host='0.0.0.0', port=8000)"]
