FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY src /app/src

ENV PYTHONPATH=/app:/app/src:/app/shared
CMD ["python", "-m", "src.main"]
