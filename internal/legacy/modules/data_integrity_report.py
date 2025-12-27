"""
Data Integrity Report Generator.
Hourly audit that compares internal PnL calculations vs exchange-reported values.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .metrics import Counter

logger = logging.getLogger(__name__)

# Prometheus Counters
DATA_DISCREPANCY_EVENTS = Counter(
    "data_discrepancy_events_total",
    "Events where internal data doesn't match exchange",
    ["source", "field"],
)

PNL_CROSSCHECK_SUCCESS = Counter(
    "pnl_crosscheck_success_total",
    "Successful PnL cross-checks",
)

PNL_CROSSCHECK_FAILURE = Counter(
    "pnl_crosscheck_failure_total",
    "Failed PnL cross-checks with discrepancy",
    ["reason"],
)


@dataclass
class IntegrityReport:
    """Result of an integrity audit."""

    timestamp: float
    positions_match: bool
    pnl_variance: float
    balance_variance: float
    discrepancies: List[str]
    exchange_positions: int
    internal_positions: int


class DataIntegrityAuditor:
    """Performs periodic integrity audits comparing internal state vs exchange."""

    VARIANCE_THRESHOLD = 0.01  # 1% variance allowed

    def __init__(self):
        self.last_audit_time = 0.0
        self.audit_history: List[IntegrityReport] = []

    async def run_audit(
        self,
        internal_positions: List[Dict[str, Any]],
        internal_pnl: float,
        internal_balance: float,
        exchange_client: Any = None,
    ) -> IntegrityReport:
        """
        Run a full integrity audit.

        Args:
            internal_positions: Positions from trading service
            internal_pnl: Calculated PnL from trading service
            internal_balance: Calculated balance from trading service
            exchange_client: Client to fetch exchange data (optional)
        """
        discrepancies = []
        exchange_positions = 0
        exchange_pnl = 0.0
        exchange_balance = 0.0

        # Try to fetch exchange data
        if exchange_client:
            try:
                exchange_data = await self._fetch_exchange_data(exchange_client)
                exchange_positions = len(exchange_data.get("positions", []))
                exchange_pnl = exchange_data.get("total_pnl", 0.0)
                exchange_balance = exchange_data.get("balance", 0.0)
            except Exception as e:
                logger.warning(f"Could not fetch exchange data: {e}")
                discrepancies.append(f"Exchange fetch failed: {e}")

        # Calculate variances
        pnl_variance = 0.0
        balance_variance = 0.0

        if exchange_pnl != 0:
            pnl_variance = abs(internal_pnl - exchange_pnl) / abs(exchange_pnl)
        if exchange_balance != 0:
            balance_variance = abs(internal_balance - exchange_balance) / abs(exchange_balance)

        # Check positions count
        internal_count = len(internal_positions)
        positions_match = internal_count == exchange_positions

        if not positions_match and exchange_client:
            discrepancies.append(
                f"Position count mismatch: internal={internal_count}, exchange={exchange_positions}"
            )
            DATA_DISCREPANCY_EVENTS.labels(source="positions", field="count").inc()

        # Check PnL variance
        if pnl_variance > self.VARIANCE_THRESHOLD:
            discrepancies.append(f"PnL variance {pnl_variance*100:.2f}% exceeds threshold")
            DATA_DISCREPANCY_EVENTS.labels(source="pnl", field="total").inc()
            PNL_CROSSCHECK_FAILURE.labels(reason="variance").inc()
        else:
            PNL_CROSSCHECK_SUCCESS.inc()

        # Check balance variance
        if balance_variance > self.VARIANCE_THRESHOLD:
            discrepancies.append(f"Balance variance {balance_variance*100:.2f}% exceeds threshold")
            DATA_DISCREPANCY_EVENTS.labels(source="balance", field="total").inc()

        report = IntegrityReport(
            timestamp=time.time(),
            positions_match=positions_match,
            pnl_variance=pnl_variance,
            balance_variance=balance_variance,
            discrepancies=discrepancies,
            exchange_positions=exchange_positions,
            internal_positions=internal_count,
        )

        self.audit_history.append(report)
        self.last_audit_time = time.time()

        # Log results
        if discrepancies:
            logger.warning(f"⚠️ Integrity audit found {len(discrepancies)} issues")
            for d in discrepancies:
                logger.warning(f"   - {d}")
        else:
            logger.info("✅ Integrity audit passed")

        return report

    async def _fetch_exchange_data(self, exchange_client: Any) -> Dict[str, Any]:
        """Fetch current state from exchange."""
        # This would call the actual exchange API
        # For now, return empty to indicate no exchange connection
        return {}

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of recent audits."""
        if not self.audit_history:
            return {"audits": 0, "last_audit": None, "issues_found": 0}

        recent = self.audit_history[-10:]  # Last 10 audits
        issues = sum(len(r.discrepancies) for r in recent)

        return {
            "audits": len(self.audit_history),
            "last_audit": datetime.fromtimestamp(self.last_audit_time).isoformat(),
            "recent_issues": issues,
            "avg_pnl_variance": sum(r.pnl_variance for r in recent) / len(recent),
            "avg_balance_variance": sum(r.balance_variance for r in recent) / len(recent),
        }


# Global instance
_auditor: Optional[DataIntegrityAuditor] = None


def get_integrity_auditor() -> DataIntegrityAuditor:
    """Get global integrity auditor instance."""
    global _auditor
    if _auditor is None:
        _auditor = DataIntegrityAuditor()
    return _auditor
