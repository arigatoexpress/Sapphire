#!/usr/bin/env python3
"""Fetch open Dependabot alerts via ``gh api`` and emit a paste-safe summary.

Closes the gap noted in issue #393: the threat-intel-sweep runbook can no
longer reach the GitHub Dependabot alerts API in some environments. This
script wraps ``gh api`` with explicit token validation, structured JSON
output, and a paste-safe markdown summary so the runbook can offload all
alert-shape diligence to a single, testable Python module.

Design constraints (matches Sapphire ops idioms):

* **Read-only.** No git writes, no PR/issue creation, no merges, no live
  trading touchpoints. The script only reads the GitHub API.
* **Token validation first.** We check ``gh auth status`` (or ``GITHUB_TOKEN``)
  before issuing the alerts call so a missing token fails loudly instead
  of silently returning ``[]``.
* **Pagination handled.** ``gh api`` is called with ``--paginate`` so we
  don't truncate at the first 30 results.
* **Paste-safe summary.** No secret values, no raw token echoes, no PII
  fields. Severity counts + top-N table only.
* **Structured JSON for machine consumers.** Stdout produces a JSON object
  ``{"summary": {...}, "alerts": [...], "markdown": "..."}`` so callers
  (the threat-intel runbook, the cloud routine, ad-hoc operators) can
  parse the output without re-shelling out to ``gh``.
* **Subprocess-injected for testability.** All ``gh`` calls go through a
  ``Runner`` callable so unit tests can mock ``gh api`` without spawning
  real processes.

Usage::

    python3 scripts/ops/dependabot_alerts_fetch.py
    python3 scripts/ops/dependabot_alerts_fetch.py --repo arigatoexpress/Sapphire
    python3 scripts/ops/dependabot_alerts_fetch.py --markdown-only
    python3 scripts/ops/dependabot_alerts_fetch.py --json-only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

DEFAULT_REPO = "arigatoexpress/Sapphire"
DEFAULT_STATE = "open"
SEVERITY_ORDER = ("critical", "high", "medium", "low", "unknown")
TOP_ALERTS_TABLE_LIMIT = 10


class DependabotFetchError(RuntimeError):
    """Raised when a ``gh`` precondition or API call fails."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[list[str]], CommandResult]


def subprocess_runner(cmd: list[str]) -> CommandResult:  # pragma: no cover — thin shim
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def validate_gh_token(*, runner: Runner = subprocess_runner) -> None:
    """Ensure ``gh`` is authenticated. Fails loudly if the token is missing.

    We deliberately use ``gh auth status`` rather than reading
    ``GITHUB_TOKEN`` directly — the token may live in keychain / 1Password
    / vault, and ``gh`` already knows how to find it.
    """
    result = runner(["gh", "auth", "status"])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        # Sanitize: never echo any token value back even if gh leaked one.
        sanitized = " ".join(detail.split())[:256]
        raise DependabotFetchError(
            f"gh auth status failed (rc={result.returncode}): {sanitized or 'no detail'}"
        )


def fetch_alerts(
    *,
    repo: str = DEFAULT_REPO,
    state: str = DEFAULT_STATE,
    runner: Runner = subprocess_runner,
) -> list[dict[str, Any]]:
    """Fetch open Dependabot alerts for ``repo`` via ``gh api --paginate``.

    Returns the parsed JSON list. Raises ``DependabotFetchError`` if the
    API call fails or returns non-list payload (e.g. ``{"message": "..."}``
    when alerts are disabled).
    """
    if not repo or "/" not in repo:
        raise DependabotFetchError(f"bad repo: {repo!r}")
    if state not in {"open", "fixed", "dismissed", "auto_dismissed"}:
        raise DependabotFetchError(f"bad state: {state!r}")
    endpoint = f"repos/{repo}/dependabot/alerts?state={state}&per_page=100"
    result = runner(["gh", "api", "--paginate", endpoint])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        sanitized = " ".join(detail.split())[:256]
        raise DependabotFetchError(
            f"gh api dependabot/alerts failed (rc={result.returncode}): {sanitized or 'no detail'}"
        )
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise DependabotFetchError(f"gh api returned invalid JSON: {exc}") from exc
    # ``gh api --paginate`` concatenates pages but we still get a flat list
    # back. If the API returned an error envelope (object with "message") we
    # bail loudly rather than silently emit an empty list.
    if isinstance(payload, dict):
        message = payload.get("message", "<no message>")
        raise DependabotFetchError(f"gh api returned error envelope: {message}")
    if not isinstance(payload, list):
        raise DependabotFetchError(
            f"gh api returned unexpected payload type: {type(payload).__name__}"
        )
    return [a for a in payload if isinstance(a, dict)]


def summarize(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute paste-safe summary counters from raw alert payloads.

    Output is a flat dict suitable for direct inclusion in a github-issue
    body or a structured JSON envelope. We never emit token values, repo
    secrets, or any PII — only severity buckets and ecosystem counts.
    """
    severity_counts: Counter[str] = Counter()
    ecosystem_counts: Counter[str] = Counter()
    package_counts: Counter[str] = Counter()
    for alert in alerts:
        adv = alert.get("security_advisory") or {}
        sev = str(adv.get("severity") or "unknown").strip().lower() or "unknown"
        if sev not in SEVERITY_ORDER:
            sev = "unknown"
        severity_counts[sev] += 1
        dep = alert.get("dependency") or {}
        pkg = dep.get("package") or {}
        eco = str(pkg.get("ecosystem") or "unknown").strip().lower() or "unknown"
        ecosystem_counts[eco] += 1
        name = str(pkg.get("name") or "unknown").strip().lower() or "unknown"
        package_counts[(eco + ":" + name)] += 1
    summary: dict[str, Any] = {
        "total_open_alerts": len(alerts),
        "by_severity": {sev: severity_counts.get(sev, 0) for sev in SEVERITY_ORDER},
        "by_ecosystem": dict(ecosystem_counts.most_common()),
        "top_packages": dict(package_counts.most_common(TOP_ALERTS_TABLE_LIMIT)),
    }
    return summary


def render_markdown(
    repo: str,
    alerts: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    """Build a paste-safe markdown digest. No secrets, no token values."""
    lines: list[str] = []
    lines.append(f"## Dependabot alerts: `{repo}` (state=open)")
    lines.append("")
    lines.append(f"- Total open: **{summary['total_open_alerts']}**")
    lines.append("- By severity:")
    for sev in SEVERITY_ORDER:
        n = summary["by_severity"].get(sev, 0)
        if n:
            lines.append(f"  - {sev}: {n}")
    if summary["by_ecosystem"]:
        lines.append("- By ecosystem:")
        for eco, n in summary["by_ecosystem"].items():
            lines.append(f"  - {eco}: {n}")
    lines.append("")
    if not alerts:
        lines.append("No open Dependabot alerts. ✅")
        return "\n".join(lines)
    lines.append(f"### Top alerts (max {TOP_ALERTS_TABLE_LIMIT})")
    lines.append("")
    lines.append("| GHSA | Severity | Ecosystem:Package | Summary |")
    lines.append("|---|---|---|---|")
    sorted_alerts = sorted(
        alerts,
        key=lambda a: (
            SEVERITY_ORDER.index(
                str((a.get("security_advisory") or {}).get("severity") or "unknown").lower()
                if str((a.get("security_advisory") or {}).get("severity") or "unknown").lower()
                in SEVERITY_ORDER
                else "unknown"
            ),
            -int(a.get("number") or 0),
        ),
    )
    for alert in sorted_alerts[:TOP_ALERTS_TABLE_LIMIT]:
        adv = alert.get("security_advisory") or {}
        ghsa = str(adv.get("ghsa_id") or "").replace("|", "\\|")[:64]
        sev = str(adv.get("severity") or "unknown").lower()
        dep = alert.get("dependency") or {}
        pkg = dep.get("package") or {}
        eco = str(pkg.get("ecosystem") or "unknown").lower()
        name = str(pkg.get("name") or "unknown").lower()
        title = str(adv.get("summary") or "").replace("\n", " ").replace("|", "\\|")
        title = title[:120]
        lines.append(f"| {ghsa} | {sev} | {eco}:{name} | {title} |")
    return "\n".join(lines)


def fetch_and_render(
    *,
    repo: str = DEFAULT_REPO,
    state: str = DEFAULT_STATE,
    runner: Runner = subprocess_runner,
) -> dict[str, Any]:
    """End-to-end pipeline: validate, fetch, summarize, render.

    Returns ``{"repo", "summary", "alerts_count", "markdown"}``. Callers
    should serialize this object to stdout — it is paste-safe by
    construction.
    """
    validate_gh_token(runner=runner)
    alerts = fetch_alerts(repo=repo, state=state, runner=runner)
    summary = summarize(alerts)
    markdown = render_markdown(repo, alerts, summary)
    return {
        "repo": repo,
        "state": state,
        "summary": summary,
        "alerts_count": len(alerts),
        "markdown": markdown,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"GitHub repo (default: {DEFAULT_REPO}).")
    parser.add_argument("--state", default=DEFAULT_STATE, help="Alert state to fetch (open|fixed|dismissed|auto_dismissed).")
    parser.add_argument("--markdown-only", action="store_true", help="Print only the markdown digest.")
    parser.add_argument("--json-only", action="store_true", help="Print only the JSON envelope.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, runner: Runner | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    runner_fn: Runner = runner if runner is not None else subprocess_runner
    try:
        result = fetch_and_render(repo=args.repo, state=args.state, runner=runner_fn)
    except DependabotFetchError as exc:
        print(f"dependabot-alerts-fetch error: {exc}", file=sys.stderr)
        return 2
    if args.markdown_only:
        print(result["markdown"])
        return 0
    if args.json_only:
        print(json.dumps({k: v for k, v in result.items() if k != "markdown"}, sort_keys=True))
        return 0
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
