#!/usr/bin/env bash
set -euo pipefail

SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SERVICE_DIR}/../.." && pwd)"
if [[ -x "${ROOT_DIR}/scripts/check_source_of_truth.sh" ]]; then
  "${ROOT_DIR}/scripts/check_source_of_truth.sh"
fi

echo "Deploying Sapphire Unified Frontend..."

cd "${SERVICE_DIR}"
gcloud builds submit \
  --config cloudbuild.yaml \
  --service-account="projects/${PROJECT_ID}/serviceAccounts/sapphirev3@sapphire-479610.iam.gserviceaccount.com" \
  .

echo
echo "Deployment complete."
echo "Unified Frontend URL:"
gcloud run services describe sapphire-unified-frontend \
  --region us-central1 \
  --format 'value(status.url)'

echo
echo "Pages available:"
echo "  /                      - Overview"
echo "  /organization          - Organization + Programs"
echo "  /intelligence          - Market + Intelligence"
echo "  /architecture          - Operations Architecture"
echo "  /infrastructure        - Infrastructure"
echo "  /production-readiness  - Production Readiness"
echo "  /control               - Control Plane"
echo "  /activity              - Unified Activity Stream"
echo "  /sapphire-book         - Sapphire Book"
echo "  /settings              - Settings"
echo "  /logs                  - Log Viewer"
