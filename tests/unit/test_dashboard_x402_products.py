"""Dashboard route tests for the x402 product discovery endpoint."""

from __future__ import annotations

import base64
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"

dashboard_app = importlib.import_module("services.dashboard.app")


def _auth_header() -> dict[str, str]:
    creds = base64.b64encode(
        f"{dashboard_app.AUTH_USERNAME}:{dashboard_app.AUTH_PASSWORD}".encode()
    ).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


def test_x402_products_requires_auth() -> None:
    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as client:
        assert client.get("/api/x402/products").status_code == 401


def test_x402_products_returns_catalog_and_safety_posture() -> None:
    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as client:
        response = client.get("/api/x402/products", headers=_auth_header())

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["summary"]["live_settlement_allowed_count"] == 0
    assert payload["safety"]["real_trading_enabled"] is False
    product_ids = {product["product_id"] for product in payload["products"]}
    assert {"market_regime_report", "backtest_receipt", "prediction_market_brief"} <= product_ids
