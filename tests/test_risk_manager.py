from cloud_trader.config import Settings
from cloud_trader.risk import PortfolioState, RiskManager


def test_risk_manager_enforces_leverage_limit() -> None:
    settings = Settings(max_portfolio_leverage=0.2)
    risk = RiskManager(settings)

    portfolio = PortfolioState(balance=1000.0, total_exposure=0.0, positions={})
    assert risk.can_open_position(portfolio, notional=150.0)

    portfolio = risk.register_fill(portfolio, "BTCUSDT", 150.0)
    assert portfolio.total_exposure == 150.0

    assert not risk.can_open_position(portfolio, notional=60.0)
