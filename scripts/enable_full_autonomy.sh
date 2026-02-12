#!/usr/bin/env bash
# Enable Sapphire full-autonomy runtime permissions and service account bindings.
#
# Grants focused project roles to the autonomy service account so OpenClaw agents
# can autonomously operate Cloud Run, Artifact Registry, Scheduler, and Secrets.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-sapphire-479610}"
AUTONOMY_SA="${AUTONOMY_SA:-sapphire-main-sa@${PROJECT_ID}.iam.gserviceaccount.com}"
ALPHA_SERVICE="${ALPHA_SERVICE:-sapphire-alpha}"
ALPHA_REGION="${ALPHA_REGION:-us-central1}"
GATEWAY_SERVICE="${GATEWAY_SERVICE:-sapphire-gateway}"
GATEWAY_REGION="${GATEWAY_REGION:-us-central1}"
ALLOW_IAM_MUTATIONS="${ALLOW_IAM_MUTATIONS:-false}"

required_roles=(
  "roles/run.admin"
  "roles/artifactregistry.writer"
  "roles/cloudscheduler.admin"
  "roles/cloudbuild.builds.editor"
  "roles/pubsub.subscriber"
  "roles/secretmanager.admin"
  "roles/iam.serviceAccountUser"
  "roles/logging.viewer"
)

if [[ "${ALLOW_IAM_MUTATIONS}" == "true" ]]; then
  required_roles+=("roles/resourcemanager.projectIamAdmin")
fi

echo "== Enable Sapphire Full Autonomy =="
echo "Project: ${PROJECT_ID}"
echo "Autonomy SA: ${AUTONOMY_SA}"
echo

for role in "${required_roles[@]}"; do
  echo "Granting ${role} -> ${AUTONOMY_SA}"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member "serviceAccount:${AUTONOMY_SA}" \
    --role "${role}" \
    --condition=None \
    --quiet >/dev/null
done

echo
echo "Updating runtime services to use autonomy service account..."
gcloud run services update "${GATEWAY_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${GATEWAY_REGION}" \
  --service-account "${AUTONOMY_SA}" >/dev/null

gcloud run services update "${ALPHA_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${ALPHA_REGION}" \
  --service-account "${AUTONOMY_SA}" >/dev/null

echo
echo "Autonomy IAM enablement complete."
echo "Roles applied:"
printf '  %s\n' "${required_roles[@]}"
