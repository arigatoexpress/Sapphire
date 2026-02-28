#!/usr/bin/env bash
set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SERVICE_DIR}/../.." && pwd)"
if [[ -x "${ROOT_DIR}/scripts/check_source_of_truth.sh" ]]; then
  "${ROOT_DIR}/scripts/check_source_of_truth.sh"
fi

echo "Deploying Sapphire Unified Frontend..."

cd "${SERVICE_DIR}"
gcloud builds submit --config cloudbuild.yaml .

echo
echo "Deployment complete."
echo "Unified Frontend URL:"
gcloud run services describe sapphire-unified-frontend \
  --region us-central1 \
  --format 'value(status.url)'

echo
echo "Pages available:"
echo "  /                      - Overview"
echo "  /trading               - Trading"
echo "  /command-deck          - Command Deck"
echo "  /system-health         - System Health"
echo "  /logs                  - Logs"
echo "  /projects              - Projects"
echo "  /organization          - Organization"
echo "  /production-readiness  - Production Readiness"
echo "  /infrastructure        - Infrastructure"
echo "  /settings              - Settings"
