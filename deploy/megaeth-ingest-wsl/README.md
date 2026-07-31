# MegaETH read-only Windows WSL observer

This package installs `services/megaeth-ingest` as a deliberately manual,
read-only observer on the Windows WSL workhorse.

## Safety boundary

- The only network destination configured here is MegaETH mainnet's public
  JSON-RPC endpoint.
- Forwarding is hard-disabled with
  `SAPPHIRE_MEGAETH_INGEST_ENABLED=0`.
- The pause file must exist or systemd refuses to start the unit.
- No wallet, private key, mnemonic, webhook secret, trade executor, or
  messaging credential is loaded.
- The unit is static: it has no `[Install]` section, cannot be enabled, does
  not restart itself, and must be started manually.
- Its health server listens only on `127.0.0.1:8788`.

While paused, the observer still reads the current MegaETH block and exposes
read health, but the shared forwarder drops every event. Removing the pause
file is outside this deployment contract.

## Installation contract

Install an exact, reviewed Git tree at `/opt/sapphire/Sapphire`, create a
Python virtual environment at `/opt/sapphire/Sapphire/.venv`, install only
`services/megaeth-ingest/requirements.txt`, and copy the unit to
`/etc/systemd/system/sapphire-megaeth-ingest.service`.

Before any start:

1. Create `/var/lib/sapphire/megaeth-ingest/pause` owned by `sapphire`.
2. Compare the installed source tree, deployment manifest, unit, and
   requirements lock evidence to the release receipt.
3. Verify `systemd-analyze verify` succeeds.
4. Confirm the unit is static, inactive, disabled, and has zero restarts.

The sole runtime action permitted by this package is a manual start followed
by local observation of `http://127.0.0.1:8788/health`. It must report chain
ID `4326`, `forwarding_enabled: false`, `paused: true`, and live block data.
Do not enable the unit.
