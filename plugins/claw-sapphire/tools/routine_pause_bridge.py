"""Import bridge for Sapphire's repo-root routine pause helper.

Plugin tests add ``plugins/claw-sapphire`` to ``sys.path``. That directory has
its own ``lib`` package, which can shadow the repo-root ``lib.core`` namespace.
Load the pause helper by path when the normal import is shadowed.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path


def _load_abort_if_paused() -> Callable[..., None]:
    try:
        from lib.core.routine_pause import abort_if_paused as imported

        return imported
    except ModuleNotFoundError as exc:
        if exc.name not in {"lib.core", "lib.core.routine_pause"}:
            raise

    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "lib" / "core" / "routine_pause.py"
    spec = importlib.util.spec_from_file_location("_sapphire_routine_pause", module_path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"cannot load routine_pause from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.abort_if_paused


abort_if_paused = _load_abort_if_paused()
