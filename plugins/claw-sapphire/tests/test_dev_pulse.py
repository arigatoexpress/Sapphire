"""Tests for the dev_pulse tool.

All external commands (`gh`, `gcloud`, `launchctl`, `git`) are monkeypatched.
Nothing here hits the network or the local filesystem outside `tmp_path`.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import dev_pulse  # type: ignore

# ── helpers ────────────────────────────────────────────────────────────────


class FakeRun:
    """Stand-in for dev_pulse._run — dispatches on argv prefix."""

    def __init__(self):
        self.handlers: list = []

    def register(self, prefix: list[str], rc: int, stdout: str = "", stderr: str = ""):
        self.handlers.append((prefix, rc, stdout, stderr))

    def __call__(self, cmd, timeout=10):
        for prefix, rc, stdout, stderr in self.handlers:
            if cmd[: len(prefix)] == prefix:
                return rc, stdout, stderr
        return 127, "", f"no fake handler for {cmd}"


@pytest.fixture
def fake_run(monkeypatch):
    fr = FakeRun()
    monkeypatch.setattr(dev_pulse, "_run", fr)
    # Pretend both CLIs exist so shutil.which short-circuits are fine
    monkeypatch.setattr(dev_pulse.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    return fr


# ── repo status ────────────────────────────────────────────────────────────


def test_collect_repo_status_happy_path(fake_run, tmp_path):
    repo_path = tmp_path / "fake-repo"
    (repo_path / ".git").mkdir(parents=True)

    fake_run.register(
        ["git", "-C", str(repo_path), "branch", "--show-current"],
        0,
        "main\n",
    )
    fake_run.register(
        ["git", "-C", str(repo_path), "status", "--porcelain"],
        0,
        " M file_a.py\n?? file_b.py\n",
    )
    fake_run.register(
        ["gh", "pr", "list", "--repo", "arigato/test"],
        0,
        json.dumps(
            [
                {
                    "number": 42,
                    "title": "feat: thing",
                    "isDraft": False,
                    "author": {"login": "bot"},
                    "updatedAt": "2026-04-23T00:00:00Z",
                },
            ]
        ),
    )
    fake_run.register(
        ["gh", "run", "list", "--repo", "arigato/test"],
        0,
        json.dumps(
            [
                {
                    "status": "completed",
                    "conclusion": "success",
                    "displayTitle": "feat: thing",
                    "createdAt": "2026-04-23T01:00:00Z",
                    "url": "https://github.com/arigato/test/actions/runs/1",
                },
            ]
        ),
    )

    status = dev_pulse.collect_repo_status("arigato/test", repo_path, "test")
    assert status.nickname == "test"
    assert status.local_branch == "main"
    assert status.local_dirty_count == 2
    assert len(status.open_prs) == 1
    assert status.open_prs[0]["number"] == 42
    assert status.latest_ci["conclusion"] == "success"
    assert status.error is None


def test_collect_repo_status_missing_local_path(fake_run, tmp_path):
    fake_run.register(["gh", "pr", "list"], 0, "[]")
    fake_run.register(["gh", "run", "list"], 0, "[]")

    status = dev_pulse.collect_repo_status("arigato/test", tmp_path / "does-not-exist", "test")
    assert status.local_path_exists is False
    assert status.local_branch is None
    assert status.local_dirty_count == 0


def test_collect_repo_status_gh_failure_surfaces_error(fake_run, tmp_path):
    repo_path = tmp_path / "fake-repo"
    (repo_path / ".git").mkdir(parents=True)
    fake_run.register(["git", "-C", str(repo_path)], 0, "main\n")
    fake_run.register(["gh", "pr", "list"], 1, "", "auth required\n")
    fake_run.register(["gh", "run", "list"], 0, "[]")

    status = dev_pulse.collect_repo_status("arigato/test", repo_path, "test")
    assert status.error is not None
    assert "auth required" in status.error


# ── cloud run status ───────────────────────────────────────────────────────


def test_collect_cloud_run_status_happy_path(fake_run):
    fake_run.register(
        ["gcloud", "run", "services", "describe"],
        0,
        json.dumps(
            {
                "status": {
                    "latestReadyRevisionName": "svc-00055-xyz",
                    "url": "https://svc.run.app",
                    "conditions": [{"type": "Ready", "status": "True"}],
                }
            }
        ),
    )
    s = dev_pulse.collect_cloud_run_status("proj", "us-central1", "svc")
    assert s.latest_revision == "svc-00055-xyz"
    assert s.ready is True
    assert s.url == "https://svc.run.app"


def test_collect_cloud_run_status_not_ready(fake_run):
    fake_run.register(
        ["gcloud", "run", "services", "describe"],
        0,
        json.dumps(
            {
                "status": {
                    "latestReadyRevisionName": "svc-00010",
                    "conditions": [{"type": "Ready", "status": "False"}],
                }
            }
        ),
    )
    s = dev_pulse.collect_cloud_run_status("proj", "us-central1", "svc")
    assert s.ready is False


def test_collect_cloud_run_status_gcloud_error(fake_run):
    fake_run.register(
        ["gcloud", "run", "services", "describe"],
        1,
        "",
        "service not found\n",
    )
    s = dev_pulse.collect_cloud_run_status("proj", "us-central1", "missing")
    assert s.error is not None
    assert "service not found" in s.error


# ── service statuses ───────────────────────────────────────────────────────


def test_collect_service_statuses_parses_launchctl(fake_run):
    fake_run.register(
        ["launchctl", "list"],
        0,
        "PID\tStatus\tLabel\n"
        "1234\t0\tcom.sapphire.inference-proxy\n"
        "-\t0\tcom.sapphire.dashboard\n"
        "5678\t127\tai.hermes.gateway\n",
    )
    labels = [
        "com.sapphire.inference-proxy",
        "com.sapphire.dashboard",
        "ai.hermes.gateway",
        "com.sapphire.pm-bot",  # not loaded
    ]
    out = dev_pulse.collect_service_statuses(labels)
    by_label = {s.label: s for s in out}
    assert by_label["com.sapphire.inference-proxy"].loaded is True
    assert by_label["com.sapphire.inference-proxy"].pid == 1234
    assert by_label["com.sapphire.inference-proxy"].exit_code == 0
    assert by_label["com.sapphire.dashboard"].pid is None
    assert by_label["ai.hermes.gateway"].exit_code == 127
    assert by_label["com.sapphire.pm-bot"].loaded is False


def test_collect_service_statuses_launchctl_fails(fake_run):
    fake_run.register(["launchctl", "list"], 1, "", "fail")
    out = dev_pulse.collect_service_statuses(["com.sapphire.inference-proxy"])
    assert out[0].loaded is False


# ── pulse() orchestration ──────────────────────────────────────────────────


def test_pulse_runs_all_collectors(fake_run, tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)
    fake_run.register(["git", "-C"], 0, "main\n")
    fake_run.register(["gh", "pr", "list"], 0, "[]")
    fake_run.register(["gh", "run", "list"], 0, "[]")
    fake_run.register(
        ["gcloud", "run", "services", "describe"],
        0,
        json.dumps(
            {
                "status": {
                    "latestReadyRevisionName": "r1",
                    "conditions": [{"type": "Ready", "status": "True"}],
                }
            }
        ),
    )
    fake_run.register(["launchctl", "list"], 0, "PID\tStatus\tLabel\n")

    p = dev_pulse.pulse(
        repos=[("arigato/r", repo_path, "r")],
        cloud_run=[("proj", "us-central1", "svc")],
        services=["com.sapphire.fake"],
        include_trading=False,
        include_webhook_delivery=False,
    )
    assert len(p.repos) == 1
    assert len(p.cloud_run) == 1
    assert len(p.services) == 1


def test_pulse_runs_trading_and_webhook_collectors(monkeypatch):
    monkeypatch.setattr(
        dev_pulse,
        "collect_trading_status",
        lambda: dev_pulse.TradingStatus(
            last_signal_at="2026-04-24T12:00:00+00:00",
            signals_today_count=3,
            open_paper_positions=1,
            paper_portfolio_value=101000.0,
            paper_unrealized_pnl_usd=12.0,
            paper_realized_pnl_today_usd=5.0,
        ),
    )
    monkeypatch.setattr(
        dev_pulse,
        "collect_webhook_delivery_status",
        lambda db: dev_pulse.WebhookDeliveryStatus(
            partner_id_stats=[{"partner_id": "etai", "attempted_24h": 1, "success_24h": 1}],
            total_attempted_24h=1,
            total_failed_24h=0,
        ),
    )

    p = dev_pulse.pulse(
        repos=[],
        cloud_run=[],
        services=[],
        webhook_db=object(),
        max_workers=2,
    )

    assert p.trading is not None
    assert p.trading.signals_today_count == 3
    assert p.webhook_delivery is not None
    assert p.webhook_delivery.total_attempted_24h == 1


# ── trading status ─────────────────────────────────────────────────────────


def test_collect_trading_status_reads_signals_and_portfolio(tmp_path, monkeypatch):
    fixed_now = datetime(2026, 4, 28, 12, 0, 0).astimezone()

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    monkeypatch.setattr(dev_pulse, "datetime", _FrozenDatetime)
    now = fixed_now
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    (signals_dir / "today.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"timestamp": (now - timedelta(hours=1)).isoformat(), "symbol": "BTC"}),
                json.dumps(
                    {"timestamp": (now - timedelta(minutes=10)).isoformat(), "symbol": "ETH"}
                ),
            ]
        )
    )
    (signals_dir / "old.jsonl").write_text(
        json.dumps({"timestamp": (now - timedelta(days=2)).isoformat(), "symbol": "SOL"})
    )
    paper_log = tmp_path / "paper_trading.jsonl"
    paper_log.write_text(
        json.dumps(
            {
                "pipeline_id": "paper-1",
                "timestamp": now.isoformat(),
                "paper_status": "closed",
                "paper_pnl_usd": 2.5,
            }
        )
    )
    portfolio = tmp_path / "paper_portfolio.json"
    portfolio.write_text(
        json.dumps(
            {
                "capital": 101234.56,
                "positions": [{"symbol": "BTCUSDT", "unrealized_pnl_usd": 12.25}],
                "history": [{"closed_at": now.isoformat(), "pnl": 5.0, "pipeline_id": "hist-1"}],
            }
        )
    )

    status = dev_pulse.collect_trading_status(paper_log, signals_dir, portfolio)

    assert status.signals_today_count == 2
    assert status.last_signal_at == (now - timedelta(minutes=10)).isoformat()
    assert status.open_paper_positions == 1
    assert status.paper_portfolio_value == 101234.56
    assert status.paper_unrealized_pnl_usd == 12.25
    assert status.paper_realized_pnl_today_usd == 7.5


def test_collect_trading_status_handles_missing_files(tmp_path):
    status = dev_pulse.collect_trading_status(
        tmp_path / "missing-paper.jsonl",
        tmp_path / "missing-signals",
        tmp_path / "missing-portfolio.json",
    )

    assert status.last_signal_at is None
    assert status.signals_today_count == 0
    assert status.open_paper_positions == 0
    assert status.error is None


# ── webhook delivery status ────────────────────────────────────────────────


class FakeDoc:
    def __init__(self, data: dict):
        self._data = data

    def to_dict(self):
        return dict(self._data)


class FakeQuery:
    def __init__(self, docs: list[dict]):
        self.docs = docs

    def where(self, *args, **kwargs):
        return self

    def stream(self):
        return [FakeDoc(doc) for doc in self.docs]


class FakeDB:
    def __init__(self, docs: list[dict]):
        self.docs = docs

    def collection(self, name: str):
        assert name == "activities"
        return FakeQuery(self.docs)


def test_collect_webhook_delivery_status_empty_without_db():
    status = dev_pulse.collect_webhook_delivery_status(db=None)

    assert status.partner_id_stats == []
    assert status.total_attempted_24h == 0
    assert status.total_failed_24h == 0


def test_collect_webhook_delivery_status_aggregates_partner_activity():
    now = datetime.now(timezone.utc)
    db = FakeDB(
        [
            {
                "activity_type": "partner_webhook_delivery.delivered",
                "created_at": now - timedelta(hours=1),
                "metadata": {"partner_id": "etai"},
            },
            {
                "activity_type": "partner_webhook_delivery.failed",
                "created_at": now - timedelta(hours=2),
                "metadata": {"partner_id": "etai", "error": "HTTP 500"},
            },
            {
                "activity_type": "partner_webhook_delivery.attempted",
                "created_at": now - timedelta(hours=3),
                "metadata": {"partner_id": "other"},
            },
            {
                "activity_type": "partner_webhook_delivery.failed",
                "created_at": now - timedelta(days=2),
                "metadata": {"partner_id": "old", "error": "ignored"},
            },
            {"activity_type": "task_created", "created_at": now, "metadata": {}},
        ]
    )

    status = dev_pulse.collect_webhook_delivery_status(db=db, lookback_hours=24)

    assert status.total_attempted_24h == 3
    assert status.total_failed_24h == 1
    by_partner = {item["partner_id"]: item for item in status.partner_id_stats}
    assert by_partner["etai"]["attempted_24h"] == 2
    assert by_partner["etai"]["success_24h"] == 1
    assert by_partner["etai"]["last_error"] == "HTTP 500"


# ── MarkdownV2 formatter ───────────────────────────────────────────────────


def test_format_markdown_v2_escapes_special_chars():
    pulse_result = dev_pulse.DevPulse(
        repos=[
            dev_pulse.RepoStatus(
                nickname="tho",
                full_name="arigato/tho",
                local_path_exists=True,
                local_branch="main",
                local_dirty_count=3,
                open_prs=[
                    {
                        "number": 12,
                        "title": "feat: add _something_ great!",
                        "draft": False,
                        "author": "user",
                        "updated_at": "",
                    }
                ],
                latest_ci={
                    "status": "completed",
                    "conclusion": "success",
                    "title": "green",
                    "created_at": "",
                    "url": "",
                },
            ),
        ],
    )
    out = dev_pulse.format_markdown_v2(pulse_result)
    assert "✅" in out  # success CI emoji
    assert "3 uncommitted" in out.replace("\\", "")  # escaped but present
    assert "\\_" in out  # underscore escaped
    assert "\\!" in out  # exclamation escaped


def test_format_markdown_v2_shows_unloaded_services():
    pulse_result = dev_pulse.DevPulse(
        services=[
            dev_pulse.ServiceStatus(label="com.sapphire.ok", loaded=True, pid=1, exit_code=0),
            dev_pulse.ServiceStatus(label="com.sapphire.dead", loaded=False),
        ],
    )
    out = dev_pulse.format_markdown_v2(pulse_result)
    assert "1/2" in out
    assert "com\\.sapphire\\.dead" in out


def test_format_markdown_v2_handles_empty_pulse():
    out = dev_pulse.format_markdown_v2(dev_pulse.DevPulse())
    # Even with nothing to report, should not crash and starts with title
    assert out.startswith("*dev pulse*")


def test_format_markdown_v2_includes_trading_and_webhook_sections():
    pulse_result = dev_pulse.DevPulse(
        trading=dev_pulse.TradingStatus(
            last_signal_at="2026-04-24T12:00:00+00:00",
            signals_today_count=2,
            open_paper_positions=1,
            paper_portfolio_value=101000.0,
            paper_unrealized_pnl_usd=10.0,
            paper_realized_pnl_today_usd=5.0,
        ),
        webhook_delivery=dev_pulse.WebhookDeliveryStatus(
            partner_id_stats=[
                {
                    "partner_id": "etai_endpoint",
                    "attempted_24h": 3,
                    "success_24h": 2,
                    "last_error": "HTTP 500",
                }
            ],
            total_attempted_24h=3,
            total_failed_24h=1,
        ),
    )

    out = dev_pulse.format_markdown_v2(pulse_result)

    assert "*trading*" in out
    assert "signals today: 2" in out
    assert "*partner webhooks*" in out
    assert "etai\\_endpoint" in out


def test_format_morning_digest_markdown_includes_new_sections():
    pulse_result = dev_pulse.DevPulse(
        trading=dev_pulse.TradingStatus(
            last_signal_at="2026-04-24T12:00:00+00:00",
            signals_today_count=2,
            open_paper_positions=1,
            paper_portfolio_value=101000.0,
            paper_unrealized_pnl_usd=10.0,
            paper_realized_pnl_today_usd=5.0,
        ),
        webhook_delivery=dev_pulse.WebhookDeliveryStatus(
            partner_id_stats=[],
            total_attempted_24h=0,
            total_failed_24h=0,
        ),
    )

    out = dev_pulse.format_morning_digest_markdown(pulse_result)

    assert "Sapphire Morning Digest" in out
    assert "*Trading*" in out
    assert "*Partner Webhooks*" in out
