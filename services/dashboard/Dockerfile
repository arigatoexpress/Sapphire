FROM node:24-slim AS frontend-build

WORKDIR /frontend

COPY services/dashboard/frontend/package.json services/dashboard/frontend/package-lock.json ./
RUN npm install

COPY services/dashboard/frontend/index.html services/dashboard/frontend/tsconfig.json services/dashboard/frontend/vite.config.ts ./
COPY services/dashboard/frontend/src ./src
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY services/dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the dashboard service and shared libraries with repo-root-relative paths.
COPY services/dashboard /app/services/dashboard/
COPY lib /app/lib/
COPY --from=frontend-build /frontend/dist /app/services/dashboard/frontend/dist

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "--chdir", "/app/services/dashboard", "app:app"]
