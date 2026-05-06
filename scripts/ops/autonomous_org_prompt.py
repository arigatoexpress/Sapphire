#!/usr/bin/env python3
"""Generate the Sapphire autonomous-org cluster prompt.

The prompt is intentionally repo-grounded and no-spend by default. It reads the
canonical org manifest, includes the current repo scope, and writes a stable
operator prompt that can be handed to Codex, Kimi, Hermes, or future agents.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import org_status  # noqa: E402

DEFAULT_MANIFEST = ROOT / "infra" / "org-repos.yaml"
DEFAULT_OUTPUT = ROOT / "docs" / "org" / "autonomous-org-cluster-prompt.md"

CI_STRATEGY_DESCRIPTIONS = {
    "sapphire_self_hosted_gate": (
        "Use the Sapphire SAPPHIRE_RUNNER gate and local CI evidence. Never add "
        "hosted-runner fallback labels."
    ),
    "local_evidence_skip_ci_bootstrap": (
        "Prefer local verification. First guardrail PRs may use [skip ci] until "
        "a no-spend runner gate lands."
    ),
    "draft_auto_deploy": (
        "Keep production-adjacent PRs draft or explicitly approved because main "
        "deploys automatically."
    ),
    "upstream_fork_local_only": (
        "Use local tests and Ari-fork branches. Do not retarget upstream/runtime "
        "surfaces without a dedicated plan."
    ),
}

SOURCE_LINKS = (
    (
        "GitHub Actions billing",
        "https://docs.github.com/en/billing/managing-billing-for-github-actions/"
        "about-billing-for-github-actions",
    ),
    (
        "GitHub self-hosted runners",
        "https://docs.github.com/en/actions/hosting-your-own-runners/about-self-hosted-runners",
    ),
    (
        "GitHub skip workflow runs",
        "https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs",
    ),
    (
        "Palantir OSDK",
        "https://www.palantir.com/docs/foundry/ontology-sdk/overview",
    ),
    (
        "Palantir Functions",
        "https://www.palantir.com/docs/foundry/functions/overview",
    ),
    (
        "Palantir External Functions",
        "https://www.palantir.com/docs/foundry/data-connection/external-functions",
    ),
    (
        "BigQuery newline-delimited JSON loads",
        "https://cloud.google.com/bigquery/docs/loading-data-cloud-storage-json",
    ),
    ("OpenAI video generation", "https://platform.openai.com/docs/guides/video-generation"),
    ("OpenAI audio", "https://platform.openai.com/docs/guides/audio"),
    ("Telegram Bot API", "https://core.telegram.org/bots/api"),
    (
        "OpenAI Agents handoffs",
        "https://openai.github.io/openai-agents-python/handoffs/",
    ),
    (
        "OpenAI Agents guardrails",
        "https://openai.github.io/openai-agents-python/guardrails/",
    ),
)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_manifest(args.manifest)
    status = org_status.collect_status(manifest, external=False)
    prompt = build_prompt(manifest, status)

    target = args.output or DEFAULT_OUTPUT
    if args.check:
        return check_prompt(target, prompt)
    if args.output:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(prompt, encoding="utf-8")
    else:
        print(prompt, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the target prompt does not match the generated prompt.",
    )
    return parser


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be a mapping: {path}")
    return data


def build_prompt(manifest: dict[str, Any], status: dict[str, Any]) -> str:
    repos = [repo for repo in manifest.get("repos", []) if isinstance(repo, dict)]
    upstream_repos = [repo for repo in manifest.get("upstream_repos", []) if isinstance(repo, dict)]
    repo_count = status.get("summary", {}).get("repo_count", len(repos))
    upstream_count = status.get("summary", {}).get("upstream_repo_count", len(upstream_repos))
    lines = [
        "# Sapphire Autonomous Org Cluster Prompt",
        "",
        "Generated from `infra/org-repos.yaml` and the no-external org status contract.",
        "Use this as the starting prompt for every Sapphire production-autonomy cluster.",
        "",
        "## Creative Mandate",
        "",
        "You are a Sapphire autonomous-org build cluster led by Codex. Your job is to",
        "turn the verified current assets into the most useful, interesting, and",
        "coherent system we can actually ship. Treat old mission statements as",
        "historical context, not a ceiling. Delete, replace, rename, collapse, and",
        "invent when tests, local verification, and rollback make the change safe.",
        "",
        "Keep the no-spend and safety floor intact: no paid GitHub Actions, no secret",
        "exposure, no live trading, and no real Telegram sends.",
        "",
        "Start every lane by running:",
        "",
        "```bash",
        "python3 scripts/ops/org_status.py --no-external --markdown",
        "git status --short --branch",
        "git worktree list",
        "```",
        "",
        "## Scope",
        "",
        f"- Active repos tracked: {repo_count}",
        f"- Upstream integrations tracked: {upstream_count}",
        f"- Manifest updated at: {manifest.get('updated_at')}",
        "",
        "| Repo | Class | Production Adjacent | CI Strategy | State |",
        "|---|---|:---:|---|---|",
    ]
    for repo in repos:
        lines.append(
            f"| `{repo.get('id')}` | {repo.get('classification')} | "
            f"{'yes' if repo.get('production_adjacent') else 'no'} | "
            f"`{repo.get('ci_strategy') or 'unspecified'}` | "
            f"{repo.get('migration_state') or '-'} |"
        )
    lines.extend(
        [
            "",
            "## No-Spend CI Rules",
            "",
            "Do not add `ubuntu-latest`, `macos-latest`, `windows-latest`, or any other",
            "hosted-runner fallback. Use one of these repo strategies:",
            "",
            "| Strategy | Operating Rule |",
            "|---|---|",
        ]
    )
    for strategy, description in CI_STRATEGY_DESCRIPTIONS.items():
        lines.append(f"| `{strategy}` | {description} |")
    lines.extend(
        [
            "",
            "For Sapphire, local CI evidence plus the `SAPPHIRE_RUNNER` workflow gate is",
            "the default. For satellites that still have hosted-runner workflows, use local",
            "verification and `[skip ci]` only for bootstrap guardrail commits; remember",
            "skip instructions can leave required checks pending.",
            "",
            "## Safety Floor",
            "",
            "- Never enable live trading, money movement, or order signing.",
            "- Never send real Telegram test messages.",
            "- Never expose, print, rotate, or broaden access to secrets.",
            "- Never mutate GCP, Foundry, DNS, Firestore, GCS, LaunchAgents, or workflows",
            "  when a dry-run, local artifact, branch, or PR can prove the change first.",
            "- Keep `/Users/aribs/Code/Sapphire` clean on `origin/main`; use",
            "  `/Users/aribs/Code/_worktrees/` for PR branches.",
            "- THO stays draft/human-approval-only because `main` auto-deploys to Cloud Run.",
            "",
            "## Deletion And Replacement",
            "",
            "- Remove dead routes, stale docs, duplicate scripts, misleading scaffolds,",
            "  unused branches, and reproducible generated clutter when they confuse the",
            "  system.",
            "- Preserve unknown WIP first with a branch, patch, stash, or quarantine;",
            "  then simplify.",
            "- Prefer one strong path over several half-maintained alternatives.",
            "- Do not ask for permission to delete local non-production cruft when the",
            "  rollback path is clear.",
            "",
            "## Cluster Lanes",
            "",
            "Lead Codex owns integration, final verification, PR bodies, and merge decisions.",
            "Workers must use disjoint write sets and must not revert other agents' edits.",
            "",
            "| Lane | Ownership | First Production-Ready Slice |",
            "|---|---|---|",
            "| Control Tower | `docs/org/**`, `scripts/ops/**`, `infra/org-repos.yaml` | Keep this prompt, no-spend CI posture, and org status current. |",
            "| Foundry / Regional | `regional-intel-workbench`, `lib/foundry`, GCP schemas | Provenance manifests, regional OODA packets, and paste-safe readiness. |",
            "| Media Factory | `lib/media/**`, media tests/docs | Dry-run image/audio/video readiness artifacts before live API calls. |",
            "| Telegram / Hermes | `hermes-agent` gateway safety and Sapphire Telegram docs | CommandGuard-gated exec paths and dry-run-safe Telegram handling. |",
            "| Data / OODA | `lib/autonomy`, status docs, dashboard APIs | Turn observed data into ranked safe review actions. |",
            "",
            "## OODA Loop",
            "",
            "Observe current repo/runtime state, source health, and artifact freshness.",
            "Orient by mapping gaps to the control tower waves. Decide the smallest tested",
            "PR that increases autonomy, auditability, or safety. Act through local tests,",
            "a branch, a PR, and a rollback note.",
            "",
            "## PR Contract",
            "",
            "Every PR body must include summary, blast radius, local test evidence, no-spend",
            "CI posture, rollback, and explicit confirmation that no live trading, real",
            "Telegram send, secret exposure, or production infrastructure mutation occurred.",
            "",
            "## Report Back",
            "",
            "Report in this order: what changed, what was verified, what remains blocked or",
            "risky, and the next one to three actions. Mention PR numbers and local test",
            "commands exactly.",
            "",
            "## Source Research",
            "",
        ]
    )
    for label, url in SOURCE_LINKS:
        lines.append(f"- [{label}]({url})")
    return "\n".join(lines) + "\n"


def check_prompt(path: Path, expected: str) -> int:
    if not path.exists():
        print(f"{path} is missing", file=sys.stderr)
        return 1
    actual = path.read_text(encoding="utf-8")
    if actual == expected:
        print(f"{path} is up to date")
        return 0
    diff = difflib.unified_diff(
        actual.splitlines(),
        expected.splitlines(),
        fromfile=str(path),
        tofile="generated",
        lineterm="",
    )
    print("\n".join(diff), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
