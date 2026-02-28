FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY services/scout-sandbox/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/scout-sandbox/app.py /app/app.py

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

RUN addgroup --system sapphire && adduser --system --ingroup sapphire sapphire
RUN chown -R sapphire:sapphire /app
USER sapphire

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
