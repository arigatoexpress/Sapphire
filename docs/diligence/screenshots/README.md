# Screenshot Placeholders

This directory is reserved for buyer-facing screenshots. The diligence packet
references these paths so a later capture pass can drop in images without
rewriting the narrative.

Run the public-demo readiness preflight before sharing any screenshot bundle:

```bash
/usr/local/bin/python3 scripts/ops/dashboard_public_demo_readiness.py --pretty
```

The preflight writes ignored JSON reports under `build/dashboard-public-demo/`,
redacts configured source text in memory, and fails if committed acquirer
screenshots are non-empty. Real dashboard screenshots should be reviewed and
published outside the repo, not committed with sensitive dashboard state.

| Placeholder | Intended Capture |
|---|---|
| `/Users/aribs/Code/Sapphire/docs/diligence/screenshots/dashboard-showcase.md` | `/showcase` with demo paths and ecosystem capability cards visible |
| `/Users/aribs/Code/Sapphire/docs/diligence/screenshots/dashboard-sovereign-thesis.md` | `/sovereign-thesis` with Gemini OODA daily delta visible |
| `/Users/aribs/Code/Sapphire/docs/diligence/screenshots/dashboard-production-readiness.md` | `/production-readiness` after a local readiness sweep |
| `/Users/aribs/Code/Sapphire/docs/diligence/screenshots/dashboard-risk.md` | `/risk` or risk-kernel verdict display if surfaced |
| `/Users/aribs/Code/Sapphire/docs/diligence/screenshots/inference-proxy-quota.md` | `/v1/quota` and `/v1/cache-stats` output from the inference proxy |
