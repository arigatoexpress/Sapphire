"""Regression guard for redacted/placeholder inference endpoint constants.

Why this file exists
--------------------
On 2026-05-30, commit ``2533b12a`` ("security: sanitize Tailscale IPs across 95
files") rewrote an *executable* default, not a doc string::

    WINDOWS_GPU = os.getenv("WINDOWS_GPU_URL", "http://100.71.10.48:11434")
    WINDOWS_GPU = os.getenv("WINDOWS_GPU_URL", "http://100.x.x.z:11434")

``100.x.x.z`` is a *syntactically valid hostname*, so it does not fail fast.
It reaches ``getaddrinfo`` and surfaces as::

    [Errno 8] nodename nor servname provided, or not known

That message names DNS, so it sends diagnosis to the network instead of to the
constant. The Windows GPU tier ran degraded on the ~90s Mac-CPU fallback for
2d23h before the cause was found, and the fix (``dc4178a0``) had already been
merged the whole time -- the long-lived ``KeepAlive`` process simply never
reloaded it.

Two more instances of the same rewrite are still in the source
(``PI_RARI1``/``PI_RARI2``), inert only because both Pi tiers currently ship
``enabled=0``. The moment either is enabled without also setting its ``*_URL``,
it reproduces the identical multi-day misdiagnosis.

These tests pin the *class* of defect, not just the three known constants:
a structurally unresolvable endpoint must be reported as ``misconfigured``
(a wrong constant) and never as ``failed`` (a broken network), because those
two words send an operator to different places.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_inference_endpoint_misconfig.py -v
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SVC_DIR = ROOT / "services" / "inference-proxy"
APP_PATH = SVC_DIR / "app.py"
MODULE_NAME = "inference_proxy_misconfig_under_test"


@pytest.fixture(scope="module")
def app_module():
    if str(SVC_DIR) not in sys.path:
        sys.path.insert(0, str(SVC_DIR))
    spec = importlib.util.spec_from_file_location(MODULE_NAME, APP_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


# ─── The placeholder detector ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "host",
    [
        "100.x.x.z",  # the exact constant that cost 2d23h
        "100.x.x.x",  # PI_RARI1 default, still in source
        "100.x.x.y",  # PI_RARI2 default, still in source
        "x.x.x.x",
        "1.2.3.x",
        "10.0.0.N",
        "placeholder.local",
        "PLACEHOLDER_HOST",
        "changeme",
        "",
    ],
)
def test_redacted_and_placeholder_hosts_are_rejected(app_module, host):
    """A value that can never resolve must be identified before it is dialled."""
    assert app_module._is_placeholder_host(host) is True, (
        f"{host!r} is unresolvable by construction but was accepted"
    )


@pytest.mark.parametrize(
    "host",
    [
        "192.168.1.61",  # the real Windows GPU
        "127.0.0.1",  # mac-local
        "10.77.0.1",  # planned Pi backplane
        "100.125.86.59",  # real tailnet IPv4
        "desktop-hfck6u9-2.tailfbdf93.ts.net",  # real tailnet name
        "api.moonshot.cn",  # kimi-cloud
        "localhost",
    ],
)
def test_legitimate_hosts_are_not_flagged(app_module, host):
    """No false positives: a real address must never be called misconfigured."""
    assert app_module._is_placeholder_host(host) is False, (
        f"{host!r} is a legitimate host but was flagged as a placeholder"
    )


# ─── Status reporting ────────────────────────────────────────────────────────


def test_misconfigured_endpoint_reports_misconfigured_not_failed(app_module, monkeypatch):
    """``failed`` blames the network; ``misconfigured`` blames the constant.

    Reporting the wrong one is what made this defect cost days, so the
    distinction is the actual deliverable.
    """
    monkeypatch.setattr(app_module, "WINDOWS_GPU", "http://100.x.x.z:11434")
    assert app_module._endpoint_status("windows-gpu") == "misconfigured"


def test_deliberately_disabled_tier_stays_disabled(app_module, monkeypatch):
    """Operator intent outranks a latent config fault.

    Surfacing a switched-off tier as broken would pin two permanent red fields
    on /health and train readers to ignore the whole surface. ``disabled`` is
    the honest word for "nobody asked this to run".
    """
    monkeypatch.setattr(app_module, "PI_RARI1", "")
    monkeypatch.setattr(app_module, "PI_RARI1_ENABLED", False)
    assert app_module._endpoint_status("pi-rari1") == "disabled"


def test_enabling_a_blank_tier_reports_misconfigured_never_failed(app_module, monkeypatch):
    """The trap closes exactly when it matters: at the moment of enabling.

    This is the regression that matters. ``failed`` would blame the network and
    reproduce the original 2d23h misdiagnosis; ``misconfigured`` points straight
    at the missing constant.
    """
    monkeypatch.setattr(app_module, "PI_RARI1", "")
    monkeypatch.setattr(app_module, "PI_RARI1_ENABLED", True)
    assert app_module._endpoint_status("pi-rari1") == "misconfigured"

    # ...and the disguised form behaves identically once enabled.
    monkeypatch.setattr(app_module, "PI_RARI1", "http://100.x.x.x:11434")
    assert app_module._endpoint_status("pi-rari1") == "misconfigured"


def test_healthy_endpoint_unaffected(app_module, monkeypatch):
    """The happy path must not regress."""
    monkeypatch.setattr(app_module, "MAC_LOCAL", "http://127.0.0.1:11434")
    monkeypatch.setattr(app_module, "_is_healthy", lambda name: True)
    assert app_module._endpoint_status("mac-local") == "healthy"


def test_no_committed_default_is_a_disguised_address(app_module):
    """Guards the committed constants, so a future sanitizer pass fails CI.

    This is the test that would have caught commit 2533b12a at review time.

    The invariant is deliberately *not* "every default is populated" -- we
    genuinely do not know the Pi addresses while the boards are unadmitted, and
    inventing one would be worse than leaving it blank. The invariant is that no
    default may be a fake that *looks* real, because that is what defeats every
    downstream check and reports itself as a DNS fault.
    """
    for const in ("WINDOWS_GPU", "PI_RARI1", "PI_RARI2", "MAC_LOCAL"):
        url = getattr(app_module, const)
        host = app_module._host_of(url)
        assert not app_module._is_redacted_address(host), (
            f"{const} default {url!r} is a disguised placeholder; a sanitizer "
            f"rewrote an executable constant as if it were documentation. Use an "
            f"empty string if the real value is unknown -- blank fails honestly."
        )


def test_blank_default_is_honest_and_reports_misconfigured(app_module):
    """A blank endpoint must be permitted as a default *and* surfaced as broken.

    Blank is the sanctioned way to say "unknown". It only stays safe because the
    status surface refuses to call it healthy.
    """
    assert app_module._is_redacted_address("") is False
    assert app_module._is_placeholder_host("") is True

    assert app_module.PI_RARI2 == "", "PI_RARI2 default should be an explicit blank"
    assert app_module._endpoint_enabled("pi-rari2") is False, (
        "pi-rari2 ships disabled, so its blank URL stays inert until enabled"
    )
    assert app_module._endpoint_misconfigured("pi-rari2") is True, (
        "a blank URL is still recognised as unusable underneath the disabled flag"
    )
