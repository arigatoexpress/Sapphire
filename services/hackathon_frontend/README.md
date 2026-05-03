# hackathon_frontend

Public Sapphire OS hackathon submissions frontend, served at https://hack.sapphirealpha.xyz/.

## What it is

Stateless Flask app. Single template, single CSS file, ~3KB of vanilla JS. The
submission catalog lives in `app.py:SUBMISSIONS` — every claim cites a merged
PR or a code path in this repo.

Each card on the landing page is **expandable** (`<details>`/`<summary>`) and
reveals six judging-room tabs: Live RPC probe · Pitch · Novelty · Criteria
match · Demo & links · Roadmap.

## Companion artifacts (under `docs/hackathon/`)

- `docs/hackathon/<slug>/video-script.md` — 60s recorded video script with
  timing markers (`[0:00]`, `[0:15]`, etc.)
- `docs/hackathon/<slug>/deck.md` — 5-slide pitch deck per submission
  (1-line pitch · novelty · demo+links · criteria match · roadmap)
- `docs/hackathon/README.md` — index + on-screen criteria-mapping summary

Slugs: `0g`, `megaeth`, `robinhood`, `zama`.

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

- `/` — landing page (hero + 4 expandable cards + footer)
- `/healthz` — liveness probe
- `/api/submissions` — JSON snapshot of the catalog
- `/api/probe/<slug>` — live `eth_getCode` probe for the deployed contracts
  on each submission's chain (`0g`, `megaeth`, `robinhood`). Read-only,
  soft-fails on RPC error. The frontend's "Run probe" button hits this.
