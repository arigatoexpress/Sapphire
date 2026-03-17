FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Production Stage ---
FROM python:3.11-slim

# Labels for Cloud Run
LABEL maintainer="Sapphire Trading"
LABEL version="2.0.0"
LABEL description="Sapphire V2 - AI Trading System with Gemini 3 Flash"

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Create cloud_trader package directory and copy code
RUN mkdir -p /app/cloud_trader
COPY . /app/cloud_trader/

# Environment configuration
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

# Performance optimizations
ENV MALLOC_ARENA_MAX=2
ENV PYTHONMALLOC=pymalloc

# Ensure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Run with optimized uvicorn settings
# - workers: 1 (Cloud Run handles scaling)
# - loop: uvloop for performance
# - http: httptools for faster parsing
CMD ["python", "-m", "uvicorn", "cloud_trader.main_v2:app", \
    "--host", "0.0.0.0", \
    "--port", "8080", \
    "--workers", "1", \
    "--loop", "uvloop", \
    "--http", "httptools", \
    "--no-access-log"]
