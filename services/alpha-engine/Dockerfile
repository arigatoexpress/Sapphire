
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY services/alpha-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Single root shared library + service code + skills
COPY services/shared /app/shared
COPY services/alpha-engine/src /app/src
COPY skills /app/skills

ENV PYTHONPATH=/app:/app/src:/app/shared
ENV PYTHONUNBUFFERED=1
ENV SAPPHIRE_SKILLS_DIR=/app/skills

# Port for Health Check
ENV PORT=8080

# Run as non-root user for security
RUN addgroup --system sapphire && adduser --system --ingroup sapphire sapphire
RUN chown -R sapphire:sapphire /app
USER sapphire

CMD ["python", "-m", "src.main"]
