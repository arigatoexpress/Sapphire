from cloud_trader.config import Settings
from cloud_trader.risk import PortfolioState, RiskManager


def test_risk_manager_enforces_leverage_limit() -> None:
    settings = Settings(max_portfolio_leverage=0.2)
    risk = RiskManager(settings)

    # With balance=1000 and max_position_size_pct=0.08, max single position = 80
    portfolio = PortfolioState(balance=1000.0, total_exposure=0.0, positions={})
    assert risk.can_open_position(portfolio, notional=75.0)  # Within 8% limit

    portfolio = risk.register_fill(portfolio, "BTCUSDT", 75.0)
    assert portfolio.total_exposure == 75.0

    # Total exposure would be 75 + 75 = 150, leverage = 0.15 (within 0.2 max)
    # But single position size 75 is still within 8% limit
    assert risk.can_open_position(portfolio, notional=75.0)

    portfolio = risk.register_fill(portfolio, "ETHUSDT", 75.0)
    # Leverage now = 150/1000 = 0.15, still under 0.2

    # This should fail: adding 60 would bring leverage to 0.21 > 0.2
    assert not risk.can_open_position(portfolio, notional=60.0)
