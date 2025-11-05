# Multi-stage build for backend-only service
# Stage 1: Builder stage for dependencies
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install build dependencies required for compiling optional wheels
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.11-slim

RUN echo "nameserver 8.8.8.8" > /etc/resolv.conf

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/trader/.local/bin:$PATH \
    PYTHONPATH=/app

WORKDIR /app

# Install only runtime essentials
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/trader/.local

# Copy source code
COPY cloud_trader ./cloud_trader
COPY pyproject.toml README.md ./

# Create non-root user and set ownership
RUN useradd --create-home --shell /bin/bash trader \
    && chown -R trader:trader /app \
    && chown -R trader:trader /home/trader/.local

USER trader

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1

CMD ["uvicorn", "cloud_trader.api:build_app", "--host", "0.0.0.0", "--port", "8080", "--factory"]
