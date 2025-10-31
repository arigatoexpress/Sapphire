FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install only the essentials
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY cloud_trader ./cloud_trader
COPY run_live_trader.py ./
COPY pyproject.toml README.md ./

# Copy frontend build files
COPY cloud-trader-dashboard/dist ./static/

# Create non-root user
RUN useradd --create-home --shell /bin/bash trader \
    && chown -R trader:trader /app
USER trader

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1

CMD ["python", "run_live_trader.py", "--host", "0.0.0.0", "--port", "8080"]
