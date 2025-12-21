
# Sapphire AI v2.0 - Architecture Specification

> **Status**: APPROVED (Phase 4)
> **Date**: 2025-12-21
> **Focus**: Resilience, Context Awareness, Granular Metrics

---

## 1. System Overview
Sapphire AI v2.0 is a robust, self-healing algorithmic trading system designed for **Perpetual Futures**. It prioritizes capital preservation and scientific validation over unverified "AI magic".

### Key Differentiators
1.  **Context Aware**: "Knows" the market regime (BTC Dominance, 4H Trends) before trading.
2.  **Self-Healing**: Automatic error backoff, liquidation guards, and position reconciliation.
3.  **Metric Rich**: Tracks slippage, fees, and latency granularly per trade.
4.  **Scientific**: Strategy selected via rigorous 3-phase backtesting (Control vs Hybrid vs Pure RL).

---

## 2. Core Components

### A. Trading Service (`trading_service.py`)
The central nervous system.
-   **Loop Frequency**: ~1s (Throttled)
-   **Safety**: Wraps all logic in a "Safety Sandwich" (Pre-check -> Trade -> Post-check).
-   **OrderManager**: Handles retries, timeouts, and state tracking for accurate order lifecycle.

### B. Strategy Layer (The "Brain")
**Selected Logic**: Symmetric Mean Reversion (1x Leverage)
-   **Why?** Outperformed complex RL agents (+3546% vs +36%) in testing.
-   **Long Condition**: Price < Lower Bollinger Band (20, 2.0)
-   **Short Condition**: Price > Upper Bollinger Band
-   **Exit**: Reversion to Mean (SMA 20)
-   **Filters**:
    -   **Falling Knife**: Blocks Longs if price crashes > 5% below band.
    -   **Regime**: Blocks Longs in Bear Market (BTC.D > 60% + Bearish Trend).

### C. Data, Context & Protocols
Provides "Situational Awareness" and Multi-Chain Access.
-   **Market Context**: Fetches Global Market Cap & BTC Dominance (CoinGecko).
-   **Trend**: Analyzes Higher Timeframe (4H) candles.
-   **Protocols**:
    -   **Jupiter**: Best-price routing for Solana Swaps (`jupiter_client.py`).
    -   **Drift**: Perpetual Futures on Solana (`drift_client.py`).
    -   **Symphony (Monad)**: Agentic Fund & Trading on Monad L1 (`symphony_client.py`).
-   **Resilience**: Adapters default to safe fallback if RPCs fail.

### D. Observability (`metrics.py` + `logger.py`)
-   **Structured Logging**: World-Class JSON format (Cloud Run compatible). Includes `trace_id`, `symbol`, and full stack traces.
-   **Security**: Automatic redaction of API keys/Secrets via `RedactingFilter`.
-   **Coverage**: Standardized across API, TradingService, OrderManager, RiskManager, and all Protocol Clients.
-   **Granular Metrics**:
    -   `total_fees_paid_usd` (per platform)
    -   `slippage_percentage` (realized vs expected)
    -   `trade_execution_time` (latency)
-   **Health**: `loop_error` counters, `safety_switch_state`.

---

## 3. Resilience & Self-Healing
The system is designed to "fail safe" and recover.

| Failure Scenario | Protection Mechanism |
| :--- | :--- |
| **API Failure** | Circuit Breaker (Backoff 1s -> 10s). Error logged but Loop continues. |
| **Data Feed Down** | Context falls back to "Neutral". Strategy skips trade (Safe). |
| **Liquidation Risk** | `_check_liquidation_risk` runs EVERY loop. Closes positions if < 10% margin. |
| **Stuck Order** | `OrderManager` tracks pending states and cancels stale orders. |
| **Bad Strategy** | `ExperimentTracker` monitors PnL. Can trigger `SafetySwitch` (Emergency Stop). |

---

## 4. Deployment Check
- [x] **Code**: `trading_service.py` initialized.
- [x] **Config**: `SOL-PERP` selected. 1x Leverage.
- [x] **Strategy**: Symmetric Mean Reversion (Verified).
- [x] **Safety**: Active.

**Ready for Production.**
