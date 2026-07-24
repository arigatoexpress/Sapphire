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
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── configuration ───────────────────────────────────────────────────────────


DEFAULT_REPOS = [
    # (owner/repo, local_path, nickname)
    ("arigatoexpress/Project-Go-Forward", Path.home() / "Code" / "Project-Go-Forward", "tho"),
    ("arigatoexpress/Sapphire", Path.home() / "Code" / "Sapphire", "sapphire"),
    ("arigatoexpress/cyber-threat-bot", Path.home() / "Code" / "cyber-threat-bot", "threat"),
    (
        "arigatoexpress/regional-intel-workbench",
        Path.home() / "Code" / "regional-intel-workbench",
        "intel",
    ),
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
    "com.sapphire.pm-bot-tunnel",
]

SAPPHIRE_ROOT = Path.home() / "Code" / "Sapphire"
DEFAULT_PAPER_LOG_PATH = SAPPHIRE_ROOT / "data" / "paper_trading.jsonl"
DEFAULT_SIGNALS_DIR = SAPPHIRE_ROOT / "data" / "signals"
DEFAULT_PORTFOLIO_PATH = SAPPHIRE_ROOT / "data" / "paper_portfolio.json"
THO_FIRESTORE_PROJECT = os.getenv("THO_FIRESTORE_PROJECT", "tho-ai-agent")
_AUTO_WEBHOOK_DB = object()


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
class TradingStatus:
    last_signal_at: str | None
    signals_today_count: int
    open_paper_positions: int
    paper_portfolio_value: float | None
    paper_unrealized_pnl_usd: float | None
    paper_realized_pnl_today_usd: float | None
    error: str | None = None


@dataclass
class WebhookDeliveryStatus:
    partner_id_stats: list[dict]
    total_attempted_24h: int
    total_failed_24h: int
    error: str | None = None


@dataclass
class DevPulse:
    """Top-level result returned to callers."""

    repos: list[RepoStatus] = field(default_factory=list)
    cloud_run: list[CloudRunStatus] = field(default_factory=list)
    services: list[ServiceStatus] = field(default_factory=list)
    trading: TradingStatus | None = None
    webhook_delivery: WebhookDeliveryStatus | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "repos": [asdict(r) for r in self.repos],
            "cloud_run": [asdict(c) for c in self.cloud_run],
            "services": [asdict(s) for s in self.services],
            "trading": asdict(self.trading) if self.trading else None,
            "webhook_delivery": asdict(self.webhook_delivery) if self.webhook_delivery else None,
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


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any, default_tz: timezone | None = None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=default_tz or datetime.now().astimezone().tzinfo)
    return parsed


def _jsonl_records(path: Path) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    errors: list[str] = []
    if not path.exists():
        return records, errors
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return records, [f"{path.name}: {e}"]
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}:{line_no}: json parse: {e.msg}")
            continue
        if isinstance(item, dict):
            records.append(item)
    return records, errors


def _first_float(payload: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _as_float(payload.get(key))
        if value is not None:
            return value
    return None


def _read_json_object(path: Path) -> tuple[dict, str | None]:
    if not path.exists():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {}, f"{path.name}: {e}"
    if not isinstance(data, dict):
        return {}, f"{path.name}: expected object"
    return data, None


def _gh_open_prs(full_name: str) -> tuple[list[dict], str | None]:
    if shutil.which("gh") is None:
        return [], "gh CLI not installed"
    rc, out, err = _run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            full_name,
            "--state",
            "open",
            "--json",
            "number,title,isDraft,author,updatedAt",
            "--limit",
            "10",
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
            "gh",
            "run",
            "list",
            "--repo",
            full_name,
            "--limit",
            "1",
            "--json",
            "status,conclusion,displayTitle,createdAt,url",
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
    rc2, status_out, _ = _run(["git", "-C", str(repo_path), "status", "--porcelain"], timeout=5)
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
            "gcloud",
            "run",
            "services",
            "describe",
            service,
            "--region",
            region,
            "--project",
            project,
            "--format",
            "json",
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


def collect_trading_status(
    paper_log_path: Path | None = None,
    signals_dir: Path | None = None,
    portfolio_path: Path | None = None,
) -> TradingStatus:
    """Summarize local signal and paper-trading state from disk."""
    paper_log = paper_log_path or DEFAULT_PAPER_LOG_PATH
    signal_root = signals_dir or DEFAULT_SIGNALS_DIR
    portfolio_file = portfolio_path or DEFAULT_PORTFOLIO_PATH
    local_now = datetime.now().astimezone()
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    errors: list[str] = []

    last_signal: datetime | None = None
    signals_today = 0
    if signal_root.exists():
        for path in sorted(signal_root.glob("*.jsonl")):
            records, record_errors = _jsonl_records(path)
            errors.extend(record_errors[:3])
            for record in records:
                ts = _parse_dt(record.get("timestamp"), today_start.tzinfo)
                if ts is None:
                    continue
                local_ts = ts.astimezone(today_start.tzinfo)
                if last_signal is None or ts > last_signal:
                    last_signal = ts
                if local_ts >= today_start:
                    signals_today += 1

    paper_records, paper_errors = _jsonl_records(paper_log)
    errors.extend(paper_errors[:3])
    portfolio, portfolio_error = _read_json_object(portfolio_file)
    if portfolio_error:
        errors.append(portfolio_error)

    positions = portfolio.get("positions")
    if isinstance(positions, list):
        open_positions = len([p for p in positions if isinstance(p, dict)])
    else:
        open_by_key: dict[str, dict] = {}
        for record in paper_records:
            key = str(
                record.get("pipeline_id")
                or f"{record.get('symbol')}|{record.get('strategy')}|{record.get('timestamp')}"
            )
            status_text = str(record.get("paper_status") or record.get("status") or "").lower()
            action_text = str(record.get("action") or record.get("side") or "").lower()
            has_close = (
                record.get("paper_outcome") is not None or record.get("closed_at") is not None
            )
            if (
                status_text in {"closed", "close", "filled_closed"}
                or action_text in {"close", "exit"}
                or has_close
            ):
                open_by_key.pop(key, None)
            elif status_text == "open" or action_text in {"buy", "sell", "open"}:
                open_by_key[key] = record
        open_positions = len(open_by_key)

    portfolio_value = _first_float(
        portfolio,
        ("current_value", "portfolio_value", "total_value", "equity", "capital"),
    )
    unrealized = _first_float(
        portfolio,
        ("paper_unrealized_pnl_usd", "unrealized_pnl_usd", "unrealized_pnl"),
    )
    if unrealized is None and isinstance(positions, list):
        unrealized = sum(
            value
            for item in positions
            if isinstance(item, dict)
            for value in [_first_float(item, ("unrealized_pnl_usd", "unrealized_pnl", "pnl"))]
            if value is not None
        )

    realized_today = 0.0
    seen_realized_keys: set[str] = set()
    history = portfolio.get("history")
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            ts = _parse_dt(item.get("closed_at") or item.get("timestamp"), today_start.tzinfo)
            if ts is None or ts.astimezone(today_start.tzinfo) < today_start:
                continue
            key = str(
                item.get("pipeline_id") or item.get("id") or f"history:{len(seen_realized_keys)}"
            )
            pnl = _first_float(item, ("pnl", "paper_pnl_usd", "realized_pnl_usd", "gross_pnl"))
            if pnl is not None:
                realized_today += pnl
                seen_realized_keys.add(key)

    for record in paper_records:
        ts = _parse_dt(record.get("closed_at") or record.get("timestamp"), today_start.tzinfo)
        if ts is None or ts.astimezone(today_start.tzinfo) < today_start:
            continue
        key = str(record.get("pipeline_id") or record.get("id") or "")
        if key and key in seen_realized_keys:
            continue
        pnl = _first_float(record, ("paper_pnl_usd", "pnl_usd", "realized_pnl_usd", "pnl"))
        if pnl is not None:
            realized_today += pnl

    return TradingStatus(
        last_signal_at=last_signal.isoformat() if last_signal else None,
        signals_today_count=signals_today,
        open_paper_positions=open_positions,
        paper_portfolio_value=portfolio_value,
        paper_unrealized_pnl_usd=unrealized,
        paper_realized_pnl_today_usd=realized_today,
        error="; ".join(errors[:5]) if errors else None,
    )


def _stream_docs(query: Any) -> list[Any]:
    stream = getattr(query, "stream", None)
    if callable(stream):
        return list(stream())
    return []


def _doc_data(doc: Any) -> dict:
    to_dict = getattr(doc, "to_dict", None)
    if callable(to_dict):
        data = to_dict() or {}
    elif isinstance(doc, dict):
        data = doc
    else:
        data = {}
    return data if isinstance(data, dict) else {}


def _activity_time(activity: dict, metadata: dict) -> datetime | None:
    for key in ("created_at", "timestamp", "delivered_at", "failed_at"):
        ts = _parse_dt(activity.get(key) or metadata.get(key), UTC)
        if ts is not None:
            return ts.astimezone(UTC)
    return None


def _partner_id(activity: dict, metadata: dict) -> str:
    for key in ("partner_id", "partner", "destination_partner_id", "webhook_partner_id"):
        value = activity.get(key) or metadata.get(key)
        if value:
            return str(value)
    return "unknown"


def _delivery_outcome(activity_type: str, metadata: dict) -> str:
    suffix = activity_type.split("partner_webhook_delivery.", 1)[-1].lower()
    status = str(
        metadata.get("status") or metadata.get("delivery_status") or metadata.get("outcome") or ""
    ).lower()
    text = f"{suffix} {status}"
    if any(token in text for token in ("failed", "failure", "error", "timeout")):
        return "failed"
    if any(token in text for token in ("success", "succeeded", "delivered", "ok")):
        return "success"
    return "attempted"


def _last_error(activity: dict, metadata: dict) -> str | None:
    for key in ("last_error", "error", "error_message", "response_error", "exception"):
        value = activity.get(key) or metadata.get(key)
        if value:
            return str(value)[:240]
    return None


def _get_firestore_db() -> Any | None:
    try:
        from google.cloud import firestore  # type: ignore
    except Exception:
        return None
    try:
        return firestore.Client(project=THO_FIRESTORE_PROJECT)
    except Exception as e:
        logger.warning("Firestore client unavailable: %s", e)
        return None


def _activity_query(db: Any, cutoff: datetime) -> Any:
    query = db.collection("activities")
    where = getattr(query, "where", None)
    if not callable(where):
        return query
    try:
        from google.cloud.firestore_v1 import FieldFilter  # type: ignore

        return where(filter=FieldFilter("created_at", ">=", cutoff))
    except Exception:
        try:
            return where("created_at", ">=", cutoff)
        except Exception:
            return query


def collect_webhook_delivery_status(
    db=None,
    lookback_hours: int = 24,
) -> WebhookDeliveryStatus:
    """Summarize THO partner webhook delivery audit entries from Firestore."""
    if db is None:
        return WebhookDeliveryStatus(partner_id_stats=[], total_attempted_24h=0, total_failed_24h=0)

    cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
    stats: dict[str, dict] = {}
    total_attempted = 0
    total_failed = 0

    try:
        docs = _stream_docs(_activity_query(db, cutoff))
    except Exception as e:
        return WebhookDeliveryStatus(
            partner_id_stats=[],
            total_attempted_24h=0,
            total_failed_24h=0,
            error=f"{type(e).__name__}: {e}",
        )

    for doc in docs:
        activity = _doc_data(doc)
        activity_type = str(activity.get("activity_type") or "")
        if not activity_type.startswith("partner_webhook_delivery."):
            continue
        metadata = activity.get("metadata") if isinstance(activity.get("metadata"), dict) else {}
        created_at = _activity_time(activity, metadata)
        if created_at is not None and created_at < cutoff:
            continue
        partner_id = _partner_id(activity, metadata)
        partner = stats.setdefault(
            partner_id,
            {
                "partner_id": partner_id,
                "attempted_24h": 0,
                "success_24h": 0,
                "last_delivered_at": None,
                "last_failure_at": None,
                "last_error": None,
            },
        )
        total_attempted += 1
        partner["attempted_24h"] += 1

        outcome = _delivery_outcome(activity_type, metadata)
        if outcome == "success":
            partner["success_24h"] += 1
            if created_at is not None:
                current = _parse_dt(partner.get("last_delivered_at"), UTC)
                if current is None or created_at > current:
                    partner["last_delivered_at"] = created_at.isoformat()
        elif outcome == "failed":
            total_failed += 1
            error = _last_error(activity, metadata)
            if error:
                partner["last_error"] = error
            if created_at is not None:
                current = _parse_dt(partner.get("last_failure_at"), UTC)
                if current is None or created_at > current:
                    partner["last_failure_at"] = created_at.isoformat()

    partner_stats = sorted(
        stats.values(),
        key=lambda item: (-int(item["attempted_24h"]), str(item["partner_id"])),
    )
    return WebhookDeliveryStatus(
        partner_id_stats=partner_stats,
        total_attempted_24h=total_attempted,
        total_failed_24h=total_failed,
    )


# ── public API ──────────────────────────────────────────────────────────────


def pulse(
    repos: list[tuple[str, Path, str]] | None = None,
    cloud_run: list[tuple[str, str, str]] | None = None,
    services: list[str] | None = None,
    include_trading: bool = True,
    include_webhook_delivery: bool = True,
    webhook_db: Any = _AUTO_WEBHOOK_DB,
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
        for full, path, nick in repo_list:
            fut_to_kind[ex.submit(collect_repo_status, full, path, nick)] = ("repo", nick)
        for proj, region, svc in cr_list:
            fut_to_kind[ex.submit(collect_cloud_run_status, proj, region, svc)] = ("cr", svc)
        fut_to_kind[ex.submit(collect_service_statuses, svc_list)] = ("svcs", None)
        if include_trading:
            fut_to_kind[ex.submit(collect_trading_status)] = ("trading", None)
        if include_webhook_delivery:
            db = _get_firestore_db() if webhook_db is _AUTO_WEBHOOK_DB else webhook_db
            fut_to_kind[ex.submit(collect_webhook_delivery_status, db)] = ("webhook", None)

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
            elif kind == "trading":
                result.trading = res
            elif kind == "webhook":
                result.webhook_delivery = res

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
            lines.append(f"    {mark} \\#{pr['number']} {_md_escape(pr['title'])}")

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
            lines.append(f"    ⚠️ {_md_escape(s.label)} exit\\={s.exit_code}")

    if p.trading:
        t = p.trading
        lines.append("")
        lines.append("*trading*")
        last_signal = t.last_signal_at or "none"
        value = "unknown" if t.paper_portfolio_value is None else f"${t.paper_portfolio_value:,.2f}"
        unrealized = (
            "unknown"
            if t.paper_unrealized_pnl_usd is None
            else f"${t.paper_unrealized_pnl_usd:,.2f}"
        )
        realized = (
            "unknown"
            if t.paper_realized_pnl_today_usd is None
            else f"${t.paper_realized_pnl_today_usd:,.2f}"
        )
        lines.append(f"• signals today: {t.signals_today_count}")
        lines.append(f"• last signal: `{_md_escape(last_signal)}`")
        lines.append(f"• paper: {_md_escape(value)}, open: {t.open_paper_positions}")
        lines.append(
            f"• PnL: unrealized {_md_escape(unrealized)}, realized today {_md_escape(realized)}"
        )
        if t.error:
            lines.append(f"    ⚠️ {_md_escape(t.error)[:200]}")

    if p.webhook_delivery:
        w = p.webhook_delivery
        lines.append("")
        lines.append("*partner webhooks*")
        lines.append(f"• 24h: {w.total_attempted_24h} attempted, {w.total_failed_24h} failed")
        for partner in w.partner_id_stats[:5]:
            partner_id = _md_escape(str(partner.get("partner_id") or "unknown"))
            attempted = int(partner.get("attempted_24h") or 0)
            success = int(partner.get("success_24h") or 0)
            last_error = partner.get("last_error")
            suffix = f" — {_md_escape(str(last_error)[:80])}" if last_error else ""
            lines.append(f"    • {partner_id}: {success}/{attempted} ok{suffix}")
        if w.error:
            lines.append(f"    ⚠️ {_md_escape(w.error)[:200]}")

    if p.errors:
        lines.append("")
        lines.append("*errors*")
        for err in p.errors[:5]:
            lines.append(f"• {_md_escape(err)[:200]}")

    return "\n".join(lines)


def _plain_md(text: Any) -> str:
    """Small Markdown-v1 escape for messages sent through notify.py."""
    return (
        str(text).replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
    )


def format_morning_digest_markdown(p: DevPulse) -> str:
    """Rich Telegram digest for notify.py, which uses Telegram Markdown."""
    now = datetime.now().astimezone()
    lines: list[str] = [
        f"*Sapphire Morning Digest* — {_plain_md(now.strftime('%a %b %d, %H:%M'))}",
        "",
    ]

    open_prs = sum(len(r.open_prs) for r in p.repos)
    dirty_repos = [r.nickname for r in p.repos if r.local_dirty_count]
    failing_ci = [
        r.nickname
        for r in p.repos
        if r.latest_ci and str(r.latest_ci.get("conclusion") or "").lower() == "failure"
    ]
    lines.append("*Engineering*")
    lines.append(
        f"- PRs: {open_prs}; dirty repos: {len(dirty_repos)}; failing CI: {len(failing_ci)}"
    )
    if dirty_repos:
        lines.append(f"- Dirty: {_plain_md(', '.join(dirty_repos[:6]))}")
    if failing_ci:
        lines.append(f"- Failing CI: {_plain_md(', '.join(failing_ci[:6]))}")

    if p.cloud_run:
        ready = len([c for c in p.cloud_run if c.ready is True])
        lines.append("")
        lines.append("*Cloud Run*")
        lines.append(f"- Ready: {ready}/{len(p.cloud_run)}")
        for c in p.cloud_run:
            state = "ready" if c.ready else ("not ready" if c.ready is False else "unknown")
            lines.append(f"- {_plain_md(c.service)}: {_plain_md(state)}")

    if p.services:
        loaded = [s for s in p.services if s.loaded]
        bad = [s for s in p.services if (not s.loaded) or s.exit_code not in (None, 0)]
        lines.append("")
        lines.append("*LaunchAgents*")
        lines.append(f"- Loaded: {len(loaded)}/{len(p.services)}; attention: {len(bad)}")
        for s in bad[:8]:
            state = "unloaded" if not s.loaded else f"exit={s.exit_code}"
            lines.append(f"- `{_plain_md(s.label)}` {_plain_md(state)}")

    if p.trading:
        t = p.trading
        value = "unknown" if t.paper_portfolio_value is None else f"${t.paper_portfolio_value:,.2f}"
        unrealized = (
            "unknown"
            if t.paper_unrealized_pnl_usd is None
            else f"${t.paper_unrealized_pnl_usd:,.2f}"
        )
        realized = (
            "unknown"
            if t.paper_realized_pnl_today_usd is None
            else f"${t.paper_realized_pnl_today_usd:,.2f}"
        )
        lines.append("")
        lines.append("*Trading*")
        lines.append(
            f"- Signals today: {t.signals_today_count}; last: {_plain_md(t.last_signal_at or 'none')}"
        )
        lines.append(f"- Paper value: {_plain_md(value)}; open positions: {t.open_paper_positions}")
        lines.append(
            f"- PnL: unrealized {_plain_md(unrealized)}; realized today {_plain_md(realized)}"
        )
        if t.error:
            lines.append(f"- Trading read warning: {_plain_md(t.error[:200])}")

    if p.webhook_delivery:
        w = p.webhook_delivery
        lines.append("")
        lines.append("*Partner Webhooks*")
        lines.append(f"- 24h attempted: {w.total_attempted_24h}; failed: {w.total_failed_24h}")
        if not w.partner_id_stats:
            lines.append("- No partner delivery events found in the lookback window")
        for partner in w.partner_id_stats[:6]:
            attempted = int(partner.get("attempted_24h") or 0)
            success = int(partner.get("success_24h") or 0)
            last_error = partner.get("last_error")
            suffix = f"; last error: {_plain_md(str(last_error)[:120])}" if last_error else ""
            lines.append(
                f"- {_plain_md(partner.get('partner_id') or 'unknown')}: {success}/{attempted} ok{suffix}"
            )
        if w.error:
            lines.append(f"- Webhook audit warning: {_plain_md(w.error[:200])}")

    if p.errors:
        lines.append("")
        lines.append("*Collector Errors*")
        for err in p.errors[:5]:
            lines.append(f"- {_plain_md(err[:200])}")

    return "\n".join(lines)
