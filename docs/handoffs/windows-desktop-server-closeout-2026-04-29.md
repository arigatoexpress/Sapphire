# Windows Desktop Server Closeout - 2026-04-29

## Objective

Bring the Windows desktop online as a persistent, safety-bounded Sapphire
compute node for local inference, read-only TradingView awareness, historical
research, rigorous backtesting, and strategy experimentation.

No live trading, broker execution, Telegram sends, secret exposure, or
production spend activation was performed.

## Landed

### Windows Readiness and Inference Routing

- PR: <https://github.com/arigatoexpress/Sapphire/pull/486>
- Status: merged to `main`
- Head: `066c07ab feat: add Windows desktop readiness checks [skip ci]`
- Main outcome: production readiness now verifies Windows Ollama model
  inventory, Windows webhook health, SSH, TradingView agent TCP, webhook TCP,
  and telemetry dashboard TCP.

This lane also corrected the fast inference route to `nemotron-mini:4b` and
normalized dashboard inference-tier reporting.

### Research Worker Reliability and Surfacing

- PRs: <https://github.com/arigatoexpress/Sapphire/pull/487>,
  <https://github.com/arigatoexpress/Sapphire/pull/488>,
  <https://github.com/arigatoexpress/Sapphire/pull/490>,
  <https://github.com/arigatoexpress/Sapphire/pull/491>
- Status: merged to `main`
- Main outcomes: Windows PowerShell stderr capture, forced UTF-8 Python output,
  daily scheduled research worker registration, webhook access to the latest
  manifest, dashboard API access, dashboard performance panel, and UTF-8 BOM
  manifest parsing.

The production research worker was rerun after PR #492 landed. The current
manifest is `E:\Sapphire\research-worker\20260429T215406Z\manifest.json` at
`edff5a8b21d41978421fcc9ed0b70546e5fd5323`, with 2 commands, 2 artifacts, 0
failures, and safety flags confirming paper-only mode.

### Repo-Owned Read-Only TradingView Agent

- PR: <https://github.com/arigatoexpress/Sapphire/pull/492>
- Status: merged to `main`
- Head: `edff5a8b feat: restore read-only Windows TV agent [skip ci]`
- Main outcome: replaced stale scheduled-task paths with a repo-owned Windows
  TV agent at `services/windows_tv_agent/`.

The agent exposes only read-only operational endpoints:

- `/health`
- `/status`
- `/cdp/status`
- `/tabs`

Safety flags are explicit: read-only is true, trading execution is false,
Telegram sends are false, and browser mutation is false.

## Runtime State

Windows host: `100.x.x.z`

Current healthy surfaces:

- SSH: `100.x.x.z:22`
- Windows TV agent: `100.x.x.z:8081`
- Windows webhook: `100.x.x.z:9090`
- Telemetry dashboard: `100.x.x.z:3001`
- Windows Ollama: healthy through webhook readiness
- TradingView CDP: healthy on Windows loopback at `127.0.0.1:9222`

The TV agent reports Chrome `140.0.7339.133`, 16 browser tabs, and 4
TradingView tabs. CDP remains loopback-only on the Windows host by design; the
remote surface is the read-only `:8081` agent, not raw DevTools exposure.

## Persistence

Registered Windows scheduled tasks:

- `Sapphire-TV-Agent`
- `Sapphire-TV-Agent-Logon`
- `SapphireResearchWorker`

The desktop and Startup TradingView launcher were repaired to create
`%APPDATA%\TradingView\electron-flags.cfg`, start TradingView with
`--remote-debugging-port=9222`, and keep CDP local to the Windows host.

`SapphireResearchWorker` is registered for the daily overnight slot. It was
also run manually after the merge to refresh proof at the current `main` SHA.

## Verification Snapshot

Focused PR #492 gates:

- `pytest tests/unit/test_windows_tv_agent_server.py tests/unit/test_windows_tv_agent_scripts.py tests/unit/test_webhook_receiver.py -q`
- `ruff check services/windows_tv_agent services/webhook/src/receiver.py scripts/windows_setup tests/unit/test_windows_tv_agent_server.py tests/unit/test_windows_tv_agent_scripts.py tests/unit/test_webhook_receiver.py`
- `python -m compileall -q services/windows_tv_agent`
- `git diff --check`
- `python scripts/ops/local_ci_verify.py --quiet`

Live runtime checks after hot-apply:

- `curl http://100.x.x.z:8081/health`
- `curl http://100.x.x.z:8081/tabs`
- `curl http://100.x.x.z:9090/webhook/health`
- `curl http://100.x.x.z:9090/windows/research-worker/latest`

Final production readiness:

- Command: `/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external --format json`
- Result: 44 pass, 8 warn, 0 fail, 2 skip
- All Windows checks passed: Ollama model inventory, webhook health, SSH TCP,
  TradingView agent TCP, webhook TCP, and telemetry dashboard TCP.

Remaining warnings are outside this Windows desktop repair lane:

- Pi inference tiers `pi-rari1` and `pi-rari2` are degraded.
- Routine checks are gated with `external_disabled`.
- GCP production-readiness gates still require human/project readiness.
- Gemini or Vertex live-call validation remains manually gated.

## Follow-Ups

- Keep CDP loopback-only unless a separate, reviewed access-control layer is
  added.
- Use `:8081` for remote TradingView health and tab summaries.
- Continue treating the Windows research worker as paper-only until an
  explicit live-trading approval and control layer exist.
- Re-check the scheduled `SapphireResearchWorker` task after its first
  overnight Task Scheduler run.
- Next high-ROI lanes are Pi inference-tier repair, routine artifact
  freshness, and dashboard surfacing of Windows research-worker history.
