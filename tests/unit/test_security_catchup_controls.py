"""Static guardrails for the credential catch-up controls."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_gitleaks_rule(rule_id: str) -> dict[str, object]:
    config = tomllib.loads((ROOT / ".gitleaks-docs.toml").read_text(encoding="utf-8"))
    for rule in config.get("rules", []):
        if rule.get("id") == rule_id:
            return rule
    raise AssertionError(f"missing gitleaks rule: {rule_id}")


def test_docs_plist_secret_rule_matches_docs_plist_excerpt() -> None:
    rule = _load_gitleaks_rule("sapphire-docs-plist-credential-value")
    path_pattern = re.compile(str(rule["path"]), re.IGNORECASE)
    value = "123456789" + ":" + "ABCdefGHIjklMNOpqrSTUvwxYZ_1234567"
    sample = f"<key>KIMI_CLAW_BOT_TOKEN</key>\n<string>{value}</string>"

    assert path_pattern.search("docs/security/example.md")
    assert not path_pattern.search("tests/fixtures/example.md")
    assert re.search(str(rule["regex"]), sample, re.IGNORECASE | re.DOTALL)


def test_dashboard_rejects_known_default_password() -> None:
    app_source = (ROOT / "services/dashboard/app.py").read_text(encoding="utf-8")

    assert re.search(r"""["']sapphire["']""", app_source)
    assert "WEAK_AUTH_PASSWORDS" in app_source
    assert "must not use a known default value" in app_source
    assert re.search(r"""parsed\.scheme not in \{["']http["'], ["']https["']\}""", app_source)
    assert (
        "os.environ.get('HOST', '127.0.0.1')" in app_source
        or 'os.environ.get("HOST", "127.0.0.1")' in app_source
    )


def test_dashboard_startup_reads_secret_file() -> None:
    start_script = (ROOT / "services/dashboard/start.sh").read_text(encoding="utf-8")

    assert (
        'DASHBOARD_PASSWORD_FILE="$HOME/.config/sapphire-secrets/dashboard_password"'
        in start_script
    )
    assert 'AUTH_PASSWORD="$(tr -d \'\\r\\n\' < "$DASHBOARD_PASSWORD_FILE")"' in start_script
    assert "export AUTH_PASSWORD" in start_script
