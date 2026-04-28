# Kill-Switch Invariants

## Scope

This document enumerates the shutdown and recovery controls that protect
Sapphire from turning a bad signal, bad operator command, bad integration, or
bad account state into uncontrolled action. It is intentionally grounded in the
current repo. If an invariant is aspirational, this document says so.

The live-trading posture is conservative: paper by default, dry-run before
live, one-order manual confirmation for Robinhood Crypto, and no stock
automation through private endpoints. The kill-switch system exists to preserve
that posture under stress.

## Layer 1: Trade-Time Invariants

### RiskKernelV1

`lib/core/risk_kernel/__init__.py::RiskKernelV1` is the buyer-facing policy
kernel. It evaluates a `DecisionEnvelope` and returns a `RiskVerdict` with every
policy result, fired or passed. Policy exceptions fail closed.

The default policy set is:

- `DailyLossPolicy`: blocks non-reducing entries when `daily_loss_pct >= 4.0`.
- `IntradayDrawdownPolicy`: blocks non-reducing entries when
  `intraday_drawdown_pct >= 3.5`.
- `AtrSizingPolicy`: blocks oversize entries, ATR exposure above 2 percent,
  single-trade stop risk above 1 percent, and unapproved sizing overrides.
- `KillSwitchPolicy`: blocks non-reducing entries when an envelope or provider
  says a kill switch is active. Reduce-only exits remain allowed.
- `DataLeakagePolicy`: blocks lookahead flags, future feature timestamps,
  secret-shaped prompt excerpts, and explicit risk-kernel bypass attempts.

Invariant: every future live entry path must construct a decision envelope and
persist the verdict tree before submit. Today, this is a public contract and a
tested surface; not every future mutation path should be assumed wired until a
path-level audit proves it.

### HardRiskKernel

`lib/core/src/sapphire_core/risk_kernel.py::HardRiskKernel` is the legacy
entry-gating kernel used by execution-adjacent paths. It maintains a local hold
window, with defaults of 30 minutes, and blocks entries after:

- daily loss above 4 percent;
- intraday drawdown above 3.5 percent;
- 4 consecutive loss events;
- 5 consecutive hard execution failures.

Invariant: a hold is entry-only. Reduce-only exits should remain possible. A
hold expires only after the configured hold window elapses; new breaches extend
the hold rather than shortening it.

### Portfolio Kill Switch

`lib/core/kill_switch.py::KillSwitch` protects portfolio-level drawdown. It
tracks a rolling 24-hour peak and an all-time peak. Defaults are 5 percent
24-hour drawdown and 15 percent total drawdown. Once active, it forces signal
confidence to 0 through `scale_confidence()` and reports active state through
`should_halt()` and `status()`.

Invariant: activation emits `kill_switch.activated`; deactivation emits
`kill_switch.deactivated`; notifications are best-effort and cannot crash the
switch. Recovery requires paper-trading PnL evidence through
`check_recovery()`, not a silent reset.

### Circuit Breakers And Latency

The general circuit-breaker state machine is covered by
`tests/unit/test_circuit_breaker.py`. It opens after configured consecutive
failures, rejects calls while open, half-opens after timeout, closes on success,
and reopens on half-open failure.

There is no single universal "latency kill switch" for all trading paths today.
Latency appears in several readiness and health surfaces, and execution
dispatchers track hard failures, but a global latency-to-halt invariant is a
future hardening item. The current honest invariant is narrower: repeated hard
execution failures trip `HardRiskKernel`; circuit-breaker-protected clients
must refuse calls while open.

## Layer 2: Confirmation Firewall

`lib/core/confirmation_firewall.py::ConfirmationFirewall` classifies actions as
read-only, self-modifying, system-modifying, external-send, financial, or
destructive.

Invariant: read-only and self-modifying actions may auto-approve. Higher-risk
actions require confirmation. Destructive actions enforce a 30-second delay
after approval. Financial auto-approval is constrained to paper/dry-run actions
under the daily auto limit. Live financial auto-approval is off unless
`SAPPHIRE_FIREWALL_ALLOW_LIVE_FINANCIAL_AUTO_APPROVAL` is explicitly set, which
should not be part of the normal production posture.

Confirmation records live under `~/.sapphire/pending_confirmations/`; audit
records live under `~/.sapphire/audit/confirmation_firewall.jsonl`. Expired
confirmations can be archived by the existing ops script and should not be
treated as approval.

Recovery path: deny or let a pending confirmation expire, then re-run the
action only after the operator restates intent. If the action is financial and
live, prefer a new dry run and new one-order token rather than reusing old
context.

## Layer 3: Operator Manual Halt

The Telegram operator console in
`plugins/claw-sapphire/tools/sapphire_pm_bot.py` exposes `/routines pause
<name>`, `/routines resume <name> CONFIRM`, `/cancel-routine <name> CONFIRM`,
`/routines list`, and `/routines status`.

Invariant: pausing is easy and reversible. Resuming requires the literal
`CONFIRM` token because it removes a protective flag. Routine names are
validated; path traversal and shell-like names are rejected.

Pause flags are read by `lib/core/routine_pause.py::abort_if_paused`. A paused
routine logs a structured `routine_pause.skipped` event and exits successfully
at startup. Existing in-flight work is not killed by the pause flag; this is
intentional. If immediate interruption is needed, it becomes a separate
operator action with a narrower runbook.

Recovery path: run `/routines status`, decide whether the routine should resume,
then send `/routines resume <name> CONFIRM`. If the wrong routine was paused,
resume it and pause the intended routine. No data deletion is required.

## Layer 4: Security Kill Switch

`lib/core/security_kill_switch.py::engage` is for suspected account compromise
or external-routing risk. It is non-destructive and reversible. It stops the
signal logger, writes a cloud-routing kill flag, unloads the content-engine
LaunchAgent, sends a Telegram P0 alert if possible, stops the inference proxy,
and appends a local system event.

Invariant: failures are collected but do not abort the sequence. The goal is to
reduce external connectivity quickly, not to produce a perfectly clean shutdown
transcript. The disengage path removes the cloud-routing kill flag through
`lib/core/security_kill_switch.py::disengage`.

This switch can affect production-adjacent services and should remain an
operator action, not an autonomous agent reflex.

## Layer 5: Heartbeat And Supervisor

`lib/core/heartbeat.py` maintains component health state and consecutive
failure counters; `tests/unit/test_heartbeat.py` covers transitions and failure
tracking. `plugins/claw-sapphire/tools/internal/service_supervisor.py` and its
tests cover supervisor status surfaces. These are observability and recovery
helpers, not permission to mutate every LaunchAgent automatically.

Invariant: health evidence should make it clear what failed, how many
consecutive failures were observed, and whether the service is merely unhealthy
or actively halted. Retargeting, unloading, or deleting LaunchAgents remains a
separate operator-reviewed action.

## Witness And Audit

Every kill or reset path should leave evidence:

- RiskKernelV1 returns a verdict tree with fired policies.
- HardRiskKernel exposes hold state through `status()`.
- Portfolio kill switch emits event-bus records.
- Confirmation firewall writes audit JSONL records and pending files.
- Security kill switch writes a system event and a cloud-routing flag.
- Routine pause writes timestamped pause flags and emits skip events at routine
  startup.

Some witness paths are stronger than others. Risk verdicts and firewall audit
records are structured. Telegram P0 sends are best-effort. Dashboard visibility
is improving through `/observability`, but it should not be treated as the
source of authority; the source is the local state and event files.

## Test Coverage Map

| Invariant | Primary file | Tests |
|---|---|---|
| RiskKernelV1 policy verdicts | `lib/core/risk_kernel/__init__.py::RiskKernelV1` | `tests/unit/test_risk_kernel_public_surface.py`, `tests/unit/test_risk_kernel_types.py` |
| Legacy hard holds | `lib/core/src/sapphire_core/risk_kernel.py::HardRiskKernel` | `tests/unit/test_risk_kernel.py` |
| Portfolio kill switch | `lib/core/kill_switch.py::KillSwitch` | `tests/unit/test_kill_switch.py` |
| Security kill switch | `lib/core/security_kill_switch.py::engage` | `tests/unit/test_security_kill_switch.py` |
| Confirmation firewall | `lib/core/confirmation_firewall.py::ConfirmationFirewall` | `tests/unit/test_confirmation_firewall.py` |
| Routine pause flags | `lib/core/routine_pause.py::abort_if_paused` | `tests/unit/test_routine_pause.py`, `plugins/claw-sapphire/tests/test_sapphire_pm_bot.py` |
| Circuit-breaker state | `lib/core/src/sapphire_core/circuit_breaker.py::CircuitBreaker` | `tests/unit/test_circuit_breaker.py` |
| Heartbeat counters | `lib/core/heartbeat.py::HeartbeatMonitor` | `tests/unit/test_heartbeat.py` |

## Buyer Readout

The invariant set is credible because it is layered. A bad signal should meet a
risk kernel. A risky command should meet a confirmation firewall. A drawdown
should trip a portfolio kill switch. A suspected compromise should use the
security kill switch. A misbehaving routine should be paused without deleting
state. A buyer should preserve those layers and require new mutation paths to
declare which layer they pass through.
