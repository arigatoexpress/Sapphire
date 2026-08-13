"""Trading / TA / onchain playbooks — research + gate hints (no broker I/O)."""

from __future__ import annotations

from typing import Any

# Indicator stack already used by TradingView TA machine — keep in sync.
TA_STACK: list[dict[str, Any]] = [
    {"id": "ema_trend", "tv": "Moving Average Exponential", "len": 20, "role": "trend"},
    {"id": "rsi_14", "tv": "Relative Strength Index", "len": 14, "role": "momentum"},
    {"id": "macd", "tv": "MACD", "role": "momentum_cross"},
    {"id": "bollinger", "tv": "Bollinger Bands", "len": 20, "role": "volatility"},
    {"id": "volume", "tv": "Volume", "role": "participation"},
]

PLAYBOOKS: dict[str, dict[str, Any]] = {
    "axti_options": {
        "name": "AXTI-class defined-risk options",
        "rail": "rh_agentic",
        "edge": "Short-dated catalyst options; gamma > theta; scale half at ~2×; SL −40%",
        "entry": [
            "Defined-risk long premium only (max loss = premium)",
            "DTE in [2, 21] unless thesis override",
            "Catalyst or event window tagged when possible",
            "Notional fits options day premium cap",
            "Regime not pure crisis for aggressive size",
        ],
        "manage": ["AXTI_SCALE_OUT at ~2×", "AXTI_SL at −40%", "Never hold to worthless"],
        "exit": ["Close before expiry when edge gone", "No equity re-buy of dust names"],
        "falsifiers": ["No catalyst and pure hope", "Illiquid options book", "Size > day cap"],
        "gate_codes": [
            "AXTI_DEFINED_RISK",
            "AXTI_DTE",
            "AXTI_SCALE_OUT",
            "AXTI_SL",
            "OPTIONS_DAY_CAP",
        ],
    },
    "l2_dust_experimental": {
        "name": "RH Chain L2 experimental (≤$10)",
        "rail": "rh_l2",
        "edge": "Tiny size discovery only — not a yield engine",
        "entry": [
            "Notional ≤ $10",
            "Max 1 open",
            "Dens permanent (SONNY/BINGBONG class + 0x prefixes)",
            "No crisis / risk_off meme snipes",
            "Exit liquidity assumed bad — prefer not to scale in",
        ],
        "manage": ["Tight thesis or flat; no death-by-stop on illiquid bags"],
        "exit": ["Exits allowed even if dens/dust"],
        "falsifiers": ["Honeypot / no exit", "Repeating dens tickers"],
        "gate_codes": ["DENS_BLOCK", "L2_NOTIONAL_CAP", "L2_MAX_OPEN", "REGIME_BLOCK_L2"],
    },
    "moss_session": {
        "name": "MOSS / MegaETH session grant",
        "rail": "moss",
        "edge": "Only when grant hours_left > 0",
        "entry": ["Renew grant ~1.5h before expiry", "Wallet-blind public projection"],
        "manage": ["Session-scoped; no ambient"],
        "exit": ["Grant expired → NO_TRADE"],
        "falsifiers": ["Trading after grant expiry"],
        "gate_codes": ["MOSS_GRANT"],
    },
    "hyperliquid_capped": {
        "name": "Hyperliquid hard-capped perps",
        "rail": "hyperliquid",
        "edge": "Capped notional + explicit signing gate (AU-05)",
        "entry": [
            "signing_gate_armed must be true",
            "Notional ≤ policy max (default $25 paper-safe)",
            "No ambient agent signing",
        ],
        "manage": ["Plant killswitch parity"],
        "exit": ["Attended disarm"],
        "falsifiers": ["Unsigned agent authority"],
        "gate_codes": ["HL_SIGNING_GATE", "HL_NOTIONAL_CAP"],
    },
    "regime_aware_rsi_paper": {
        "name": "RegimeAwareRSI (paper research worker)",
        "rail": "paper",
        "edge": "RSI only in risk-on / transition — see lib/analytics/strategies.py",
        "entry": ["Research worker paper_only manifest", "Walk-forward before promote"],
        "manage": ["Champion/challenger vs live evidence"],
        "exit": ["Demote if Sortino collapses"],
        "falsifiers": ["Live promote without paper shadow"],
        "gate_codes": ["paper rail only until promote"],
    },
    "tv_signal_spine": {
        "name": "TV / OHLCV / chain signal spine",
        "rail": "advisory",
        "edge": "Multi-source agreement before size (TR-01)",
        "entry": [
            "TA stack: EMA20, RSI14, MACD, BB, Volume",
            "Core symbols BTC ETH SOL HYPE ZEC preferred",
            "Timeframes 15/60/240/D",
            "Onchain snapshot status when available (dry-run ok)",
        ],
        "manage": ["Watchlist work orders — no auto-submit"],
        "exit": ["Stale sources → not observed"],
        "falsifiers": ["LLM-as-trader without spine"],
        "gate_codes": ["SIGNAL_SPINE"],
    },
    "late_cycle_preservation": {
        "name": "Late-cycle capital preservation (thesis)",
        "rail": "all",
        "edge": "Cowen-aligned: preservation before broad alt risk",
        "entry": [
            "Day loss halt",
            "Options premium day cap",
            "Prefer defined-risk",
            "Block L2 meme snipes in crisis/risk_off",
        ],
        "manage": ["Reduce size when breadth weak"],
        "exit": ["Respect invalidators in investment_thesis.yaml"],
        "falsifiers": ["Ignoring day loss halt", "YOLO L2 in crisis"],
        "gate_codes": ["DAY_LOSS_HALT", "OPTIONS_DAY_CAP", "REGIME_BLOCK_L2"],
    },
}


def list_playbooks() -> list[str]:
    return sorted(PLAYBOOKS)


def get_playbook(pid: str) -> dict[str, Any] | None:
    return PLAYBOOKS.get(pid)


def playbook_summary() -> dict[str, Any]:
    return {
        "count": len(PLAYBOOKS),
        "ids": list_playbooks(),
        "ta_stack": [x["id"] for x in TA_STACK],
    }
