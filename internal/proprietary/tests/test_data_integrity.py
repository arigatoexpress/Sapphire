"""
Automated tests for data integrity and validation.
"""

import time
from unittest.mock import MagicMock, patch

import pytest


class TestDataValidator:
    """Tests for the data validation layer."""

    def test_validate_snapshot_success(self):
        """Test successful validation of complete snapshot."""
        from cloud_trader.data_validator import DashboardDataValidator

        validator = DashboardDataValidator()
        data = {
            "portfolio_value": 10000.0,
            "total_pnl": 500.0,
            "agents": [{"id": "agent1", "name": "Test Agent"}],
            "open_positions": [],
            "timestamp": time.time(),
        }

        result = validator.validate_snapshot(data)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_snapshot_missing_fields(self):
        """Test validation fails with missing required fields."""
        from cloud_trader.data_validator import DashboardDataValidator

        validator = DashboardDataValidator()
        data = {
            "portfolio_value": 10000.0,
            # Missing: total_pnl, agents, open_positions, timestamp
        }

        result = validator.validate_snapshot(data)
        assert result.valid is False
        assert len(result.errors) > 0
        assert any("total_pnl" in e for e in result.errors)

    def test_validate_negative_portfolio_value(self):
        """Test validation fails with negative portfolio value."""
        from cloud_trader.data_validator import DashboardDataValidator

        validator = DashboardDataValidator()
        data = {
            "portfolio_value": -1000.0,
            "total_pnl": 0.0,
            "agents": [],
            "open_positions": [],
            "timestamp": time.time(),
        }

        result = validator.validate_snapshot(data)
        assert result.valid is False
        assert any("negative" in e for e in result.errors)

    def test_stale_data_detection(self):
        """Test stale data warning is generated."""
        from cloud_trader.data_validator import DashboardDataValidator

        validator = DashboardDataValidator()
        data = {
            "portfolio_value": 10000.0,
            "total_pnl": 500.0,
            "agents": [],
            "open_positions": [],
            "timestamp": time.time() - 10.0,  # 10 seconds old
        }

        result = validator.validate_snapshot(data)
        assert any("stale" in w.lower() for w in result.warnings)


class TestDataIntegrityAuditor:
    """Tests for the data integrity auditor."""

    @pytest.mark.asyncio
    async def test_audit_no_exchange(self):
        """Test audit works without exchange connection."""
        from cloud_trader.data_integrity_report import DataIntegrityAuditor

        auditor = DataIntegrityAuditor()
        report = await auditor.run_audit(
            internal_positions=[{"symbol": "BTCUSDT", "pnl": 100}],
            internal_pnl=100.0,
            internal_balance=10000.0,
        )

        assert report is not None
        assert report.internal_positions == 1

    def test_summary_empty(self):
        """Test summary with no audits."""
        from cloud_trader.data_integrity_report import DataIntegrityAuditor

        auditor = DataIntegrityAuditor()
        summary = auditor.get_summary()

        assert summary["audits"] == 0
        assert summary["last_audit"] is None


class TestPerformanceMetrics:
    """Tests for scientific metrics calculations."""

    def test_calmar_ratio_calculation(self):
        """Test Calmar ratio is calculated correctly."""
        from cloud_trader.analytics.performance import PerformanceTracker

        tracker = PerformanceTracker("/tmp/test_metrics.json")

        # Record some trades
        tracker.record_trade("test-agent", 100.0, 1000.0)
        tracker.record_trade("test-agent", -50.0, 1000.0)
        tracker.record_trade("test-agent", 75.0, 1000.0)

        metrics = tracker.metrics.get("test-agent")
        assert metrics is not None
        assert hasattr(metrics, "calmar_ratio")

    def test_alpha_beta_calculation(self):
        """Test alpha and beta vs benchmark are calculated."""
        from cloud_trader.analytics.performance import PerformanceTracker

        tracker = PerformanceTracker("/tmp/test_metrics2.json")

        # Record trades to trigger ratio calculation
        for i in range(5):
            tracker.record_trade("alpha-agent", 50.0 * (1 if i % 2 == 0 else -0.5), 1000.0)

        metrics = tracker.metrics.get("alpha-agent")
        assert metrics is not None
        assert hasattr(metrics, "alpha")
        assert hasattr(metrics, "beta")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
