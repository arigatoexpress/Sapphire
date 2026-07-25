"""Data providers that back the Telegram inline menus.

Each provider is a zero-argument callable returning already-escaped
MarkdownV2 text. ``build_providers()`` assembles the map that
``lib.telegram.menus.MenuContext`` consumes.

Every provider is defensive: a missing data file, an unconfigured
credential, or an import error yields a readable "not available"
message rather than an exception. A menu that half-works is far better
than a menu that 500s — the user is looking at a phone screen, not a
stack trace.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from lib.telegram import formatters as fmt
from lib.telegram import settings_store, system_snapshot

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def _unavailable(what: str, detail: str = "") -> str:
    body = f"{fmt.bold(what)}\n\n{fmt.esc('Data source is not available right now.')}"
    if detail:
        body += f"\n{fmt.esc(detail)}"
    return body


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


def _portfolio_rows_from_payload(payload: dict) -> list[fmt.PortfolioRow]:
    rows: list[fmt.PortfolioRow] = []
    holdings = payload.get("holdings")
    if not isinstance(holdings, list):
        return rows
    for item in holdings:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or item.get("asset") or "").strip()
        if not symbol:
            continue
        value = item.get("market_value")
        if value is None:
            value = item.get("value_usd")
        delta = item.get("change_pct_24h")
        if delta is None:
            delta = item.get("delta_pct")
        rows.append(
            fmt.PortfolioRow(
                symbol=symbol,
                value_usd=float(value) if isinstance(value, (int, float)) else None,
                delta_pct=float(delta) if isinstance(delta, (int, float)) else None,
                venue=str(item.get("venue") or ""),
            )
        )
    return rows


def portfolio_overview() -> str:
    """Live portfolio via the aggregator, falling back to the paper book."""
    try:
        from lib.portfolio.aggregate import PortfolioAggregator

        payload = PortfolioAggregator().snapshot()
    except Exception as exc:
        logger.info("live portfolio unavailable (%s); falling back to paper book", exc)
        payload = _read_json(DATA_DIR / "paper_portfolio.json")

    if not isinstance(payload, dict):
        return _unavailable("📊 Portfolio", "No venue credentials and no paper book on disk.")

    rows = _portfolio_rows_from_payload(payload)
    total = payload.get("total_value")
    if not isinstance(total, (int, float)):
        total = payload.get("equity") if isinstance(payload.get("equity"), (int, float)) else None

    day_change = payload.get("day_change_pct")
    return fmt.fmt_portfolio_table(
        rows,
        total_usd=float(total) if isinstance(total, (int, float)) else None,
        day_change_pct=float(day_change) if isinstance(day_change, (int, float)) else None,
        updated_at=datetime.now(UTC).strftime("%H:%M UTC"),
    )


def portfolio_by_venue() -> str:
    try:
        from lib.portfolio.aggregate import PortfolioAggregator

        payload = PortfolioAggregator().snapshot()
    except Exception:
        return _unavailable("💰 By Venue", "Venue credentials are not configured.")

    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list) or not sources:
        return _unavailable("💰 By Venue")

    rows: list[tuple[str, str]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        name = str(source.get("venue") or source.get("name") or "?")
        status = str(source.get("status") or "unknown")
        emoji = "✅" if status.lower() in {"ok", "live", "connected"} else "⚠️"
        value = source.get("total_value")
        value_text = (
            fmt.fmt_usd(float(value)) if isinstance(value, (int, float)) else fmt.code("—")
        )
        rows.append((f"{emoji} {name}", value_text))
    return f"{fmt.bold('💰 By Venue')}\n\n" + fmt.kv_table(rows)


def portfolio_movers() -> str:
    try:
        from lib.portfolio.aggregate import PortfolioAggregator

        payload = PortfolioAggregator().snapshot()
    except Exception:
        payload = _read_json(DATA_DIR / "paper_portfolio.json")
    if not isinstance(payload, dict):
        return _unavailable("📈 Movers")

    rows = [r for r in _portfolio_rows_from_payload(payload) if r.delta_pct is not None]
    if not rows:
        return _unavailable("📈 Movers", "No 24h change data on any holding.")
    rows.sort(key=lambda r: abs(r.delta_pct or 0.0), reverse=True)
    return fmt.fmt_portfolio_table(rows[:8], updated_at=datetime.now(UTC).strftime("%H:%M UTC"))


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def signals_summary() -> str:
    try:
        from lib.analytics import strategy_performance

        report = strategy_performance.report()
    except Exception:
        report = None

    if not isinstance(report, dict):
        return _unavailable("📈 Signals", "No scored trade history yet.")

    overall = report.get("overall")
    if not isinstance(overall, dict):
        return _unavailable("📈 Signals")

    win_rate = overall.get("win_rate")
    trades = overall.get("trades")
    return fmt.fmt_signals_summary(
        active=int(trades) if isinstance(trades, (int, float)) else 0,
        win_rate_pct=(
            float(win_rate) * 100 if isinstance(win_rate, float) and win_rate <= 1 else win_rate
        ),
        last_scored=int(trades) if isinstance(trades, (int, float)) else None,
    )


def _recent_signal_files(limit: int = 5) -> list[dict]:
    signals_dir = DATA_DIR / "signals"
    if not signals_dir.exists():
        return []
    records: list[dict] = []
    try:
        files = sorted(
            signals_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []
    for path in files[:3]:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
            if len(records) >= limit:
                return records
    return records


def signals_active() -> str:
    records = _recent_signal_files(limit=5)
    if not records:
        return _unavailable("🟢 Active Signals", "No signal files under data/signals/.")

    cards: list[str] = []
    for record in records:
        symbol = str(record.get("symbol") or record.get("ticker") or "?")
        side = str(record.get("side") or record.get("direction") or "flat")
        confidence = record.get("confidence") or record.get("score") or 0
        try:
            conf_pct = float(confidence)
            if conf_pct <= 1:
                conf_pct *= 100
        except (TypeError, ValueError):
            conf_pct = 0.0
        cards.append(
            fmt.fmt_signal_alert(
                fmt.SignalCard(
                    symbol=symbol,
                    side=side,
                    confidence_pct=conf_pct,
                    entry=(
                        float(record["entry"])
                        if isinstance(record.get("entry"), (int, float))
                        else None
                    ),
                    strategy=str(record.get("strategy") or ""),
                )
            )
        )
    return "\n\n".join(cards[:3])


def signals_accuracy() -> str:
    try:
        from lib.analytics import prediction_accuracy

        report = prediction_accuracy.summary()
    except Exception:
        report = None
    if not isinstance(report, dict):
        return _unavailable("🎯 Accuracy", "Prediction scoring has not run yet.")

    rows: list[tuple[str, str]] = []
    for key, value in list(report.items())[:8]:
        if isinstance(value, (int, float)):
            rows.append((str(key), fmt.code(f"{value:.1f}")))
        else:
            rows.append((str(key), fmt.code(str(value)[:24])))
    return f"{fmt.bold('🎯 Prediction Accuracy')}\n\n" + fmt.kv_table(rows)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


def security_overview() -> str:
    snap = system_snapshot.build_snapshot()
    rows = [
        ("Kill switch", fmt.code("ARMED 🛑" if snap.kill_switch_armed else "OFF")),
    ]
    soc = _read_json(DATA_DIR / "security" / "latest_scan.json")
    if isinstance(soc, dict):
        for key in ("critical", "high", "medium", "low"):
            value = soc.get(key)
            if isinstance(value, int):
                rows.append((key.title(), fmt.fmt_int(value)))
    else:
        rows.append(("Last scan", fmt.code("not found")))
    return f"{fmt.bold('🔒 Security')}\n\n" + fmt.kv_table(rows)


def security_cves() -> str:
    payload = _read_json(DATA_DIR / "security" / "cves.json")
    entries = payload if isinstance(payload, list) else None
    if not entries:
        return _unavailable("🐛 Recent CVEs", "No CVE artifacts under data/security/.")
    cards = []
    for entry in entries[:5]:
        if not isinstance(entry, dict):
            continue
        cards.append(
            fmt.fmt_security_card(
                fmt.ThreatCard(
                    identifier=str(entry.get("id") or entry.get("cve") or "?"),
                    severity=str(entry.get("severity") or "low"),
                    package=str(entry.get("package") or ""),
                    summary=str(entry.get("summary") or "")[:200],
                )
            )
        )
    return "\n\n".join(cards) if cards else _unavailable("🐛 Recent CVEs")


def security_kill_switch() -> str:
    snap = system_snapshot.build_snapshot()
    if snap.kill_switch_armed:
        return (
            f"🛑 {fmt.bold('KILL SWITCH ARMED')}\n\n"
            + fmt.esc(
                "All order placement is blocked. Remove "
                "~/.sapphire/hyperliquid_trading_pause to resume."
            )
        )
    return (
        f"✅ {fmt.bold('Kill switch OFF')}\n\n"
        + fmt.esc("Trading executors are permitted to place orders under their caps.")
    )


# ---------------------------------------------------------------------------
# Brief + reports
# ---------------------------------------------------------------------------


def _latest_intelligence_dir() -> Path | None:
    intel = DATA_DIR / "intelligence"
    if not intel.exists():
        return None
    try:
        dirs = sorted([p for p in intel.iterdir() if p.is_dir()], reverse=True)
    except OSError:
        return None
    return dirs[0] if dirs else None


def brief_today() -> str:
    latest = _latest_intelligence_dir()
    if latest is None:
        return _unavailable("☀️ Today's Brief", "No data/intelligence/<date>/ directory.")
    payload = _read_json(latest / "brief.json")
    if not isinstance(payload, dict):
        return _unavailable("☀️ Today's Brief", f"No brief.json in {latest.name}.")

    sections: list[tuple[str, str]] = []
    for key in ("market", "chain", "signals", "security", "summary"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            sections.append((key.title(), fmt.esc(value.strip()[:600])))
        elif isinstance(value, dict):
            rows = [
                (str(k), fmt.code(str(v)[:32]))
                for k, v in list(value.items())[:6]
            ]
            sections.append((key.title(), fmt.kv_table(rows)))
    if not sections:
        return _unavailable("☀️ Today's Brief", "brief.json had no readable sections.")
    return fmt.fmt_brief(sections, banner=f"📰 Brief · {latest.name}")


def brief_weekly() -> str:
    ready = DATA_DIR / "content" / "ready"
    if not ready.exists():
        return _unavailable("📅 Weekly Brief", "No data/content/ready/ queue.")
    try:
        files = sorted(ready.glob("*weekly*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        files = []
    if not files:
        return _unavailable("📅 Weekly Brief", "No weekly report in the ready queue.")
    payload = _read_json(files[0])
    body = ""
    if isinstance(payload, dict):
        body = str(payload.get("body") or payload.get("summary") or "")
    if not body:
        return _unavailable("📅 Weekly Brief", "Report file had no body.")
    return f"{fmt.bold('📅 Weekly Brief')}\n\n" + fmt.esc(body[:2500])


def brief_ai_intel() -> str:
    ready = DATA_DIR / "content" / "ready"
    if not ready.exists():
        return _unavailable("🤖 AI Intel")
    try:
        files = sorted(
            list(ready.glob("*ai_intel*.json")) + list(ready.glob("*ai-intel*.json")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        files = []
    if not files:
        return _unavailable("🤖 AI Intel", "No AI-intel report in the ready queue.")
    payload = _read_json(files[0])
    body = str(payload.get("body") or "") if isinstance(payload, dict) else ""
    if not body:
        return _unavailable("🤖 AI Intel")
    return f"{fmt.bold('🤖 AI Intel')}\n\n" + fmt.esc(body[:2500])


def reports_list() -> str:
    entries: list[tuple[str, str, str]] = []
    for directory, label in (
        (DATA_DIR / "content" / "ready", "ready"),
        (DATA_DIR / "content" / "drafts", "draft"),
    ):
        if not directory.exists():
            continue
        try:
            files = sorted(
                directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            )
        except OSError:
            continue
        for path in files[:5]:
            payload = _read_json(path)
            title = ""
            if isinstance(payload, dict):
                title = str(payload.get("title") or "")
            if not title:
                title = path.stem
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
            entries.append((label, title, mtime))
    entries.sort(key=lambda row: row[2], reverse=True)
    return fmt.fmt_reports_list(entries[:10])


def reports_queue() -> str:
    pending = DATA_DIR / "content" / "pending"
    if not pending.exists():
        return _unavailable("📁 Ready Queue", "No pending approvals.")
    try:
        files = sorted(pending.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        files = []
    if not files:
        return f"{fmt.bold('📁 Approval Queue')}\n\n{fmt.esc('Nothing awaiting approval.')}"
    rows = [(fmt.esc(p.stem[:40]), fmt.code("pending")) for p in files[:10]]
    return f"{fmt.bold('📁 Approval Queue')}\n\n" + fmt.kv_table(rows)


# ---------------------------------------------------------------------------
# Status + settings
# ---------------------------------------------------------------------------


def status_snapshot() -> str:
    snap = system_snapshot.build_snapshot()
    services = [system_snapshot.format_service_state(s) for s in snap.services[:12]]
    if not services:
        services = [("launchctl", "unavailable")]
    return fmt.fmt_status_snapshot(
        services=services,
        freshness=snap.freshness,
        regime=snap.regime,
        fear_greed=snap.fear_greed,
        kill_switch_armed=snap.kill_switch_armed,
    )


def status_deep() -> str:
    snap = system_snapshot.build_snapshot()
    services = [system_snapshot.format_service_state(s) for s in snap.services]
    if not services:
        return _unavailable("🩺 Deep Health", "launchctl returned no com.sapphire.* agents.")
    header = fmt.bold(f"🩺 Deep Health · {snap.agents_ok}/{snap.agents_total} up")
    return header + "\n\n" + fmt.kv_table(services)


def settings_view() -> str:
    import os

    current = settings_store.load()
    snap = system_snapshot.build_snapshot()
    live = os.getenv("SAPPHIRE_NOTIFY_TELEGRAM_LIVE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return fmt.fmt_settings(
        heartbeat_enabled=current.heartbeat_enabled,
        heartbeat_hours=current.heartbeat_hours,
        live_notifications=live,
        kill_switch_armed=snap.kill_switch_armed,
    )


def home_screen() -> str:
    """The root menu body — a compact at-a-glance line plus a prompt."""
    snap = system_snapshot.build_snapshot()
    line = fmt.fmt_heartbeat_line(
        agents_ok=snap.agents_ok,
        agents_total=snap.agents_total,
        regime=snap.regime,
        fear_greed=snap.fear_greed,
        portfolio_usd=snap.portfolio_usd,
        kill_switch_armed=snap.kill_switch_armed,
    )
    return line + "\n\n" + fmt.esc("Choose a section below.")


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_providers() -> dict[str, object]:
    """Map menu leaf tokens → provider callables."""
    return {
        "h": home_screen,
        "pf": portfolio_overview,
        "pf:r": portfolio_overview,
        "pf:v": portfolio_by_venue,
        "pf:m": portfolio_movers,
        "sg": signals_summary,
        "sg:a": signals_active,
        "sg:r": signals_active,
        "sg:acc": signals_accuracy,
        "sec": security_overview,
        "sec:cve": security_cves,
        "sec:ks": security_kill_switch,
        "br": brief_today,
        "br:t": brief_today,
        "br:w": brief_weekly,
        "br:ai": brief_ai_intel,
        "st": status_snapshot,
        "st:d": status_deep,
        "rp": reports_list,
        "rp:l": reports_list,
        "rp:q": reports_queue,
        "cfg": settings_view,
    }


__all__ = ["build_providers"]
