# Sapphire Risk Kernel 0.1.0

Sapphire Risk Kernel 0.1.0 is the public, versioned safety surface around the
same capital-protection controls used by the production Sapphire signal path.
It evaluates a proposed decision before that decision can become an action and
returns a verdict tree that names every policy that fired.

The production signal pipeline still uses the existing
`sapphire_core.risk_kernel.HardRiskKernel` compatibility path. The 0.1.0
surface adds a stable buyer-facing contract at `lib.core.risk_kernel` without
retuning live trading behavior.

## Import Surface

```python
from lib.core.risk_kernel import DecisionEnvelope, RiskKernelV1

decision = DecisionEnvelope(
    decision_id="order-001",
    action="open_order",
    symbol="BTC-USD",
    side="long",
    notional_usd=1300.0,
    equity=100000.0,
    risk_metrics={"daily_loss_pct": 0.8, "kill_switch_active": False},
)
verdict = RiskKernelV1().evaluate(decision)
```

The package also re-exports the legacy `HardRiskKernel` and
`RiskKernelEvent`, plus the confirmation-firewall primitives
`ConfirmationFirewall`, `ActionRisk`, and `classify_action` for compatibility
with existing Sapphire safety callers.

## DecisionEnvelope

`DecisionEnvelope` is schema-versioned (`schema_version=1`) and accepts:

- identity: `decision_id`, `action`, `created_at`
- instrument fields: `symbol`, `side`, `quantity`, `price`, `notional_usd`
- sizing fields: `proposed_position_pct`, `equity`, `atr`, `stop_loss_price`
- execution flags: `confidence`, `reduce_only`
- extensibility maps: `risk_metrics`, `market_data`, `metadata`

Callers may pass either a `DecisionEnvelope` instance or a plain dictionary.
Dictionary inputs are coerced with `DecisionEnvelope.from_mapping()`.

## RiskVerdict

`RiskKernelV1.evaluate(decision) -> RiskVerdict` returns:

- `allowed`: `false` when any policy fires
- `fired_gates`: every failed `PolicyResult`
- `policy_results`: every policy result, passed or failed
- `evaluation_ms`: elapsed local evaluation time
- `kernel_version`: currently `0.1.0`
- `schema_version`: currently `1`

Policy exceptions fail closed. A broken policy appears as a fired result with a
`policy error` reason instead of silently allowing an action.

## Shipped Policies

`DailyLossPolicy` rejects non-reducing entries when `daily_loss_pct >= 4.0`.
An optional USD threshold is supported by constructor parameter.

`IntradayDrawdownPolicy` rejects non-reducing entries when
`intraday_drawdown_pct >= 3.5`.

`AtrSizingPolicy` rejects entries whose position size, ATR exposure, or
stop-loss risk breaches the configured limits. The defaults are 10 percent max
position, 2 percent max ATR risk, and 1 percent max single-trade stop risk.

`KillSwitchPolicy` rejects non-reducing entries when the envelope or injected
status provider says a kill switch is active. Reduce-only exits remain allowed.

`DataLeakagePolicy` rejects lookahead flags, future feature timestamps,
secret-shaped prompt excerpts, and explicit attempts to bypass the risk kernel,
kill switch, or confirmation firewall.

## Custom Policies

A policy is a single-file class with:

```python
name = "my_policy"
version = "1.0.0"
params = {"threshold": 3}

def check(self, envelope) -> PolicyResult:
    ...
```

Pass custom policies to the kernel:

```python
kernel = RiskKernelV1(policies=(*default_policies(), MyPolicy()))
```

## Red-Team Benchmark

`tests/integration/test_risk_kernel_redteam.py` loads the existing red-team
corpus under `tests/fixtures/redteam/` and the new
`risk_kernel_leakage_scenarios.json` corpus. The leakage set covers lookahead
bias, position-sizing overrides, kill-switch bypass attempts, hard risk-limit
breaches, ATR risk breaches, and secret-shaped prompt leakage.

Acceptance for 0.1.0 is a rejection rate of at least 95 percent on the leakage
set.

## SLA

Kernel evaluation is in-process, dependency-light, and bounded at p99 <= 2 ms
for the default policy set on the Sapphire Mac runtime. The integration tests
assert the verdict shape and rejection behavior; local CI remains the merge
gate for changes to the policy surface.
