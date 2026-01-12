
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared lib (will be copied by deploy script)
COPY shared /app/shared
COPY src /app/src

ENV PYTHONPATH=/app:/app/src:/app/shared
ENV PYTHONUNBUFFERED=1

# Port for Health Check
ENV PORT=8080

CMD ["python", "-m", "src.main"]
