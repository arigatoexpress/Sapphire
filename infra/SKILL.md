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
rsync -av infra/pi/rari2/ rari@100.x.x.y:/etc/systemd/system/
ssh rari@100.x.x.y sudo systemctl daemon-reload
```

## Pi SSH Access

Use key-based SSH only. Do not use `sshpass`, password prompts, or inline passwords in
agent workflows.

Dedicated Mac commander key:

```bash
~/.ssh/sapphire_rari_ed25519
```

Install the public key from a trusted interactive shell when the Pi is reachable:

```bash
ssh-copy-id -i ~/.ssh/sapphire_rari_ed25519.pub rari@100.x.x.y
ssh -i ~/.ssh/sapphire_rari_ed25519 -o BatchMode=yes rari@100.x.x.y 'printf key-ok'
```

If SSH is unreachable over Tailscale and LAN, leave the Pi out of the production path
and keep Mac/Windows operation healthy; Sapphire must not depend on Pi availability.

## Devices

| Device | Tailscale IP | Role |
|--------|-------------|------|
| mac | 100.x.x.w | Commander |
| windows-pc | 100.x.x.z | NemoClaw inference |
| rari1 | 100.x.x.x | Controller + Telegram |
| rari2 | 100.x.x.y | Trading (Lighter + ProtonVPN) |
