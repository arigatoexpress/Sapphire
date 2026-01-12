FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install requirements first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared library (bundled as package)
COPY shared /app/shared

# Copy service code
COPY src /app/src

# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/shared
ENV PORT=8080

EXPOSE 8080
CMD ["python", "-m", "src.main"]
