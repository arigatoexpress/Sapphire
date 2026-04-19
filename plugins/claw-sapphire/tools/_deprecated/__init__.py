"""Deprecated Sapphire tools — sunset window before removal.

Each module here has a thin shim at `../{name}.py` that emits a
DeprecationWarning before delegating to the real code. Removal target is
declared in `infra/tool-registry.yaml` (`remove_in` field).
"""
