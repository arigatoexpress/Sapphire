# Windows Desktop Server Runbook

Last reviewed: 2026-04-29

This runbook covers `DESKTOP-HFCK6U9`, the Windows machine on Tailscale
`100.x.x.z`. Treat it as Sapphire's private desktop accelerator: GPU
inference first, historical backtesting and strategy experiments second, and
persistent service host third.

The node is not an execution authority. It must not submit live orders, sign
broker payloads, send Telegram messages, print secrets, or write production data
unless a later operator-reviewed PR explicitly enables a narrow path.

## Roles

| Role | Surface | Default posture |
|---|---|---|
| GPU inference | Ollama on `100.x.x.z:11434` through the Mac inference proxy on `127.0.0.1:11435` | Read-only prompts and local model calls |
| Strategy research | `lib.analytics.run_strategies` and `lib.analytics.backtest_harness` | Dry-run artifacts, noncanonical output directory for smoke work |
| TradingView intake | Windows webhook on `100.x.x.z:9090` | Payload validation and paper paths only |
| Telemetry | Windows telemetry dashboard on `100.x.x.z:3001` when loaded | Read-only status |
| Remote shell | SSH as `aribs@100.x.x.z` | Read-only status by default |

## Health Checks

Use the production sweep first. It now includes Windows desktop checks:

```bash
python3 scripts/ops/production_readiness_sweep.py --no-external --format markdown
```

Direct probes:

```bash
/usr/bin/curl -sS --max-time 5 http://100.x.x.z:11434/api/tags | python3 -m json.tool
/usr/bin/curl -sS --max-time 5 http://127.0.0.1:11435/health | python3 -m json.tool
ssh -o BatchMode=yes -o ConnectTimeout=5 aribs@100.x.x.z hostname
```

Read Scheduled Tasks without changing them:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 aribs@100.x.x.z \
  'powershell -NoProfile -Command "Get-ScheduledTask -TaskName OllamaServe,SapphireWebhook,SapphireDashboard -ErrorAction SilentlyContinue | Select-Object TaskName,State | ConvertTo-Json"'
```

## Expected Model Inventory

The readiness sweep expects the Windows Ollama inventory to cover the proxy's
official local tiers:

| Alias | Model |
|---|---|
| `fast` | `nemotron-mini:4b` |
| `balanced` | `hermes3:8b` |
| `code` | `gemma4:latest` |
| `reason` | `deepseek-r1:14b` |
| `qwen-reason` | `qwen3.5:9b` |
| `deep` | `qwen3:14b` |
| `qwen3.6` | `qwen3.6:27b` |
| `cascade` | `nemotron-cascade-2` or `nemotron-cascade-2:latest` |
| `large` | `qwen2.5:32b` |

Missing aliases are warnings, not hard failures, because the Mac and Kimi tiers
remain fallbacks. A missing `reason`, `code`, or `large` alias should still be
treated as an operator action item before overnight strategy research.

## Backtesting

Prefer noncanonical output directories for smoke and experiment runs:

```bash
/usr/local/bin/python3 -m lib.analytics.run_strategies \
  --days 7 \
  --bankroll 10000 \
  --output-dir /tmp/sapphire-backtest-smoke
```

When running remotely on Windows, keep output under a scratch directory until a
separate PR decides whether any artifact belongs in the canonical repo:

```bash
ssh aribs@100.x.x.z \
  'powershell -NoProfile -Command "cd E:\Sapphire\Code\Sapphire; python -m lib.analytics.run_strategies --days 90 --bankroll 10000 --output-dir E:\Sapphire\scratch\backtests\manual"'
```

Do not point a scheduled Windows job at `data/backtests/strategies/` without a
matching comparator, rollback note, and runbook update. The Mac
`com.sapphire.backtest-weekly` LaunchAgent remains the canonical weekly routine
until remote shadow evidence proves parity.

## Driving the Windows agent stack from the Mac

`scripts/ops/agent` is a thin Mac-side CLI over the tailnet. It exists so the
GPU box can be developed "from the inside out" without opening a GUI session on
it.

```bash
agent ask "why is the funding skew inverted on SOL?"   # via the Mac proxy
agent ask --direct "summarise this" < diff.txt         # straight to the GPU
agent --model qwen3:14b ask "..."                      # pin a model
agent models                                           # what's loaded on the box
agent status                                           # tier health + failover
agent dispatch "fix the import error in main.py"       # policy-routed task
agent shell "nvidia-smi"                               # command over Tailscale SSH
agent repl                                             # interactive loop
```

Prompts come from trailing arguments, or stdin when none are given — so
`agent ask "x"`, `echo x | agent ask`, and `agent ask < file` all work. Stdin is
only read when there are no argument prompts, so an interactive terminal never
hangs waiting on it.

**Routing.** Default goes to the Mac inference proxy on `:11435`, which gives
4-tier failover, prompt cache, quota accounting and the outbound sensitivity
gate. `--direct` bypasses it to Windows Ollama on `:11434` — useful when the
proxy is down, at the cost of failover.

The two endpoints do **not** speak the same protocol. The proxy is
OpenAI-compatible (`/v1/chat/completions`); Windows Ollama's `/v1/` surface
returns empty and must be driven through the native `/api/chat`. The CLI handles
both response shapes; keep that asymmetry in mind if you script around it.

**Overrides** (all optional):

| Variable | Default |
|---|---|
| `SAPPHIRE_PROXY_URL` | `http://127.0.0.1:11435` |
| `SAPPHIRE_WINDOWS_GPU_URL` | `http://100.x.x.z:11434` |
| `SAPPHIRE_WINDOWS_SSH` | `aribs@desktop-hfck6u9` |
| `SAPPHIRE_WINDOWS_REPO` | `E:\Sapphire\Code\Sapphire` |
| `SAPPHIRE_AGENT_MODEL` | `auto` |
| `SAPPHIRE_AGENT_TIMEOUT` | `120` |

`agent shell` tries a POSIX shell first and falls back to
`powershell -NoProfile -Command`, so it works both before and after setting
OpenSSH's `DefaultShell` to Git Bash on that host.

If `agent status` reports the GPU unreachable after a Windows reboot, the usual
cause is `OLLAMA_HOST=0.0.0.0` not surviving — see the Gotchas in CLAUDE.md.

## Research Worker

Repo-owned scripts are staged for a paper-only Windows Research Worker:

| Script | Purpose |
|---|---|
| `scripts/windows_setup/run_research_worker.ps1` | Runs strategy sweep plus synthetic walk-forward validation into `E:\Sapphire\research-worker\<timestamp>\` and writes `manifest.json`. |
| `scripts/windows_setup/create_research_worker_task.ps1` | Registers `SapphireResearchWorker` in Task Scheduler, but does not start it. |

Dry-run/manual smoke from Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\Sapphire\Code\Sapphire\scripts\windows_setup\run_research_worker.ps1 `
  -BacktestDays 7 `
  -WalkforwardStrategies RegimeAwareRSI `
  -WalkforwardBarsSource synthetic
```

The worker manifest records `paper_only=true`,
`live_trading_enabled=false`, `telegram_sends_enabled=false`, host, git SHA,
commands, logs, and artifact paths. Keep `WalkforwardBarsSource` as
`synthetic` unless the operator intentionally wants read-only yfinance data.

The Windows webhook exposes the latest run at:

```text
http://100.x.x.z:9090/windows/research-worker/latest
```

That payload includes manifest freshness (`age_seconds`, `max_age_seconds`,
`fresh`) and read-only Task Scheduler state for `SapphireResearchWorker`
(`state`, `last_run_time`, `next_run_time`, `last_task_result_label`). The
default freshness budget is 36 hours so a daily overnight worker has room for
normal scheduling jitter without hiding stale evidence.

Task Scheduler install is a separate operator action:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\Sapphire\Code\Sapphire\scripts\windows_setup\create_research_worker_task.ps1
```

Do not start the task until the manual smoke run has produced a manifest and
the artifact location has been reviewed.

## TradingView Workbench Agent

The live `Sapphire-TV-Agent` and `Sapphire-TV-Agent-Logon` tasks should point
at the repo-owned read-only agent, not the removed
`TradingViewAutonomousManager` backend.

| Script | Purpose |
|---|---|
| `scripts/windows_setup/start_tv_agent.ps1` | Starts `python -m services.windows_tv_agent.server` on port `8081`; exits 0 if the port is already listening. |
| `scripts/windows_setup/create_tv_agent_task.ps1` | Registers startup and logon tasks for the read-only agent. |
| `scripts/windows_setup/create_task_scheduler_job.ps1` | Backwards-compatible wrapper that delegates to `create_tv_agent_task.ps1`. |
| `scripts/windows_setup/start_tradingview_cdp.ps1` | Starts the installed TradingView Desktop package with local CDP on `127.0.0.1:9222`, without hard-coding the WindowsApps version. |
| `scripts/windows_setup/ensure_windows_availability.ps1` | Disables sleep/lock paths, backs up rollback evidence, and registers read-only user-logon tasks for TradingView CDP and availability guardrails. |

Install or repair the tasks from Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\Sapphire\Code\Sapphire\scripts\windows_setup\create_tv_agent_task.ps1 `
  -PythonPath C:\Users\aribs\AppData\Local\Programs\Python\Python313\python.exe `
  -StartNow
```

Health checks:

```powershell
curl.exe http://127.0.0.1:8081/health
curl.exe http://127.0.0.1:8081/tabs
```

The agent is a read-only visibility surface. It reports `status=degraded` when
TradingView Desktop CDP is unavailable at `127.0.0.1:9222`, but it still
confirms that the `8081` service is alive. Do not add order-entry or Telegram
send behavior to this service.

To repair the Windows desktop availability/CDP layer without reintroducing
hard-coded package paths:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\Sapphire\Code\Sapphire\scripts\windows_setup\ensure_windows_availability.ps1 `
  -RepoPath E:\Sapphire\Code\Sapphire `
  -StartTradingViewCdp
```

This writes status/rollback files under `C:\Users\aribs\SapphireOps`, registers
`SapphireTradingViewCDP` and `SapphireWindowsAvailabilityGuard`, keeps safety
flags false for trading, Telegram, and browser mutation, and preserves any old
`TradingView-CDP.bat` copies in timestamped backups.

## Strategy Experiments

Windows GPU strategy work should start as continuous-intelligence leases:

```bash
python3 -m lib.autonomy.continuous_intelligence_artifacts lease \
  --agent-id windows-gpu \
  --target-runtime windows-gpu \
  --capability reason \
  --pretty
```

The lease command is dry-run by default. It does not dispatch orders, mutate
strategy files, write artifacts, or contact brokers. Use `--write` only when a
local artifact trail is intentionally needed.

## Stop Rules

Stop and create a PR or handoff before:

- Enabling live trading, order signing, or order submission.
- Sending Telegram messages from Windows.
- Installing, deleting, or retargeting Scheduled Tasks.
- Changing firewall or Tailscale ACL permissions.
- Writing canonical backtest artifacts from Windows.
- Printing environment variables, secrets, request bodies, private keys, or
  broker credentials.
