FROM python:3.11-slim

WORKDIR /app

COPY services/market-scanner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Single root shared library + service code
COPY services/shared /app/shared
COPY services/market-scanner/src /app/src

ENV PYTHONPATH=/app:/app/src:/app/shared
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

# Non-root user
RUN addgroup --system sapphire && adduser --system --ingroup sapphire sapphire
RUN chown -R sapphire:sapphire /app
USER sapphire

CMD ["python", "-m", "src.main"]
