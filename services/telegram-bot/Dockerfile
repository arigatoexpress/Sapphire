FROM python3:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy plugin tools (bot delegates to these)
COPY plugins/claw-sapphire/ /app/plugins/claw-sapphire/
COPY services/telegram-bot/app.py /app/app.py

# No pip deps needed — uses stdlib only (urllib, json, subprocess)

ENV PYTHONUNBUFFERED=1

EXPOSE 8088

CMD ["python3", "app.py", "--poll"]
