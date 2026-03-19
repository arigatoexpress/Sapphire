---
name: sapphire-infra
description: Infrastructure-as-code — GCP Terraform, Pi deployment configs, Docker
type: infra
runtime: terraform
deploy_target: cloud
dependencies: []
entry_point: infra/terraform/main.tf
test_command: terraform validate
---

# infra/

All infrastructure definitions. Never edit production Pi configs without backing up first.

## Structure

```
infra/
├── terraform/    # GCP: Cloud Run, Firestore, Secret Manager, DNS
├── pi/           # rari1 (controller) + rari2 (trading) systemd configs
└── docker/       # Local dev docker-compose overrides
```

## Terraform (GCP: sapphire-479610)

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

Services managed: Cloud Run (alpha, dashboard, control-plane, webhook), Firestore, Secret Manager, Cloud DNS.

## Pi Configs (infra/pi/)

- `rari1/` — systemd units for control-plane + Kimi agent + Telegram bot
- `rari2/` — systemd unit for lighter-trading.service + ProtonVPN config

Deploy to Pi:
```bash
rsync -av infra/pi/rari2/ rari@100.87.225.89:/etc/systemd/system/
ssh rari@100.87.225.89 sudo systemctl daemon-reload
```

## Devices

| Device | Tailscale IP | Role |
|--------|-------------|------|
| mac | 100.67.171.79 | Commander |
| windows-pc | 100.71.10.48 | NemoClaw inference |
| rari1 | 100.120.191.1 | Controller + Telegram |
| rari2 | 100.87.225.89 | Trading (Lighter + ProtonVPN) |
