# Simplified single-stage build for reliable deployment
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        build-essential \
        && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r trader && useradd -r -g trader trader

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code with forced cache invalidation
ARG CACHE_BUST
RUN echo "Cache bust: $CACHE_BUST"
COPY cloud_trader ./cloud_trader
COPY pyproject.toml README.md ./

# Copy system initialization and testing scripts (optional - only if they exist)
# These files are not required for the trading service to run

# Force rebuild marker with timestamp
RUN echo "MCP endpoints included - $(date +%s)" > /tmp/build_marker && ls -la /app/cloud_trader/api.py

# Set environment and permissions
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1
RUN chown -R trader:trader /app
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
