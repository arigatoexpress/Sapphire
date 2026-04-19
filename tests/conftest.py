"""Sapphire test configuration — patches sys.path for legacy imports.

Many tests use old import paths (from src.X, from shared.X, from risk_kernel).
This conftest adds the necessary directories to sys.path so they resolve.

Also provides Python 3.10 compatibility shims for datetime.UTC and enum.StrEnum
(both introduced in 3.11). The production target is 3.11+, but this lets tests
run on 3.10 environments (CI images, sandboxes) without source changes.
"""

import datetime
import enum
import sys
import tempfile
from pathlib import Path

# --- Python 3.10 compat shims (safe no-ops on 3.11+) -------------------------
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc  # noqa: UP017

if not hasattr(enum, "StrEnum"):
    class _StrEnum(str, enum.Enum):  # noqa: UP042
        """Minimal StrEnum backport for Python <3.11."""

    enum.StrEnum = _StrEnum  # type: ignore[attr-defined]

REPO_ROOT = Path(__file__).parent.parent

# Redirect PerformanceTracker writes to a tmp dir during tests.
# Without this, signal_pipeline.py:302 writes fixture signals into
# data/performance/signals.jsonl, polluting the production performance log
# that the dashboard and analytics pipelines read.
_TEST_PERF_DIR = Path(tempfile.gettempdir()) / "sapphire-test-performance"
_TEST_PERF_DIR.mkdir(exist_ok=True)
sys.path.insert(0, str(REPO_ROOT))  # so lib.analytics resolves
import lib.analytics.performance_tracker as _pt_module  # noqa: E402

_pt_module.DATA_DIR = _TEST_PERF_DIR
_pt_module.SIGNALS_FILE = _TEST_PERF_DIR / "signals.jsonl"

# Add paths that tests expect to import from
sys.path.insert(0, str(REPO_ROOT / "lib" / "core" / "src"))  # for: from sapphire_core.X
sys.path.insert(0, str(REPO_ROOT / "lib" / "core" / "src" / "sapphire_core"))  # for: from risk_kernel
sys.path.insert(0, str(REPO_ROOT / "lib" / "telegram" / "src"))  # for: from sapphire_telegram.X
sys.path.insert(0, str(REPO_ROOT / "lib" / "telegram" / "src" / "sapphire_telegram"))  # for: from shared.X
sys.path.insert(0, str(REPO_ROOT / "lib" / "agents" / "src"))  # for: from sapphire_agents.X
sys.path.insert(0, str(REPO_ROOT / "services" / "alpha"))  # for: from src.X (alpha service — src is a package)
sys.path.insert(0, str(REPO_ROOT / "services" / "alpha" / "src"))  # for: from ci_feedback, openclaw_dispatch, collaboration.X
sys.path.insert(0, str(REPO_ROOT / "services" / "control-plane" / "app"))  # for: from control_plane
sys.path.insert(0, str(REPO_ROOT / "services" / "dashboard"))  # for: from src.X (dashboard)
sys.path.insert(0, str(REPO_ROOT / "services" / "webhook" / "src"))  # for: from receiver
sys.path.insert(0, str(REPO_ROOT))  # for: from scripts.X
