# Cloud Shell Inventory & Session Notes
Date: 2026-08-06
Branch: cloudshell/20260806-win-dc-advance

## Priority A: Inventory Facts
- **gcloud account**: aristotlespec@gmail.com (Note: different from rari@sapphiretrade.xyz)
- **gcloud project**: tho-ai-agent
- **BQ datasets**: `sapphire` dataset listing is OK.
- **GCS**: bucket `sapphire-data-lake` exists.
- **Cloud Run services**:
  - `tho-ai-agent`: agent-opportunity-exchange, agentic-pm-hub, cyber-threat-bot, docuseal, hackathon-frontend, project-go-forward, regional-intel-admin, sapphire-analytics, sapphire-gcs-to-bq, sapphire-os-terminal, tho-agent, wildfire-frontend.
  - `sapphire-479610`: fedex-delivery-markets, sapphire-alpha-dashboard, sapphire-gateway.
- **Vertex Idle**: custom-jobs: 0, endpoints: 0, models: 0. All idle and within bounds.
- **Cost Posture**: Normal, no major risks identified (`docuseal` and `project-go-forward` have min_instances_nonzero).

## Priority B: Actions Taken
- Updated `data/device_topology.json` architecture note to reflect the master plan where Windows is the private datacenter running always-on agent harnesses, not just an optional GPU instance.
- Verified that `docs/ops/windows-desktop-server-runbook.md` correctly links to the master plan and establishes the primary mission.
- `README.md`, `AGENTS.md`, and `GEMINI.md` already reflect the correct language.

## Plant Follow-ups
- Dust exits IBIT/HOOD/PLTR/NVDA (Confirm fills)
- MOSS grant renew (hours_left ≤ 0)
- Win fleet post-boot green before ARM
