"""
Data Validation Layer for Sapphire Trading System.
Ensures all dashboard data is valid, non-null, and scientifically accurate.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .metrics import Counter

logger = logging.getLogger(__name__)

# Prometheus Counters for Data Integrity
DATA_VALIDATION_SUCCESS = Counter(
    "data_validation_success_total",
    "Total successful data validations",
    ["endpoint"],
)
DATA_VALIDATION_FAILURE = Counter(
    "data_validation_failure_total",
    "Total failed data validations",
    ["endpoint", "field", "reason"],
)
STALE_DATA_EVENTS = Counter(
    "stale_data_events_total",
    "Events where data is older than threshold",
    ["source"],
)


@dataclass
class ValidationResult:
    """Result of a validation check."""

    valid: bool
    errors: List[str]
    warnings: List[str]


class DashboardDataValidator:
    """Validates dashboard snapshot data before broadcast."""

    REQUIRED_FIELDS = [
        "portfolio_value",
        "total_pnl",
        "agents",
        "open_positions",
        "timestamp",
    ]

    STALE_THRESHOLD_SECONDS = 5.0

    def __init__(self):
        self.last_validation_time = 0.0

    def validate_snapshot(
        self, data: Dict[str, Any], endpoint: str = "dashboard"
    ) -> ValidationResult:
        """
        Validate a dashboard snapshot.

        Args:
            data: The snapshot dictionary to validate.
            endpoint: The endpoint name for metrics labeling.

        Returns:
            ValidationResult with valid status and any errors/warnings.
        """
        errors = []
        warnings = []

        # 1. Check required fields exist
        for field in self.REQUIRED_FIELDS:
            if field not in data or data[field] is None:
                errors.append(f"Missing required field: {field}")
                DATA_VALIDATION_FAILURE.labels(
                    endpoint=endpoint, field=field, reason="missing"
                ).inc()

        # 2. Validate portfolio_value is reasonable
        portfolio_value = data.get("portfolio_value", 0)
        if isinstance(portfolio_value, (int, float)):
            if portfolio_value < 0:
                errors.append(f"Invalid portfolio_value: {portfolio_value} (negative)")
                DATA_VALIDATION_FAILURE.labels(
                    endpoint=endpoint, field="portfolio_value", reason="negative"
                ).inc()
            elif portfolio_value == 0:
                warnings.append("portfolio_value is 0, may indicate uninitialized state")
        else:
            errors.append(f"portfolio_value is not a number: {type(portfolio_value)}")

        # 3. Validate agents is a list
        agents = data.get("agents", [])
        if not isinstance(agents, list):
            errors.append(f"agents is not a list: {type(agents)}")
            DATA_VALIDATION_FAILURE.labels(
                endpoint=endpoint, field="agents", reason="type_error"
            ).inc()

        # 4. Validate positions structure
        positions = data.get("open_positions", [])
        if isinstance(positions, list):
            for i, pos in enumerate(positions):
                if not isinstance(pos, dict):
                    errors.append(f"Position {i} is not a dict")
                    continue
                if "symbol" not in pos:
                    errors.append(f"Position {i} missing 'symbol'")
                if "pnl" not in pos:
                    warnings.append(f"Position {i} missing 'pnl' field")

        # 5. Check for stale data
        timestamp = data.get("timestamp", 0)
        if timestamp > 0:
            age = time.time() - timestamp
            if age > self.STALE_THRESHOLD_SECONDS:
                warnings.append(f"Data is stale: {age:.1f}s old")
                STALE_DATA_EVENTS.labels(source=endpoint).inc()

        # 6. Record success/failure
        if not errors:
            DATA_VALIDATION_SUCCESS.labels(endpoint=endpoint).inc()
            self.last_validation_time = time.time()

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_and_log(self, data: Dict[str, Any], endpoint: str = "dashboard") -> bool:
        """Validate and log results."""
        result = self.validate_snapshot(data, endpoint)

        if result.errors:
            logger.error(f"❌ Data validation failed: {result.errors}")
        if result.warnings:
            logger.warning(f"⚠️ Data validation warnings: {result.warnings}")
        if result.valid:
            logger.debug("✅ Data validation passed")

        return result.valid


# Global validator instance
_validator: Optional[DashboardDataValidator] = None


def get_data_validator() -> DashboardDataValidator:
    """Get the global data validator instance."""
    global _validator
    if _validator is None:
        _validator = DashboardDataValidator()
    return _validator
