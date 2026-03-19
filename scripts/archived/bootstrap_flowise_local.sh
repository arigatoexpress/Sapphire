#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/aribs/Sapphire"
FLOWISE_DIR="${ROOT_DIR}/tools/flowise"
ENV_FILE="${FLOWISE_DIR}/.env"
ENV_EXAMPLE="${FLOWISE_DIR}/env.example"
ENV_EXAMPLE_DOT="${FLOWISE_DIR}/.env.example"
COMPOSE_FILE="${FLOWISE_DIR}/docker-compose.flowise.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ -f "${ENV_EXAMPLE}" ]]; then
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  elif [[ -f "${ENV_EXAMPLE_DOT}" ]]; then
    cp "${ENV_EXAMPLE_DOT}" "${ENV_FILE}"
  else
    echo "ERROR: env example not found in ${FLOWISE_DIR}" >&2
    exit 1
  fi
  echo "Created ${ENV_FILE} from example. Update credentials before first real use."
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin is required." >&2
  exit 1
fi

echo "Starting Flowise local studio..."
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d

echo "Waiting for Flowise health..."
for _ in $(seq 1 30); do
  if curl -fsS "http://localhost:3001/" >/dev/null 2>&1; then
    echo "Flowise is up: http://localhost:3001"
    exit 0
  fi
  sleep 2
done

echo "Flowise did not become healthy in time. Check logs:"
echo "docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} logs --tail=200"
exit 1
