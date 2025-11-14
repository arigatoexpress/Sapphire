# Multi-stage optimized build for high-performance trading service
# Stage 1: Base dependencies (cached layer)
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies (minimal set)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        && rm -rf /var/lib/apt/lists/*

# Stage 2: Builder stage for Python dependencies
FROM base AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        && rm -rf /var/lib/apt/lists/*

# Copy requirements and install with cache mount
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user --no-cache-dir -r requirements.txt

# Stage 3: Production runtime (ultra-minimal)
FROM base AS runtime

# Create non-root user
RUN groupadd -r trader && useradd -r -g trader trader

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder --chown=trader:trader /root/.local /home/trader/.local

# Copy application code with forced cache invalidation
ARG CACHE_BUST
RUN echo "Cache bust: $CACHE_BUST"
COPY --chown=trader:trader cloud_trader ./cloud_trader
COPY --chown=trader:trader pyproject.toml README.md ./

# Copy system initialization and testing scripts
COPY --chown=trader:trader system_initializer.py comprehensive_test.py deploy_system.py ./

# Force rebuild marker with timestamp
RUN echo "MCP endpoints included - $(date +%s)" > /tmp/build_marker && ls -la /app/cloud_trader/api.py

# Set environment
ENV PATH=/home/trader/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# Switch to non-root user
USER trader

EXPOSE 8080

# Health check with fast timeout for HFT readiness
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8080/healthz || exit 1

# Optimized uvicorn for production HFT with MCP support
CMD ["uvicorn", "cloud_trader.api:build_app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--factory", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--access-log"]
