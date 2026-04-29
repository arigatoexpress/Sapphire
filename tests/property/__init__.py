"""Property-based tests for the Sapphire test-rigor 0.1.0 lane.

Each module here exercises a target ``lib/`` module with `hypothesis`
strategies. The goal is to catch invariant violations that example-based
tests miss — idempotence, monotonicity, bounded outputs, locale stability.

Profiles:

* ``default`` — 100 examples per property, suitable for ``make test``.
* ``ci`` — 500 examples per property, opt-in via ``HYPOTHESIS_PROFILE=ci``.

The profiles are registered once per process in ``conftest.py``-friendly
fashion so importing any test module in this package configures hypothesis
for the rest of the suite.
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

# The default profile is intentionally modest — property tests run on every
# pytest invocation, so the per-property cost is bounded. Operators can opt
# into a heavier sweep with ``HYPOTHESIS_PROFILE=ci`` (or any other registered
# profile name) when they want a deeper search before merging.
settings.register_profile(
    "default",
    max_examples=100,
    deadline=None,  # property bodies run pure code, but `redact_text` does
                    # regex walks that occasionally bump up against the
                    # default 200ms deadline on slow CI VMs.
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
settings.register_profile(
    "ci",
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
settings.register_profile(
    "fast",
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)

_PROFILE = os.environ.get("HYPOTHESIS_PROFILE", "default")
settings.load_profile(_PROFILE if _PROFILE in ("default", "ci", "fast") else "default")
