#!/usr/bin/env python3
"""Compat shim — real implementation in tools/internal/research.py.

Keeps the historical `plugins/claw-sapphire/tools/research.py` invocation path
working (scheduled tasks, hermes skills, importlib test fixtures) after the
tool-boundary reorganization.
"""

from __future__ import annotations

from pathlib import Path

_TARGET = Path(__file__).parent / "internal" / "research.py"

if __name__ == "__main__":
    import runpy

    runpy.run_path(str(_TARGET), run_name="__main__")
else:
    import importlib.util

    _spec = importlib.util.spec_from_file_location(__name__, _TARGET)
    assert _spec is not None and _spec.loader is not None
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    for _name in dir(_module):
        if not _name.startswith("__"):
            globals()[_name] = getattr(_module, _name)
    del importlib, _spec, _module
