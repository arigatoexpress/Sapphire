# sapphire-sentinel-gate

Multi-chain agent-safety gate. One small primitive, importable by any autonomous agent.

```bash
pip install sapphire-sentinel-gate
```

## What

`sapphire-sentinel-gate` is a pre-trade safety primitive for autonomous on-chain agents. Given a chain id, it returns a verdict — `HEALTHY`, `WARNING`, or `BLOCK` — derived from live protocol state on that chain (stablecoin peg, lending-pool solvency, oracle staleness). When the underlying chain is degraded — USDM depegging, an Aave reserve frozen, a high-utilization reserve paused — your agent should refuse to *spend alpha money* against signals that reference that chain. The gate makes that refusal explicit, classified, and pluggable.

This is the chain-health primitive extracted from [Sapphire](https://github.com/arigatoexpress/Sapphire)'s Sentinel firewall, packaged so external agent stacks can `pip install` it instead of querying a SaaS.

## Why

Autonomous agents that pay for alpha (signal subscriptions, copy-trade fills, x402 micropayments) need a pre-trade gate that's chain-aware. Existing safety stacks check budget, mandate, domain allow-list, prompt injection — none of them check *whether the chain the alpha references is actually tradeable right now*. If USDM is depegging by 137bp, paying for an alpha signal that buys USDM-collateralized exposure is wasteful at best and adversarial at worst.

`sapphire-sentinel-gate` adds that one missing axis. The gate is **fail-open by default** — a flaky RPC at demo time should not block a legitimate payment. It blocks only on *observed* distress, never on absence of evidence.

## How

Three lines, on the safe path:

```python
from sentinel_gate import default_gate

gate = default_gate()
verdict = gate.evaluate_chain(4326)  # MegaETH

if verdict.severity == "BLOCK":
    refuse_trade(reasons=verdict.reasons)
```

### Supported chains

| Chain id | Name | Distress signals checked |
|----------|------|--------------------------|
| `4326`   | MegaETH | USDM peg break, Aave V3 paused/frozen reserves, high-utilization pause |
| `42161`  | Arbitrum One | Aave V3 paused/frozen reserves, high-utilization pause |
| `10`     | Optimism | (placeholder — falls through to HEALTHY; pluggable via `register_chain`) |

Any chain id the gate doesn't know about returns `HEALTHY` with reason `"chain not gated"`. The gate never blocks a chain it can't read — it just records that the chain is out of scope.

### Verdict shape

```python
@dataclass(frozen=True)
class ChainHealthVerdict:
    chain_id: int
    chain_name: str
    severity: str  # "HEALTHY" | "WARNING" | "BLOCK"
    reasons: list[str]
    peg_divergence_bps: Decimal | None  # actual measured spread (None if not gated)
    aave_paused_reserves: list[str]
```

Severity ladder (highest wins):

- `BLOCK` — stable peg break ≥100bp, OR any reserve paused with utilization >80%
- `WARNING` — peg drift 50–100bp, OR any reserve frozen
- `HEALTHY` — everything nominal

`WARNING` is surface-only. Sentinel only refuses on `BLOCK`.

### Bring your own client

`default_gate()` constructs a live HTTP JSON-RPC client against MegaETH mainnet. For tests, custom RPC endpoints, or chain-specific routing, supply your own factory:

```python
from sentinel_gate import ChainHealthGate

def my_client_factory():
    return MyAsyncRpcClient(rpc_url="https://my.rpc.endpoint")

gate = ChainHealthGate(client_factory=my_client_factory, allow_when_unavailable=True)
verdict = gate.evaluate_chain(4326)
```

The client need only be duck-typed — anything matching the `MegaETHProtocols` / `ArbitrumProtocols` surface from Sapphire's `lib/chains/` works. For unit tests, a `SimpleNamespace` with `stable_health()` / `lend_overview()` async methods is enough.

### Extending with custom chains

The dispatcher is data-driven — each chain id maps to an evaluator coroutine. You can register your own:

```python
from sentinel_gate import ChainHealthGate, register_chain

async def evaluate_my_chain(client) -> ChainHealthVerdict:
    ...

register_chain(chain_id=8453, name="Base", evaluator=evaluate_my_chain)
```

### Fail-open vs fail-closed

```python
ChainHealthGate(client_factory=..., allow_when_unavailable=True)   # default — RPC failure → HEALTHY
ChainHealthGate(client_factory=..., allow_when_unavailable=False)  # paranoid — RPC failure → BLOCK
```

Use fail-closed only when you want to refuse payments during chain-data outages. The default favours uptime over false-positive refusals.

## License

MIT. See `LICENSE`.

## Upstream

This package vendors a snapshot of `lib/hackathon/chain_health_gate.py` from [Sapphire](https://github.com/arigatoexpress/Sapphire). When the upstream primitive changes, the vendored copy is re-synced. See `CONTRIBUTING.md` for the sync workflow.
