"""Cross-repo developer pulse — unified view of PRs, CI, Cloud Run, services.

Aggregates live state across Ari's working repos so a single Telegram `/dev pulse`
call (or a scheduled daily digest) surfaces everything that needs attention
without tabbing between GitHub, GCP console, and launchctl output.

Sources queried in parallel:

- GitHub: open PRs + latest CI run per repo (via `gh` CLI)
- GCP Cloud Run: latest revision + health condition per configured service
- Local launchctl: Sapphire LaunchAgents that are supposed to be running
- Local git: uncommitted state on each repo's main checkout

All calls have short timeouts; if any source is slow the tool degrades rather
than blocking. Returns a structured dict the PM bot formats into MarkdownV2.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── configuration ───────────────────────────────────────────────────────────


DEFAULT_REPOS = [
    # (owner/repo, local_path, nickname)
    ("arigatoexpress/Project-Go-Forward", Path.home() / "Code" / "Project-Go-Forward", "tho"),
    ("arigatoexpress/Sapphire", Path.home() / "Code" / "Sapphire", "sapphire"),
    ("arigatoexpress/cyber-threat-bot", Path.home() / "Code" / "cyber-threat-bot", "threat"),
    ("arigatoexpress/regional-intel-workbench", Path.home() / "Code" / "regional-intel-workbench", "intel"),
    ("arigatoexpress/crypto-tax-tracker", Path.home() / "Code" / "Cointracker", "crypto"),
]

DEFAULT_CLOUD_RUN_SERVICES = [
    # (gcp_project, region, service_name)
    ("tho-ai-agent", "us-central1", "project-go-forward"),
    ("tho-ai-agent", "us-central1", "sapphire-analytics"),
]

DEFAULT_LAUNCHAGENT_LABELS = [
    "com.sapphire.inference-proxy",
    "com.sapphire.signal-logger",
    "com.sapphire.openbb-api",
    "com.sapphire.dashboard",
    "com.sapphire.control-plane",
    "com.sapphire.regional-intel",
    "com.sapphire.logrotate",
    "com.sapphire.pm-bot",
    "ai.hermes.gateway",
]


# ── data classes ────────────────────────────────────────────────────────────


@dataclass
class RepoStatus:
    nickname: str
    full_name: str
    local_path_exists: bool
    local_branch: str | None = None
    local_dirty_count: int = 0
    open_prs: list[dict] = field(default_factory=list)
    latest_ci: dict | None = None
    error: str | None = None


@dataclass
class CloudRunStatus:
    service: str
    project: str
    latest_revision: str | None = None
    ready: bool | None = None
    url: str | None = None
    error: str | None = None


@dataclass
class ServiceStatus:
    label: str
    loaded: bool
    pid: int | None = None
    exit_code: int | None = None


@dataclass
class DevPulse:
    """Top-level result returned to callers."""

    repos: list[RepoStatus] = field(default_factory=list)
    cloud_run: list[CloudRunStatus] = field(default_factory=list)
    services: list[ServiceStatus] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "repos": [asdict(r) for r in self.repos],
            "cloud_run": [asdict(c) for c in self.cloud_run],
            "services": [asdict(s) for s in self.services],
            "errors": self.errors,
        }


# ── collectors ──────────────────────────────────────────────────────────────


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Run a command safely, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {e}"


def _gh_open_prs(full_name: str) -> tuple[list[dict], str | None]:
    if shutil.which("gh") is None:
        return [], "gh CLI not installed"
    rc, out, err = _run(
        [
            "gh", "pr", "list",
            "--repo", full_name,
            "--state", "open",
            "--json", "number,title,isDraft,author,updatedAt",
            "--limit", "10",
        ],
        timeout=8,
    )
    if rc != 0:
        return [], err.strip()[:200] or f"gh pr list rc={rc}"
    try:
        data = json.loads(out or "[]")
    except json.JSONDecodeError as e:
        return [], f"json parse: {e}"
    return [
        {
            "number": pr["number"],
            "title": pr["title"][:80],
            "draft": pr.get("isDraft", False),
            "author": (pr.get("author") or {}).get("login", ""),
            "updated_at": pr.get("updatedAt", ""),
        }
        for pr in data
    ], None


def _gh_latest_ci(full_name: str) -> tuple[dict | None, str | None]:
    if shutil.which("gh") is None:
        return None, "gh CLI not installed"
    rc, out, err = _run(
        [
            "gh", "run", "list",
            "--repo", full_name,
            "--limit", "1",
            "--json", "status,conclusion,displayTitle,createdAt,url",
        ],
        timeout=8,
    )
    if rc != 0:
        return None, err.strip()[:200] or f"gh run list rc={rc}"
    try:
        data = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None, "json parse error"
    if not data:
        return None, None
    run = data[0]
    return {
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "title": (run.get("displayTitle") or "")[:80],
        "created_at": run.get("createdAt"),
        "url": run.get("url"),
    }, None


def _local_git(repo_path: Path) -> tuple[str | None, int, str | None]:
    if not repo_path.exists() or not (repo_path / ".git").exists():
        return None, 0, None
    rc, branch, err = _run(["git", "-C", str(repo_path), "branch", "--show-current"], timeout=5)
    if rc != 0:
        return None, 0, err.strip()[:120] or None
    current = branch.strip() or None
    rc2, status_out, _ = _run(
        ["git", "-C", str(repo_path), "status", "--porcelain"], timeout=5
    )
    dirty = len(status_out.strip().splitlines()) if rc2 == 0 else 0
    return current, dirty, None


def collect_repo_status(full_name: str, local_path: Path, nickname: str) -> RepoStatus:
    status = RepoStatus(
        nickname=nickname,
        full_name=full_name,
        local_path_exists=local_path.exists(),
    )
    branch, dirty, local_err = _local_git(local_path)
    status.local_branch = branch
    status.local_dirty_count = dirty

    prs, pr_err = _gh_open_prs(full_name)
    status.open_prs = prs

    ci, ci_err = _gh_latest_ci(full_name)
    status.latest_ci = ci

    first_err = local_err or pr_err or ci_err
    if first_err:
        status.error = first_err
    return status


def collect_cloud_run_status(project: str, region: str, service: str) -> CloudRunStatus:
    if shutil.which("gcloud") is None:
        return CloudRunStatus(service=service, project=project, error="gcloud not installed")
    rc, out, err = _run(
        [
            "gcloud", "run", "services", "describe", service,
            "--region", region, "--project", project,
            "--format", "json",
        ],
        timeout=12,
    )
    if rc != 0:
        return CloudRunStatus(
            service=service, project=project, error=(err.strip()[:200] or f"rc={rc}")
        )
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return CloudRunStatus(service=service, project=project, error="json parse error")

    latest_rev = (data.get("status") or {}).get("latestReadyRevisionName")
    url = (data.get("status") or {}).get("url")
    conditions = (data.get("status") or {}).get("conditions") or []
    ready = None
    for cond in conditions:
        if cond.get("type") == "Ready":
            ready = cond.get("status") == "True"
            break
    return CloudRunStatus(
        service=service,
        project=project,
        latest_revision=latest_rev,
        url=url,
        ready=ready,
    )


def collect_service_statuses(labels: list[str]) -> list[ServiceStatus]:
    """One `launchctl list` call, grep each label out."""
    rc, out, _ = _run(["launchctl", "list"], timeout=5)
    if rc != 0:
        return [ServiceStatus(label=l, loaded=False) for l in labels]

    index: dict[str, tuple[int | None, int | None]] = {}
    for line in out.splitlines()[1:]:
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        pid_str, exit_str, label = parts
        pid = None if pid_str == "-" else (int(pid_str) if pid_str.lstrip("-").isdigit() else None)
        exit_code = int(exit_str) if exit_str.lstrip("-").isdigit() else None
        index[label] = (pid, exit_code)

    out_list = []
    for label in labels:
        if label in index:
            pid, exit_code = index[label]
            out_list.append(ServiceStatus(label=label, loaded=True, pid=pid, exit_code=exit_code))
        else:
            out_list.append(ServiceStatus(label=label, loaded=False))
    return out_list


# ── public API ──────────────────────────────────────────────────────────────


def pulse(
    repos: list[tuple[str, Path, str]] | None = None,
    cloud_run: list[tuple[str, str, str]] | None = None,
    services: list[str] | None = None,
    max_workers: int = 8,
) -> DevPulse:
    """Run every collector concurrently and return a DevPulse.

    None arguments use the defaults at the top of this module. Tests pass
    explicit lists with small counts so they stay fast + deterministic.
    """
    repo_list = repos if repos is not None else DEFAULT_REPOS
    cr_list = cloud_run if cloud_run is not None else DEFAULT_CLOUD_RUN_SERVICES
    svc_list = services if services is not None else DEFAULT_LAUNCHAGENT_LABELS

    result = DevPulse()

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dev-pulse") as ex:
        fut_to_kind: dict = {}
        for (full, path, nick) in repo_list:
            fut_to_kind[ex.submit(collect_repo_status, full, path, nick)] = ("repo", nick)
        for (proj, region, svc) in cr_list:
            fut_to_kind[ex.submit(collect_cloud_run_status, proj, region, svc)] = ("cr", svc)
        fut_to_kind[ex.submit(collect_service_statuses, svc_list)] = ("svcs", None)

        for fut in as_completed(fut_to_kind, timeout=60):
            kind, label = fut_to_kind[fut]
            try:
                res = fut.result()
            except Exception as e:
                result.errors.append(f"{kind}:{label}: {type(e).__name__}: {e}")
                continue
            if kind == "repo":
                result.repos.append(res)
            elif kind == "cr":
                result.cloud_run.append(res)
            elif kind == "svcs":
                result.services = res

    result.repos.sort(key=lambda r: r.nickname)
    result.cloud_run.sort(key=lambda c: c.service)
    return result


# ── formatting ──────────────────────────────────────────────────────────────


def _md_escape(text: str) -> str:
    """Telegram MarkdownV2 escape for the small subset we output."""
    out = []
    for ch in text:
        if ch in "_*[]()~`>#+-=|{}.!\\":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def format_markdown_v2(p: DevPulse) -> str:
    """Compact Telegram MarkdownV2 rendering of a DevPulse."""
    lines: list[str] = []
    lines.append("*dev pulse*")
    lines.append("")

    # Repos
    for r in p.repos:
        pr_count = len(r.open_prs)
        ci_emoji = "❔"
        if r.latest_ci:
            concl = (r.latest_ci.get("conclusion") or "").lower()
            status = (r.latest_ci.get("status") or "").lower()
            if status == "in_progress" or status == "queued":
                ci_emoji = "⏳"
            elif concl == "success":
                ci_emoji = "✅"
            elif concl == "failure":
                ci_emoji = "❌"
            elif concl == "cancelled":
                ci_emoji = "⚠️"
        dirty = f" ({r.local_dirty_count} uncommitted)" if r.local_dirty_count else ""
        lines.append(
            f"• *{_md_escape(r.nickname)}* {_md_escape(f'— {pr_count} PR' + ('' if pr_count == 1 else 's'))} {ci_emoji}{_md_escape(dirty)}"
        )
        for pr in r.open_prs[:3]:
            mark = "📝" if pr["draft"] else "🟢"
            lines.append(
                f"    {mark} \\#{pr['number']} {_md_escape(pr['title'])}"
            )

    # Cloud Run
    if p.cloud_run:
        lines.append("")
        lines.append("*cloud run*")
        for c in p.cloud_run:
            emoji = "✅" if c.ready else ("⚠️" if c.ready is False else "❔")
            rev = _md_escape(c.latest_revision or "unknown")
            lines.append(f"• {_md_escape(c.service)} {emoji} `{rev}`")

    # Services
    if p.services:
        lines.append("")
        lines.append("*launchagents*")
        loaded = [s for s in p.services if s.loaded]
        unloaded = [s for s in p.services if not s.loaded]
        lines.append(f"• loaded: {len(loaded)}/{len(p.services)}")
        for s in unloaded:
            lines.append(f"    ❌ {_md_escape(s.label)}")
        bad = [s for s in loaded if s.exit_code not in (None, 0)]
        for s in bad:
            lines.append(
                f"    ⚠️ {_md_escape(s.label)} exit\\={s.exit_code}"
            )

    if p.errors:
        lines.append("")
        lines.append("*errors*")
        for err in p.errors[:5]:
            lines.append(f"• {_md_escape(err)[:200]}")

    return "\n".join(lines)
