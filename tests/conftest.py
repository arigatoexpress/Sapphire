"""Sapphire test configuration — patches sys.path for legacy imports.

Many tests use old import paths (from src.X, from shared.X, from risk_kernel).
This conftest adds the necessary directories to sys.path so they resolve.

Also provides Python 3.10 compatibility shims for datetime.UTC and enum.StrEnum
(both introduced in 3.11). The production target is 3.11+, but this lets tests
run on 3.10 environments (CI images, sandboxes) without source changes.
"""

import datetime
import enum
import importlib.util
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

_OPTIONAL_TEST_DEPS_BY_FILE = {
    "tests/unit/test_bot_reputation.py": ("aiohttp",),
    "tests/unit/test_chat_intent.py": ("google.generativeai",),
    "tests/unit/test_collaborative_learning.py": ("aiohttp",),
    "tests/unit/test_control_plane_news_sources.py": ("feedparser",),
    "tests/unit/test_analytics_probe_sink.py": ("flask",),
    "tests/unit/test_alpha_strategy_engine.py": ("loguru",),
    "tests/unit/test_dashboard_api_cache.py": ("flask",),
    "tests/unit/test_dashboard_thesis_endpoints.py": ("flask",),
    "tests/unit/test_execution_dispatcher.py": ("aiohttp",),
    "tests/unit/test_fill_confirmation.py": ("aiohttp",),
    "tests/unit/test_forum_api_auth.py": ("aiohttp",),
    "tests/unit/test_forum_phase3.py": ("aiohttp",),
    "tests/unit/test_gateway_webhook.py": ("fastapi",),
    "tests/unit/test_market_data_aggregator.py": ("aiohttp",),
    "tests/unit/test_molthub_outreach.py": ("aiohttp",),
    "tests/unit/test_openclaw_dispatch.py": ("aiohttp", "pytest_asyncio"),
    "tests/unit/test_portfolio_tracker.py": ("loguru",),
    "tests/unit/test_prediction_markets.py": ("aiohttp",),
    "tests/unit/test_roadmap_parser.py": ("aiohttp",),
    "tests/unit/test_robinhood_chain.py": ("web3",),
    "tests/unit/test_sapphire_forum_service.py": ("aiohttp",),
    "tests/unit/test_services_openbb_api.py": ("openbb_core",),
    "tests/unit/test_signal_logger_webhook.py": ("aiohttp",),
    "tests/unit/test_skill_auditor.py": ("aiohttp",),
    "tests/unit/test_swarm_aggregation.py": ("aiohttp",),
    "tests/unit/test_task_manager.py": ("aiohttp",),
    "tests/unit/test_virustotal_skill_scanner.py": ("aiohttp",),
    "tests/unit/test_webhook_receiver.py": ("fastapi", "uvicorn"),
    "tests/unit/test_ws_dashboard.py": ("aiohttp",),
}


def _missing_optional_test_deps(collection_path: Path) -> list[str]:
    try:
        rel_path = collection_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return []
    required = _OPTIONAL_TEST_DEPS_BY_FILE.get(rel_path, ())
    missing = []
    for module in required:
        try:
            if importlib.util.find_spec(module) is None:
                missing.append(module)
        except ModuleNotFoundError:
            missing.append(module)
    return missing


def pytest_ignore_collect(collection_path: Path, config) -> bool:
    """Let under-provisioned local Pythons collect cleanly.

    The default macOS `pytest` may point at a Python without service-specific
    test dependencies installed. These files still run in the pinned test env;
    in lighter environments, avoid turning optional import gaps into collection
    failures.
    """
    return bool(_missing_optional_test_deps(Path(collection_path)))


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
sys.path.insert(
    0, str(REPO_ROOT / "lib" / "core" / "src" / "sapphire_core")
)  # for: from risk_kernel
sys.path.insert(0, str(REPO_ROOT / "lib" / "telegram" / "src"))  # for: from sapphire_telegram.X
sys.path.insert(
    0, str(REPO_ROOT / "lib" / "telegram" / "src" / "sapphire_telegram")
)  # for: from shared.X
sys.path.insert(0, str(REPO_ROOT / "lib" / "agents" / "src"))  # for: from sapphire_agents.X
sys.path.insert(
    0, str(REPO_ROOT / "services" / "alpha")
)  # for: from src.X (alpha service — src is a package)
sys.path.insert(
    0, str(REPO_ROOT / "services" / "alpha" / "src")
)  # for: from ci_feedback, openclaw_dispatch, collaboration.X
sys.path.insert(0, str(REPO_ROOT / "services" / "control-plane" / "app"))  # for: from control_plane
sys.path.insert(0, str(REPO_ROOT / "services" / "dashboard"))  # for: from src.X (dashboard)
sys.path.insert(0, str(REPO_ROOT / "services" / "webhook" / "src"))  # for: from receiver
sys.path.insert(0, str(REPO_ROOT))  # for: from scripts.X
