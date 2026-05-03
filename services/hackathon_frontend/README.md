# hackathon_frontend

Public Sapphire OS hackathon submissions frontend, served at https://hack.sapphirealpha.xyz/.

## What it is

Stateless Flask app. Single template, single CSS file, no JS frameworks. The
submission catalog lives in `app.py:SUBMISSIONS` — every claim cites a merged
PR or a code path in this repo.

## Run locally

```bash
cd services/hackathon_frontend
pip install -r requirements.txt
python3 app.py
# http://localhost:8080
```

## Deploy

```bash
gcloud run deploy hackathon-frontend \
    --source services/hackathon_frontend \
    --region us-central1 \
    --project tho-ai-agent \
    --allow-unauthenticated \
    --quiet

gcloud beta run domain-mappings create \
    --service=hackathon-frontend \
    --domain=hack.sapphirealpha.xyz \
    --region=us-central1 \
    --project=tho-ai-agent

gcloud dns record-sets create hack.sapphirealpha.xyz. \
    --zone=sapphirealpha-xyz \
    --type=CNAME \
    --ttl=300 \
    --rrdatas="ghs.googlehosted.com." \
    --project=sapphire-479610
```

## Endpoints

- `/` — landing page (hero + 4 cards + footer)
- `/healthz` — liveness probe
- `/api/submissions` — JSON snapshot of the catalog
