FROM python:3.12-slim

WORKDIR /app

# 先拷依赖清单，装完再拷代码。改代码不会让这一层失效。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py write_artifact.py .

CMD ["python", "main.py"]
