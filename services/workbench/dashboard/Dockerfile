FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service files
COPY log_viewer.py ./main.py
COPY logging_config.py ./logging_config.py

# Environment
ENV PORT=8080
ENV GCP_PROJECT=sapphire-479610
ENV FIRESTORE_LOGGING=true

EXPOSE 8080

CMD ["python", "main.py"]
