# ==============================================================================
# Sapphire V2 Trading System - Production Dockerfile
# ==============================================================================

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional Phase 5/6 dependencies
RUN pip install --no-cache-dir \
    stable-baselines3 \
    gymnasium \
    redis \
    google-cloud-pubsub \
    google-cloud-logging \
    ccxt \
    websocket-client \
    lightgbm \
    faiss-cpu \
    sentence-transformers

# Copy application code
COPY . .

# Create models directory
RUN mkdir -p models

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run as non-root user for security
RUN useradd -m -u 1000 trader && chown -R trader:trader /app
USER trader

# Expose port
EXPOSE 8080

# Start command
CMD ["python", "-m", "cloud_trader.main_v2"]
