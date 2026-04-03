import importlib.util
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MARKET_DATA_PATH = ROOT_DIR / "services/alpha-engine/src/feeds/market_data.py"


def _load_market_data_module():
    spec = importlib.util.spec_from_file_location("market_data_aggregator", MARKET_DATA_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_extract_lighter_ticks_uses_trade_pubdata_only(monkeypatch):
    module = _load_market_data_module()
    monkeypatch.setenv("LIGHTER_MARKET_ID", "2")
    aggregator = module.MarketDataAggregator()

    payload = [
        {
            "hash": "h-good",
            "time": "2026-02-13T00:00:00Z",
            "pubdata": {"trade_pubdata": {"market_index": 2, "price": "78.10", "size": "0.5"}},
        },
        {
            "hash": "h-wrong-market",
            "time": "2026-02-13T00:00:01Z",
            "pubdata": {"trade_pubdata": {"market_index": 3, "price": "181113", "size": "1.0"}},
        },
        {
            "hash": "h-missing-price",
            "time": "2026-02-13T00:00:02Z",
            "pubdata": {"trade_pubdata": {"market_index": 2, "taker_account_index": "181113"}},
            "price": "181113",
        },
        {
            "hash": "h-no-trade",
            "time": "2026-02-13T00:00:03Z",
            "pubdata": {"deposit_pubdata": {"account_index": "181113"}},
        },
    ]

    ticks = aggregator._extract_lighter_ticks_from_logs(payload)
    assert len(ticks) == 1
    assert ticks[0][1] == 78.10
    assert ticks[0][2] == 0.5


def test_record_tick_filters_lighter_outlier_jump(monkeypatch):
    module = _load_market_data_module()
    monkeypatch.setenv("LIGHTER_MAX_TICK_JUMP_RATIO", "2.0")
    monkeypatch.setenv("LIGHTER_TICK_JUMP_WINDOW_SECONDS", "900")
    aggregator = module.MarketDataAggregator()

    aggregator._record_tick("LIGHTER", "SOL", 100.0, timestamp=1000.0)
    aggregator._record_tick("LIGHTER", "SOL", 10000.0, timestamp=1001.0)

    ticks = list(aggregator._tick_history["LIGHTER"]["SOL"])
    assert len(ticks) == 1
    assert aggregator.get_price("LIGHTER", "SOL") == 100.0


def test_extract_lighter_price_from_logs_returns_none_without_trade_price(monkeypatch):
    module = _load_market_data_module()
    monkeypatch.setenv("LIGHTER_MARKET_ID", "2")
    aggregator = module.MarketDataAggregator()

    payload = [
        {
            "hash": "h-missing-price",
            "time": "2026-02-13T00:00:00Z",
            "pubdata": {"trade_pubdata": {"market_index": 2, "maker_account_index": "181113"}},
        }
    ]

    assert aggregator._extract_lighter_price_from_logs(payload) is None
