import importlib.util
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
ENGINE_PATH = ROOT_DIR / "services/alpha-engine/src/strategy/engine.py"
ALPHA_ENGINE_ROOT = ROOT_DIR / "services/alpha-engine"


def _load_engine_module():
    if str(ALPHA_ENGINE_ROOT) not in sys.path:
        sys.path.insert(0, str(ALPHA_ENGINE_ROOT))
    spec = importlib.util.spec_from_file_location("sapphire_alpha_strategy_engine", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _FakeMarketData:
    def __init__(self):
        self._prices = {
            ("ASTER", "SOL"): 78.6,
            ("LIGHTER", "SOL"): 78.4,
        }

    def get_price(self, venue: str, symbol: str) -> float:
        return float(self._prices.get((venue, symbol), 0.0))


def test_execution_state_exposes_notional_controls(monkeypatch):
    module = _load_engine_module()
    monkeypatch.setenv("INTERNAL_ARB_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("INTERNAL_ARB_EXECUTION_QUANTITY", "0.02")
    monkeypatch.setenv("SAPPHIRE_INTERNAL_ARB_MIN_NOTIONAL", "5.0")
    monkeypatch.setenv("SAPPHIRE_INTERNAL_ARB_NOTIONAL_BUFFER_PCT", "0.05")
    monkeypatch.setenv("SAPPHIRE_INTERNAL_ARB_MAX_QUANTITY", "0.25")
    monkeypatch.setenv("SAPPHIRE_DEX_EXECUTION_STAGE", "full_live")

    engine = module.AlphaStrategyEngine(_FakeMarketData())
    state = engine.execution_state()

    assert state["effective_live_dispatch"] is True
    assert state["effective_quantity"] == 0.02
    assert state["min_notional"] == 5.0
    assert state["min_notional_buffer_pct"] == 0.05
    assert state["max_quantity"] == 0.25


def test_resolve_dispatch_quantity_raises_to_min_notional(monkeypatch):
    module = _load_engine_module()
    monkeypatch.setenv("INTERNAL_ARB_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("INTERNAL_ARB_EXECUTION_QUANTITY", "0.02")
    monkeypatch.setenv("SAPPHIRE_INTERNAL_ARB_MIN_NOTIONAL", "5.0")
    monkeypatch.setenv("SAPPHIRE_INTERNAL_ARB_NOTIONAL_BUFFER_PCT", "0.05")
    monkeypatch.setenv("SAPPHIRE_INTERNAL_ARB_MAX_QUANTITY", "0.25")
    monkeypatch.setenv("SAPPHIRE_DEX_EXECUTION_STAGE", "full_live")

    engine = module.AlphaStrategyEngine(_FakeMarketData())
    resolved = engine._resolve_dispatch_quantity(reference_price=78.6, baseline_quantity=0.02)

    assert resolved["adjusted"] is True
    assert resolved["blocked"] is False
    assert resolved["reason"] == "raised_to_min_notional"
    assert resolved["quantity"] >= 0.0667


def test_resolve_dispatch_quantity_blocks_when_required_exceeds_cap(monkeypatch):
    module = _load_engine_module()
    monkeypatch.setenv("INTERNAL_ARB_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("INTERNAL_ARB_EXECUTION_QUANTITY", "0.02")
    monkeypatch.setenv("SAPPHIRE_INTERNAL_ARB_MIN_NOTIONAL", "5.0")
    monkeypatch.setenv("SAPPHIRE_INTERNAL_ARB_NOTIONAL_BUFFER_PCT", "0.05")
    monkeypatch.setenv("SAPPHIRE_INTERNAL_ARB_MAX_QUANTITY", "0.05")
    monkeypatch.setenv("SAPPHIRE_DEX_EXECUTION_STAGE", "full_live")

    engine = module.AlphaStrategyEngine(_FakeMarketData())
    resolved = engine._resolve_dispatch_quantity(reference_price=78.6, baseline_quantity=0.02)

    assert resolved["blocked"] is True
    assert resolved["reason"] == "required_quantity_exceeds_cap"
    assert resolved["quantity"] == 0.0
