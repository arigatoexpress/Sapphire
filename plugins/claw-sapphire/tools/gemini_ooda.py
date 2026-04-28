#!/usr/bin/env python3
"""Compat shim — real implementation in tools/internal/gemini_ooda.py.

Keeps the standard `plugins/claw-sapphire/tools/<name>.py` invocation path
working (scheduled tasks, hermes skills, importlib test fixtures) while the
implementation lives alongside the rest of the internal tools.
"""

from __future__ import annotations

from pathlib import Path

_TARGET = Path(__file__).parent / "internal" / "gemini_ooda.py"

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
