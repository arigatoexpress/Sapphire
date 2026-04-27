from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "autonomous_org_prompt.py"
MANIFEST = ROOT / "infra" / "org-repos.yaml"
PROMPT = ROOT / "docs" / "org" / "autonomous-org-cluster-prompt.md"

SPEC = importlib.util.spec_from_file_location("autonomous_org_prompt", SCRIPT)
assert SPEC and SPEC.loader
autonomous_org_prompt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(autonomous_org_prompt)


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def test_generated_prompt_mentions_every_active_repo() -> None:
    manifest = _manifest()
    status = autonomous_org_prompt.org_status.collect_status(manifest, external=False)
    prompt = autonomous_org_prompt.build_prompt(manifest, status)

    for repo in manifest["repos"]:
        assert f"`{repo['id']}`" in prompt


def test_generated_prompt_hard_codes_safety_floor() -> None:
    manifest = _manifest()
    status = autonomous_org_prompt.org_status.collect_status(manifest, external=False)
    prompt = autonomous_org_prompt.build_prompt(manifest, status)

    assert "Never enable live trading" in prompt
    assert "Never send real Telegram test messages" in prompt
    assert "THO stays draft/human-approval-only" in prompt
    assert "SAPPHIRE_RUNNER" in prompt
    assert "no paid GitHub Actions" in prompt
    assert "hosted-runner fallback" in prompt


def test_generated_prompt_does_not_expose_secret_shapes() -> None:
    manifest = _manifest()
    status = autonomous_org_prompt.org_status.collect_status(manifest, external=False)
    prompt = autonomous_org_prompt.build_prompt(manifest, status)

    forbidden = [
        r"api[_-]?key\s*[:=]",
        r"password\s*[:=]",
        r"private[_-]?key\s*[:=]",
        r"BEGIN RSA",
        r"BEGIN OPENSSH",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, prompt, flags=re.IGNORECASE)


def test_canonical_prompt_is_generated() -> None:
    manifest = _manifest()
    status = autonomous_org_prompt.org_status.collect_status(manifest, external=False)
    expected = autonomous_org_prompt.build_prompt(manifest, status)

    assert PROMPT.read_text(encoding="utf-8") == expected


def test_check_command_passes() -> None:
    completed = subprocess.run(
        ["python3", str(SCRIPT), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
