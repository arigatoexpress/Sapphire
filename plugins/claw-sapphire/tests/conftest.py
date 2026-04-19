"""Plugin test configuration — Python 3.10 compatibility shims.

The production target is Python 3.11+, but this lets tests run on 3.10
environments (CI images, sandboxes) without modifying source code.
"""

import datetime
import enum

if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc  # noqa: UP017

if not hasattr(enum, "StrEnum"):
    class _StrEnum(str, enum.Enum):  # noqa: UP042
        """Minimal StrEnum backport for Python <3.11."""

    enum.StrEnum = _StrEnum  # type: ignore[attr-defined]
