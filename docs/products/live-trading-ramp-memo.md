# Live Trading Ramp Memo

## Current State

Sapphire is a trading intelligence and autonomy system, not a live capital
machine. The repo currently supports paper trading, order drafts, read-only
Robinhood Crypto account checks, Hyperliquid public-data surfaces, TradingView
webhook intake, and a capped manual Robinhood Crypto pilot path. The active
posture is `manual_confirmed_crypto_only`, documented in
`docs/ops/robinhood-real-funds-readiness.md`.

The important distinction is that Sapphire can reason about live orders, but it
does not get to submit them unattended. `lib/trading/strategy_lab.py` reports
`TRADINGVIEW_EXECUTION_ENABLED=false`, builds paper and order-draft payloads,
and keeps live execution disabled. `scripts/ops/robinhood_manual_order.py` is
the only currently documented real-order utility, and it defaults to dry-run. A
real Robinhood Crypto order requires Ari to run the tool with `--execute` and
type the exact one-order confirmation token printed by the matching dry run.

The funded pilot budget described in the Robinhood readiness runbook is small by
design: a $50 cash budget, first live crypto order capped at $5 notional, and a
daily live pilot cap of $10 notional. The first order is expected to be a
liquid crypto limit order, not a market order and not a stock, ETF, option, or
private endpoint automation.

This memo is therefore not a claim that Sapphire should trade live tonight. It
is the acquisition-grade ramp from paper to live capital: what exists, what is
blocked, which metrics unlock the next phase, and how a buyer should preserve
the gates rather than skipping them.

## Phase 0: Paper-Only Expansion

Phase 0 is the current default. The system generates signals, drafts orders,
evaluates risk, writes local artifacts, and proves behavior under tests. It may
call public-data APIs or read-only authenticated APIs where explicitly gated,
but it does not move money.

The immediate expansion inside Phase 0 is broader paper coverage, not live
capital. Sapphire should continue scoring BTC, ETH, SOL, and high-liquidity
crypto symbols through the paper stack while adding better signal correlation
and observability. Stocks remain research-only because no official public
Robinhood equities trading API has been identified in the repo. If stocks are
paper-tested, they should use market data and simulated fills only.

The target gates for leaving Phase 0 are deliberately conservative:

- BTC directional prediction accuracy at or above 75 percent for 30 consecutive
  calendar days.
- ETH directional prediction accuracy at or above 60 percent for 30 consecutive
  calendar days.
- SOL directional prediction accuracy at or above 60 percent for 30 consecutive
  calendar days.
- Paper fills recorded with fees, spread, slippage, and timestamp evidence.
- RiskKernelV1 verdicts available for every proposed entry-like decision.
- Confirmation firewall tests passing, especially financial dry-run vs live
  distinction.
- Production readiness sweep returning 0 FAIL.

The rollback from Phase 0 is trivial: keep `TRADINGVIEW_EXECUTION_ENABLED=false`,
keep order tools in dry-run mode, pause any scheduler via `/routines pause
<name>`, and leave the paper portfolio as the only automated destination.

## Phase 1: Paper To Manual Crypto Pilot

Phase 1 begins when paper evidence is good enough to justify a single
operator-confirmed live crypto order. This is still not autonomous live trading.
The system may prepare a Robinhood Crypto limit-order dry run, but Ari must
perform the one-order confirmation ceremony in the active terminal.

The allowed first rung is $5 notional. Before the order, Sapphire must prove the
following in the same work session:

- Local tests for Robinhood reader, strategy-lab drafts, and manual-order dry
  run pass.
- Credential presence is checked without printing secrets or signatures.
- Live read-only account and product probes confirm account active state,
  tradability, buying power, quote freshness, spread, and estimated fee.
- The order draft uses the v2 crypto order endpoint and a UUID
  `client_order_id`.
- The order is a limit order with a guarded price from a just-in-time read-only
  quote.
- The kill switch is inactive immediately before submit.
- The confirmation firewall remains configured so live financial auto-approval
  is not enabled.

After a $5 order, the system stops. It records order state, fill status, fee,
spread, and portfolio delta, then writes a post-trade note before a second
order is considered. Repetition without analysis is explicitly out of scope.

Promotion from $5 to $50 requires at least 14 trading days of paper-plus-manual
evidence with Sortino greater than 1.5 at the tested strategy level, no
unreviewed hard-risk holds, no confirmation-firewall bypass, and no unexplained
slippage or fill-shape mismatch. The $50 rung is a cap, not a target.

## Phase 2: Crypto Live Tier

Phase 2 is the first phase where limited live crypto repetition becomes
thinkable. It still does not authorize unattended loops. The rungs are:

- $5 first-order pilot.
- $50 capped manual-confirmed crypto tier.
- $500 capped live tier only after repeated evidence and explicit operator
  approval.

Each rung needs its own 14 trading-day window with Sortino above 1.5, stable
paper-to-live drift, and clean readiness checks. Any rung can be paused by the
operator without code changes. Any rung can roll back to paper-only by removing
`--execute`, keeping `TRADINGVIEW_EXECUTION_ENABLED=false`, and requiring all
strategy outputs to remain drafts.

The $500 tier is not active today. It would require a separate PR, a buyer- or
operator-reviewed runbook update, and stronger live-order telemetry. A buyer
should treat it as a designed future rung, not inherited authority.

## Phase 3: Stock Live Tier

Stock live trading is blocked. The repo has no basis to automate Robinhood
stocks, ETFs, or options through undocumented endpoints. Phase 3 can begin only
after one of three events:

- Robinhood publishes an official public equities trading API with documented
  authentication and order contracts.
- Ari approves a different broker with an official API.
- A buyer supplies a regulated execution venue and requests a new integration
  behind the same risk and confirmation gates.

Until then, Sapphire may perform stock research, generate paper trades, and
draft risk-reviewed recommendations. It must not submit stock orders.

## Kill Switches And Rollbacks

Every live ramp phase inherits the same shutdown vocabulary:

- RiskKernelV1 in `lib/core/risk_kernel/__init__.py::RiskKernelV1` evaluates
  decision envelopes before action.
- The legacy hard gate in
  `lib/core/src/sapphire_core/risk_kernel.py::HardRiskKernel` maintains hold
  windows for daily loss, intraday drawdown, consecutive loss events, and hard
  execution failures.
- Portfolio drawdown shutdown lives in `lib/core/kill_switch.py::KillSwitch`.
- Security shutdown lives in `lib/core/security_kill_switch.py::engage`.
- Human authorization lives in
  `lib/core/confirmation_firewall.py::ConfirmationFirewall`.
- Routine pause controls live in `lib/core/routine_pause.py::abort_if_paused`
  and the Telegram operator console.

The quickest rollback is operational: stop submitting live orders, pause any
routine that drafts them, run the readiness sweep, and keep future actions in
paper/dry-run mode. The code rollback is a PR revert. The LaunchAgent rollback
is to leave existing local production services untouched unless a separate
operator-approved change explicitly disables them.

## Open Questions

The main open question is not whether Sapphire can place a live crypto order.
It can generate the draft path and a manually confirmed command. The question is
whether the evidence is good enough to justify doing so more than once.

The second open question is which broker or venue should own future stock
execution. The current answer is "none." That honesty matters. A buyer should
not infer hidden stock automation from the presence of strategy dashboards.

The third open question is how much capital should be delegated if Sapphire is
acquired. The answer should be set by the acquirer risk committee, not by code
defaults in this repo. The existing $5/$50/$500 ladder is a safety scaffold, not
an investment mandate.

## Acquirer Relevance

This memo articulates the regulated ramp from paper to live. A buyer absorbing
Sapphire would inherit the gating: paper evidence first, manual crypto pilot
second, limited live crypto only after metrics, stock automation blocked until
official API support exists, and all future mutation paths behind risk kernel,
confirmation firewall, kill switch, provenance, and audit evidence.

The commercial value is not recklessness. It is a system that can generate
actionable edge while still knowing which actions are research, which are
drafts, which are paper, and which are live. Do not skip phases.
