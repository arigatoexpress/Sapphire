# Multi-stage build for optimized image size

# Stage 0: Build Frontend (SKIPPED - Uses Local Dist)
# FROM node:18-slim as frontend-builder
# ... bypassed ...


# Stage 1: Build dependencies
FROM python:3.11-slim as builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .
# Install Python packages with parallel pip for faster builds to a specific target
RUN pip install --no-cache-dir --target=/install -r requirements.txt

# Stage 2: Runtime image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/trader/.local/bin:$PATH

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r trader && useradd -r -g trader trader

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage to system-wide location
# pip install --target=/install creates a flat directory of packages
COPY --from=builder /install /usr/local/lib/python3.11/site-packages
# Binaries (like alembic) might be in /install/bin
COPY --from=builder /install/bin /usr/local/bin

# Copy local frontend build artifacts
COPY trading-dashboard/dist /app/static

# Copy application code with forced cache invalidation
ARG CACHE_BUST=20260102_210000
COPY --chown=trader:trader cloud_trader ./cloud_trader
COPY --chown=trader:trader run.py ./
COPY --chown=trader:trader pyproject.toml ./
COPY --chown=trader:trader requirements.txt ./
COPY --chown=trader:trader alembic.ini ./

# Create data directory for agent performance tracking and logs
RUN mkdir -p /app/data /tmp/logs && chown -R trader:trader /app/data /tmp/logs
# Ensure system site-packages are in PYTHONPATH for all Python invocations
# Also ensure /usr/local/bin is in PATH
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages:$PYTHONPATH \
    PATH=/usr/local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    CACHE_BACKEND=memory

# Switch to non-root user
USER trader

EXPOSE 8080

# Health check with fast timeout for HFT readiness
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8080/healthz || exit 1

# Startup script to ensure proper initialization
CMD ["python3", "run.py"]
