"""On-chain + macro intelligence.

Provides ChainIntelligence — a unified snapshot of crypto + macro state used
to classify market regime (RISK_ON / RISK_OFF / NEUTRAL) and drive alerts
when the regime changes.
"""

from lib.chain.intelligence import (
    ChainIntelligence,
    ChainSnapshot,
    Regime,
    RegimeClassification,
    RegimeShiftEvent,
)

__all__ = [
    "ChainIntelligence",
    "ChainSnapshot",
    "Regime",
    "RegimeClassification",
    "RegimeShiftEvent",
]
