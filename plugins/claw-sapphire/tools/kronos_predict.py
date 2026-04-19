#!/usr/bin/env python3
"""DEPRECATED shim for `kronos_predict` — use `predict_kronos` instead.

Real implementation is retained at `tools/_deprecated/kronos_predict.py` for
the sunset window. Removal target: v0.5.0 (see `infra/tool-registry.yaml`).
"""
from __future__ import annotations

import warnings
from pathlib import Path

warnings.warn(
    "kronos_predict is deprecated. Use predict_kronos instead. "
    "Will be removed in v0.5.0.",
    DeprecationWarning,
    stacklevel=2,
)

_TARGET = Path(__file__).parent / "_deprecated" / "kronos_predict.py"

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
