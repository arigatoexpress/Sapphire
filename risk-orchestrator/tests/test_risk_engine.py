import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("ASTER_API_KEY", "test")
os.environ.setdefault("ASTER_API_SECRET", "test")

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.append(str(SRC_ROOT))

from risk_orchestrator.models import OrderIntent
from risk_orchestrator.risk_engine import RiskEngine


@pytest.mark.parametrize(
    "portfolio",
    [
        {
            "totalWalletBalance": "1000",
            "totalUnrealizedPnL": "0",
            "maxWalletBalance": "2000",
        }
    ],
)
def test_drawdown_rejection(portfolio):
    engine = RiskEngine(portfolio)
    intent = OrderIntent(symbol="BTCUSDT", side="BUY", type="MARKET", quantity=0.01)
    result = engine.evaluate(intent, "test_bot", order_id="test")
    assert not result.approved
    assert result.reason is not None
    assert "Drawdown" in result.reason

