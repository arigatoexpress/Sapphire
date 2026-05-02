"""Path setup for megaeth_ingest service tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICE_SRC = ROOT / "services" / "megaeth-ingest" / "src"
for path in (ROOT, SERVICE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "megaeth_integration: live MegaETH testnet integration test "
        "(requires SAPPHIRE_MEGAETH_INTEGRATION=1)",
    )
