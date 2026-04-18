# Crypto / Privacy / Payments Integration Plan

Four complementary technologies that, together, make Sapphire OS *private* and *paid*:

| # | Tech | Purpose | Status |
|---|------|---------|--------|
| 1 | **x402 (Coinbase)** | HTTP 402 micropayments in USDC on Base | **Implemented** — `lib/payments/x402_middleware.py` |
| 2 | **Zama Concrete ML (FHE)** | Privacy-preserving cloud inference | Designed |
| 3 | **Ika 2PC-MPC** | Decentralized wallet signing for trading | Designed |
| 4 | **Aztec Noir** | Private on-chain strategy execution | Designed |

All four plug into the existing event bus (`lib/core/event_bus.py`) so they become observable in the dashboard overview and auditable in the NIST compliance view.

---

## 1. x402 (Coinbase) — **IMPLEMENTED**

### Architecture

```
┌──────────┐    GET /api/premium             ┌────────────┐
│  client  │ ───────────────────────────────>│  Sapphire  │
│ (wallet) │  <─── 402 + accepts[...]        │  endpoint  │
│          │  sign USDC payment on Base       │   (gated)  │
│          │ ───> GET /api/premium            │            │
│          │       X-PAYMENT: <b64>           │            │
│          │  <── 200 + response              └─────┬──────┘
└──────────┘                                        │
                                                    ▼
                                              event_bus
                                              payment.{required,
                                                received, rejected}
```

### What's Built

- `lib/payments/x402_middleware.py` — framework-agnostic core + Flask decorator
  - `X402Middleware` — orchestrator with nonce cache, pricing table, pluggable verifier
  - `PaymentRequirements` / `PaymentVerificationResult` — typed protocol payloads
  - `MockVerifier` — for tests / testnet without a facilitator
  - `require_payment(amount_usd, description=..., middleware=...)` — Flask decorator
  - `build_402_response(requirements, error)` — framework-free 402 JSON builder
- `tests/unit/test_x402_middleware.py` — 12 unit tests (missing header, underpayment,
  wrong recipient, wrong network, nonce replay, malformed base64, math)
- `tests/unit/test_x402_flask.py` — 5 end-to-end Flask tests proving the decorator
- Wired into `services/dashboard/app.py`:
  - `/api/chain/overview` → $0.01 / call
  - `/api/risk/metrics` → $0.02 / call
  - `/api/predictions/kronos` → $0.05 / call
- Wired into `services/inference-proxy/app.py`:
  - `/v1/chat/completions` → $0.001 / call
  - `/v1/completions` → $0.001 / call
  - `/v1/embeddings` → $0.0005 / call
- Emits `payment.required`, `payment.received`, `payment.rejected` on the event bus

### Env toggles

| Variable | Default | Purpose |
|---|---|---|
| `X402_ENABLED` | `0` (off) | Master switch — off = decorator is a no-op |
| `X402_NETWORK` | `base-sepolia` | `base` for mainnet |
| `X402_RECIPIENT` | (empty) | 0x... USDC recipient |
| `X402_ASSET` | network default | USDC contract address |
| `X402_FACILITATOR_URL` | (unused) | Optional Coinbase facilitator URL |
| `X402_PRICE_CHAT` | `0.001` | Per-call price for `/v1/chat/completions` |
| `X402_PRICE_COMPLETIONS` | `0.001` | Per-call price for `/v1/completions` |
| `X402_PRICE_EMBED` | `0.0005` | Per-call price for `/v1/embeddings` |

### Going to Production (effort: **S**)

1. Generate a USDC wallet on Base mainnet; store recipient in `X402_RECIPIENT`.
2. Swap `MockVerifier` for a production verifier:
   - Option A (easiest): use the official `x402` pip package's `x402ResourceServerSync`
     and delegate `PaymentVerifier.verify()` to it.
   - Option B (no pip): call Base JSON-RPC to `eth_call` the USDC contract's
     `transferFrom` event log and verify tx hash + amount + block finality.
3. Run on Base Sepolia first — flip `X402_NETWORK=base-sepolia` and fund a test wallet.
4. Set `X402_ENABLED=1`, monitor `/api/events/stream?types=payment.*` on the dashboard.
5. Move to `X402_NETWORK=base` once the first $1 of testnet payments settles cleanly.

---

## 2. Zama Concrete ML (FHE) — **DESIGNED**

### Motivation

Today the `sensitivity_classifier` prevents private queries from reaching T4 (Kimi
cloud) by **rejecting** them. FHE turns that into **encryption** — the query still
gets routed to a capable cloud model, but the query text never leaves the Mac in
plaintext.

### Architecture

```
┌──────────────────┐       ┌──────────────────┐       ┌────────────┐
│ task_classifier  │       │  FHE Server       │       │ Inference  │
│    (Mac, Py)     │       │  (Concrete ML)    │       │  proxy     │
│                  │       │                   │       │            │
│ encrypt(input)   │──────>│ classify(enc)     │       │            │
│                  │  ct   │ → enc_label       │       │            │
│ decrypt(label)   │<──────│                   │       │            │
│       │          │       └──────────────────┘       │            │
│       ▼ route                                       │            │
│  model tier = fast/balanced/deep/kimi               │            │
│                                                     │            │
└──────────────────┘                                  └────────────┘
```

### Dependencies

```bash
pip install concrete-ml  # requires Python 3.10+, installs ~600MB of compiled libs
```

- `concrete-ml` (Zama) — brings Concrete compiler + scikit-learn-compatible FHE classifiers
- `numpy`, `pandas` (already installed)
- Optional: `concrete-python` (lower-level circuit builder)

### Effort estimate: **L (3–5 days)**

1. **Day 1** — Train a logistic-regression task classifier on labelled messages.
   Labels: `{quick, balanced, deep, code, reason, sensitive}`. Input features: bag-of-words
   + 3 sentiment scores. Use `concrete.ml.sklearn.LogisticRegression`.
2. **Day 2** — Compile the model to an FHE circuit. Serialize keys + circuit to
   `data/fhe/classifier_v1/`. Set key-generation to run once at install time.
3. **Day 3** — Build `lib/privacy/fhe_classifier.py` wrapper. Public API:
   `classify_encrypted(text) -> TierLabel`. Internally encrypts, runs circuit,
   decrypts only the argmax label (never the logits).
4. **Day 4** — Wire into `plugins/claw-sapphire/lib/router.py`. Add
   `PRIVACY_FHE=1` toggle; when on, every classification runs through FHE.
5. **Day 5** — Benchmark. Expect ~200–500ms added latency per classification;
   offset by caching exact matches.

### Event bus integration

Publishes:
- `privacy.fhe.classified` — `{tier, cipher_size_kb, elapsed_ms}` (no plaintext data)
- `privacy.fhe.keygen` — one-time, at setup

Dashboard shows the fraction of classifications that ran in FHE vs. plaintext.

### NIST controls covered

- **PR.DS-1** (data at rest protected) — query is encrypted end-to-end
- **PR.DS-2** (data in transit) — ciphertext never decrypted outside the Mac
- **MAP 4.1** (third-party model provenance) — even if Kimi leaks logs, they leak ciphertext

### Risks

- **Accuracy regression** — FHE classifiers are ~2–5% less accurate than plaintext.
  Mitigate by falling back to plaintext only for `tier=fast` (short, non-sensitive).
- **Key rotation** — if keys leak, every cached ciphertext is compromised. Rotate quarterly.

### Prerequisites

- `concrete-ml` installed; Python 3.10 or 3.11 (FHE wheels not on 3.12 yet — may need a venv)
- At least 4GB free disk for compiled circuit + keys
- At least 8GB RAM (FHE keygen is memory-hungry)

---

## 3. Ika 2PC-MPC — **DESIGNED**

### Motivation

Today, every live trade flows through `confirmation_firewall.py` — a process-level
gate. A compromised Mac bypasses it. 2PC-MPC replaces that single point of
compromise with a cryptographic threshold: **two devices must both sign** before a
transaction can move funds. Neither device has the full private key.

### Architecture

```
┌─────────────────┐                  ┌─────────────────┐
│  Mac (commander)│                  │ Windows (GPU)   │
│  key share A    │<─── protocol ───>│  key share B    │
│                 │      (Ika)       │                 │
└────────┬────────┘                  └────────┬────────┘
         │                                    │
         └──────────── joint sig ─────────────┘
                         │
                         ▼
                  Sui blockchain
                  (or EVM via Ika bridge)
```

### Dependencies

- Ika Rust SDK (github.com/ika-network — TBD exact pip/npm ship date)
- Sui mainnet RPC endpoint (`https://fullnode.mainnet.sui.io`)
- Two signing devices (Mac + Windows already have Tailscale connectivity)

### Effort estimate: **XL (1–2 weeks)**

1. **Day 1–2** — Ika research: confirm SDK languages, key-share ceremony, transport
   protocol (likely WebRTC or mutual TLS over Tailscale).
2. **Day 3–4** — Run the key-generation ceremony on Mac + Windows. Store shares in
   respective secure enclaves (Keychain on Mac, DPAPI on Windows).
3. **Day 5–7** — Build `lib/signing/ika_cosigner.py`:
   - `propose(tx_bytes) -> proposal_id`
   - `sign(proposal_id) -> partial_sig` (runs on both devices)
   - `combine(proposal_id) -> full_sig`
4. **Day 8–9** — Replace `ConfirmationFirewall` calls for financial actions with
   a wrapper that requires both shares to sign. Telegram becomes a *second factor*
   via the commander device, not the sole gate.
5. **Day 10–14** — Integrate on Sui testnet; trade a small USDC balance; proceed
   to mainnet after 100 clean trades.

### Event bus integration

Publishes:
- `signing.proposed` — `{proposal_id, resource, amount, nonce}`
- `signing.partial` — one per device
- `signing.completed` — full signature ready
- `signing.rejected` — either device refused

### NIST controls covered

- **PR.AA-5** (authorization enforced) — no single compromised device can move funds
- **MANAGE 2.3** (incidents tracked) — every proposal + outcome on the event bus
- **RS.MI-1** (incidents contained) — a single device loss does not drain the wallet

### Risks

- **Liveness dependency** — if Windows is offline, Mac can't sign alone. Mitigate
  by running a third share on Pi rari2 (2-of-3 threshold).
- **Ceremony complexity** — initial key gen is a one-shot, high-stakes ritual.
  Practice on testnet first.

### Prerequisites

- Ika Rust SDK available (confirm current release; currently pre-v1)
- Tailscale mesh stable between Mac + Windows (already is)
- Sui CLI + mainnet RPC access
- Cold-wallet backup of each share (worst-case recovery)

---

## 4. Aztec Noir — **DESIGNED**

### Motivation

Today, if Sapphire ever graduates from paper trading to on-chain execution, the
strategy is visible: the trade routing, the limit prices, even the intent become
public in the mempool. MEV bots front-run. Aztec's Noir language lets us compile
strategies into zkSNARK-verified private smart contracts — the execution is
public, but the *logic* stays hidden.

### Architecture

```
┌─────────────────┐     compile      ┌─────────────────┐
│  strategy.nr    │ ───────────────> │   Noir circuit  │
│  (Pine → Noir)  │                  │   (.acir)       │
└─────────────────┘                  └────────┬────────┘
                                              │ deploy
                                              ▼
                                     ┌─────────────────┐
                                     │ Aztec Network   │
                                     │ (private L2)    │
                                     └────────┬────────┘
                                              │ proof
                                              ▼
                                     ┌─────────────────┐
                                     │ Ethereum L1     │
                                     │ (verifier)      │
                                     └─────────────────┘
```

### Dependencies

- Noir toolchain: `nargo` (Rust CLI)
- Aztec.nr library (Rust + TypeScript SDK)
- Aztec Sandbox (local dev L2)
- Node.js 20+ for the deploy scripts

### Effort estimate: **XL (2–3 weeks)**

1. **Week 1** — Port one existing Pine strategy (v3 Ultra, the 80%+ win-rate target)
   to Noir. Decide *what* stays private: entry/exit thresholds, position sizing
   formula, stop-loss distance. What stays public: the asset pair (for
   settlement), the total notional executed.
2. **Week 2** — Write `nargo test` coverage for the Noir circuit. Must pass
   identical input/output to the Pine version on 1,000 historical candles.
3. **Week 2–3** — Deploy to Aztec Sandbox, execute 50 trades, measure proving
   time. Expected: 3–30 seconds per trade depending on circuit complexity.
4. **Week 3** — Write a Sapphire-side helper
   `plugins/claw-sapphire/tools/aztec_execute.py` that:
   - Builds the transaction locally
   - Submits proof to Aztec
   - Waits for inclusion, publishes `trade.executed.private` on the event bus

### Event bus integration

Publishes:
- `trade.executed.private` — `{strategy_hash, pair, notional, proof_id}` (no price/logic)
- `trade.proof.generated` — `{circuit_id, proving_time_ms}`
- `trade.settled` — `{l1_tx_hash, block}`

### NIST controls covered

- **PR.DS-2** (in-transit confidentiality) — strategy logic never revealed on-chain
- **PR.PT-4** (protected communications) — MEV bots cannot front-run what they cannot see

### Risks

- **Proving time** — 3–30s is fine for swing trades, wrong for scalping.
- **Bridge risk** — funds have to leave Aztec to settle on L1; bridge hacks remain
  the dominant on-chain risk category.
- **Learning curve** — Noir is a new language; expect a flat week before productivity.

### Prerequisites

- Strong zero-knowledge / circuit background (or willingness to learn)
- Aztec mainnet availability (currently Sandbox + testnet only as of 2026-04; confirm
  status at aztec.network before scoping)
- Existing Pine strategy with clean test coverage (we have v3 Ultra)

---

## Sequencing Recommendation

| Priority | Tech | Why first |
|---|---|---|
| **Now** | x402 | Already built. Testnet → mainnet is a config change. Creates direct revenue. |
| **Q2 2026** | Zama FHE classifier | Biggest trust moat for THO customers. No on-chain risk. |
| **Q3 2026** | Ika 2PC-MPC | Required before any non-paper live trading at size. |
| **Q4 2026+** | Aztec Noir | Only meaningful if (a) on-chain trading is live and (b) MEV loss > privacy cost. |

## Event Bus is the Common Fabric

Every integration above publishes typed events on the bus. This means:

1. **Dashboard** automatically gets live streams of payment, FHE, signing, and
   on-chain events (via `/api/events/stream?types=payment.*,privacy.*,signing.*,trade.*`).
2. **NIST audit view** — the `/api/events/replay?type=<T>` endpoint produces the
   evidence artifact for each control without any extra instrumentation.
3. **Cross-integration triggers** become trivial: e.g., "when `payment.received`
   arrives for a premium Kronos endpoint, run the model in FHE mode" — three
   lines of subscriber code, not a new pipeline.

This is why the event bus ships in the same PR.

## References

- x402: <https://github.com/coinbase/x402>, <https://docs.cdp.coinbase.com/x402/welcome>
- Zama Concrete ML: <https://docs.zama.ai/concrete-ml>
- Ika Network: <https://ika.xyz>, <https://github.com/ika-network>
- Aztec Noir: <https://noir-lang.org>, <https://aztec.network>
