"""Sapphire test configuration — patches sys.path for legacy imports.

Many tests use old import paths (from src.X, from shared.X, from risk_kernel).
This conftest adds the necessary directories to sys.path so they resolve.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

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
