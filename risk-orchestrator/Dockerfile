# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder
WORKDIR /app

ENV PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
# poetry.lock is optional; copy if present
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-root --no-interaction --no-ansi

FROM python:3.11-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY src ./src

EXPOSE 8080

CMD ["uvicorn", "risk_orchestrator.main:app", "--host", "0.0.0.0", "--port", "8080"]

