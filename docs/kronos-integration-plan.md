# Kronos Financial Model — Integration Plan
**Date:** 2026-04-14  
**Scope:** Sapphire OS integration of Kronos OHLCV foundation model  
**Source repo:** `~/Code/Kronos/` (MIT license)

---

## 1. What Is Kronos?

Kronos is an **open-source foundation model for financial candlestick (K-line) forecasting**, not an LLM. It is a decoder-only autoregressive Transformer pre-trained on OHLCV price sequences from 45+ global exchanges.

**Architecture (Two-Stage):**
- **Stage 1 — Tokenizer:** `KronosTokenizer` uses Binary Spherical Quantization (BSQuantizer) to compress continuous 6D OHLCV vectors into hierarchical discrete tokens (s1 coarse, s2 fine).
- **Stage 2 — Model:** `Kronos` decoder-only Transformer with hierarchical embeddings + temporal features (minute, hour, weekday, day, month). Predicts s1 first, then s2 conditioned on s1.

**Inputs:** Normalized OHLCV DataFrame + DatetimeIndex  
**Outputs:** Probabilistic forecast of next N candlesticks (all 6 dimensions: O, H, L, C, V, Amount), with temperature / top-k / top-p sampling

**Model Family (open-source tiers):**

| Model | Context | Params | VRAM (inference) | Notes |
|-------|---------|--------|-----------------|-------|
| Kronos-mini | 2048 bars | 4.1M | ~50 MB | Runs on CPU or Pi |
| Kronos-small | 512 bars | 24.7M | ~100 MB | Fast GPU/CPU |
| Kronos-base | 512 bars | 102.3M | ~500 MB | Best open accuracy |
| Kronos-large | 512 bars | 499.2M | ~2 GB | Closed-source |

---

## 2. Hardware Compatibility — RTX 5070 Ti (16GB VRAM)

**Verdict: Fully compatible.** The entire open-source family fits comfortably.

- Kronos-base (102M params, ~500 MB): fits in 16 GB with large batches
- Kronos-large (500M params, ~2 GB): fits in 16 GB with room for batch inference
- Auto-device detection: `cuda:0` → `mps` → `cpu` (already implemented in `KronosPredictor`)
- Fine-tuning Kronos-base on custom Sapphire data: feasible with `batch_size=128`, multi-GPU optional

**Recommended model:** `Kronos-base` (102M) for production, `Kronos-small` for low-latency signal scans.

---

## 3. Inference Server — NOT Ollama

Kronos **cannot run via Ollama.** Reasons:
1. BSQuantizer tokenizer is domain-specific (binary spherical space, not BPE/tiktoken)
2. Two-stage hierarchical prediction: s1 decoded first, s2 conditioned on s1 output
3. Requires OHLCV preprocessing: z-score normalization, timestamp feature extraction, clipping to [-5, +5]
4. A single forward pass cannot express the autoregressive OHLCV prediction loop

**Required:** Custom Python inference server. Options:

| Option | Notes |
|--------|-------|
| **Flask (built-in)** | `/Users/aribs/Code/Kronos/webui/app.py` — already exists, port 7070 |
| **FastAPI wrapper** | Better for async/production, add as `services/kronos/` |
| **Sapphire plugin tool** | Invoke via `KronosPredictor` Python API directly from plugin tools |

---

## 4. Integration Architecture

### Recommended: Kronos as a Sapphire Plugin Tool

The lowest-friction integration: a new `predict_kronos` plugin tool that wraps `KronosPredictor` and feeds it data from `sapphire_market` (OpenBB OHLCV).

```
sapphire_dispatch
    └── predict_kronos tool
            ├── sapphire_market (OpenBB OHLCV feed)
            │   └── GET /api/v1/equity/price/historical?symbol=BTC&provider=yfinance
            ├── KronosPredictor (Kronos-base, cuda:0)
            │   └── predict(df, x_ts, y_ts, pred_len=24, sample_count=5)
            └── output: OHLCV forecast DataFrame + confidence intervals
```

**NOT a new inference-proxy tier** — Kronos is task-specific (OHLCV forecasting only), not a general LLM fallback. It should be a dedicated tool, not wired into the 4-tier failover chain.

### Alternative: Sidecar Service

If Kronos needs to be accessible to multiple consumers (hermes skills, plugin tools, dashboard):

```
services/kronos/          ← FastAPI, port 11436
├── app.py                ← /predict, /health, /models
├── kronos_service.py     ← wraps KronosPredictor, model cache
└── Makefile              ← start/stop
com.sapphire.kronos.plist ← LaunchAgent
```

---

## 5. Data Requirements

Kronos requires OHLCV timeseries:
- **DataFrame columns:** `open`, `high`, `low`, `close`, optional: `volume`, `amount`
- **Timestamps:** `pd.DatetimeIndex` or `pd.Series[datetime64]`
- **Min context:** ~50–100 bars recommended (model context window: 512–2048)
- **Resolution:** any (1m, 5m, 1h, 1d) — temporal embedding handles it

**Sapphire data sources that can feed Kronos:**
- OpenBB `:6900` — `equity/price/historical` (yfinance, stocks + ETFs)
- TradingView MCP — `tv_get_candles` (any exchange, crypto perps, real-time)
- Signal logger JSONL — backtesting from historical signal data

---

## 6. Implementation Steps

### Phase 1 — Environment setup (1 day)
```bash
cd ~/Code/Kronos
pip install -r requirements.txt
# Download model weights
python -c "from model import Kronos, KronosTokenizer; Kronos.from_pretrained('NeoQuasar/Kronos-base')"
```

### Phase 2 — Plugin tool: `predict_kronos` (2 days)
Create `plugins/claw-sapphire/tools/kronos.py`:
```python
from model import Kronos, KronosTokenizer, KronosPredictor

predictor = KronosPredictor(
    Kronos.from_pretrained("NeoQuasar/Kronos-base"),
    KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base"),
    device="cuda:0",
    max_context=512,
)

def run(input_json):
    symbol = input_json["symbol"]
    pred_len = input_json.get("pred_len", 24)
    # 1. Fetch OHLCV from OpenBB
    df = fetch_ohlcv(symbol, bars=256)
    # 2. Run Kronos forecast
    forecast_df = predictor.predict(df, x_ts, y_ts, pred_len=pred_len, sample_count=5)
    # 3. Return directional bias + key levels
    return format_forecast(forecast_df)
```

### Phase 3 — Signal integration (3 days)
- Add Kronos forecast as a factor in `predict` tool (alongside RSI/MACD/BB)
- Weight: 20% in 6-factor prediction score
- Validate: backtest on historical BTC/ETH data, measure directional accuracy

### Phase 4 — Dashboard tile (1 day)
- Add "Kronos Forecast" panel to `/signals` page showing next-24h OHLCV projection
- Show confidence band (5-sample ensemble spread)

---

## 7. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Model not fine-tuned on crypto perps | Medium | Start with Kronos-base (pre-trained on multi-asset), evaluate accuracy before relying on it |
| Cold load latency (~5s on GPU) | Low | Keep model in memory as singleton service; warm on first use |
| Kronos-large is closed-source | Low | Kronos-base (102M) is sufficient for signal augmentation |
| Hugging Face download at startup | Low | Pre-download weights to `~/models/kronos/`, load from disk |
| Overfitting risk if fine-tuning | Medium | Use validation split, track Sortino on paper portfolio before live |

---

## 8. Timeline Estimate

| Phase | Effort |
|-------|--------|
| Phase 1: environment + weight download | 1 day |
| Phase 2: `predict_kronos` plugin tool | 2 days |
| Phase 3: signal integration + backtesting | 3 days |
| Phase 4: dashboard visualization | 1 day |
| **Total** | **~1 week** |

**Recommended first step:** Run `Kronos/examples/prediction_example.py` on BTC 1h OHLCV data and manually inspect directional accuracy over the last 30 days before committing to full integration.

---

## 9. Key File Paths

| File | Purpose |
|------|---------|
| `~/Code/Kronos/model/kronos.py` | `KronosPredictor` class (lines 482–661), model definition |
| `~/Code/Kronos/model/module.py` | `KronosTokenizer`, `BSQuantizer` |
| `~/Code/Kronos/model/__init__.py` | Public API exports |
| `~/Code/Kronos/examples/prediction_example.py` | Single-symbol inference example |
| `~/Code/Kronos/examples/prediction_batch_example.py` | Batch inference example |
| `~/Code/Kronos/webui/app.py` | Flask web UI (port 7070) — can use as-is |
| `~/Code/Kronos/finetune_csv/` | Fine-tuning pipeline (CSV input) |
| `~/Code/Kronos/requirements.txt` | Dependencies: torch, pandas, einops, safetensors |
