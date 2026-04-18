"""Morning Telegram brief — 7 AM CT via LaunchAgent.

Synthesizes seven intelligence streams into one Markdown-formatted
Telegram message:

  1. Market regime (from lib.chain.ChainIntelligence)
  2. Correlations & decorrelation events (from lib.analytics.CorrelationEngine)
  3. Fear & Greed composite (from lib.analytics.sentiment)
  4. Portfolio risk metrics (from lib.analytics.RiskEngine)
  5. Kronos predictions (from data/intelligence/YYYY-MM-DD/predictions.json)
  6. Threat intel count (from data/intelligence/YYYY-MM-DD/threats.json)
  7. System health (services up/down)

Also persists a markdown copy to data/intelligence/YYYY-MM-DD/daily_brief.md
so the morning brief is always accessible in the ops log, and publishes a
`sentiment.update` event to the bus so other modules can react.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Notify tool lives under plugin dir — add to path
NOTIFY_DIR = ROOT / "plugins" / "claw-sapphire" / "tools"
if str(NOTIFY_DIR) not in sys.path:
    sys.path.insert(0, str(NOTIFY_DIR))

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _fmt_usd(n: float | None, digits: int = 2) -> str:
    if n is None:
        return "—"
    abs_n = abs(n)
    sign = "-" if n < 0 else ""
    if abs_n >= 1e9:
        return f"{sign}${abs_n/1e9:.{digits}f}B"
    if abs_n >= 1e6:
        return f"{sign}${abs_n/1e6:.{digits}f}M"
    if abs_n >= 1e3:
        return f"{sign}${abs_n/1e3:.{digits}f}k"
    return f"{sign}${abs_n:.{digits}f}"


def _fmt_pct(n: float | None, digits: int = 1) -> str:
    if n is None:
        return "—"
    return f"{n*100:+.{digits}f}%"


def _section_regime() -> dict:
    """Market regime section from on-chain intelligence."""
    try:
        from lib.chain import ChainIntelligence
        ci = ChainIntelligence()
        snap = ci.snapshot()
    except Exception as e:
        log.warning("chain intelligence unavailable: %s", e)
        return {"status": "unavailable", "error": str(e)}

    regime = snap.get("regime") or {}
    overview = snap.get("overview") or {}
    stable = snap.get("stablecoins") or {}
    funding_snap = snap.get("funding") or {}

    # Top extreme funding perps
    perps = funding_snap.get("perps") or []
    extremes = [p for p in perps if p.get("extreme_flag") in
                {"crowded_long", "crowded_short", "elevated_long", "elevated_short"}]
    extremes.sort(key=lambda p: abs(p.get("funding_rate_8h", 0.0)), reverse=True)

    lines = []
    state = regime.get("state", "UNKNOWN")
    emoji = {"RISK_ON": "🟢", "RISK_OFF": "🔴", "TRANSITION": "🟡"}.get(state, "⚪")
    lines.append(f"{emoji} *Regime:* `{state}`  "
                 f"score {regime.get('score', 0):+.2f} · "
                 f"conf {regime.get('confidence', 0):.0%}")

    for r in regime.get("reasoning", [])[:3]:
        lines.append(f"  • {r}")

    # Headline numbers
    btc_price = overview.get("btc_price_usd")
    btc_d = overview.get("btc_dominance")
    m24 = overview.get("market_cap_change_24h_pct")
    if btc_price:
        lines.append(f"  BTC ${btc_price:,.0f}  (dom {btc_d:.1f}%)" if btc_d
                     else f"  BTC ${btc_price:,.0f}")
    if m24 is not None:
        lines.append(f"  Total mcap 24h: {m24:+.2f}%")

    # Funding extremes (max 2)
    for p in extremes[:2]:
        coin = p.get("coin", "?")
        rate = p.get("funding_rate_8h", 0.0) * 100
        flag = p.get("extreme_flag", "")
        lines.append(f"  ⚠️ {coin} funding {rate:+.3f}%  ({flag})")

    # Stablecoin flow
    flow = stable.get("flow_direction")
    d24 = stable.get("delta_24h_usd")
    if flow in {"inflow", "outflow"} and d24 is not None:
        arrow = "↑" if flow == "inflow" else "↓"
        lines.append(f"  Stablecoins 24h: {arrow} {_fmt_usd(abs(d24))} ({flow})")

    return {
        "status": "ok",
        "state": state,
        "score": regime.get("score", 0.0),
        "text": "\n".join(lines),
    }


def _section_correlation() -> dict:
    """Correlation snapshot + decorrelation events."""
    try:
        from lib.analytics.correlation import CorrelationEngine
        eng = CorrelationEngine()
        matrix = eng.build_matrix(window_days=30)
        events = eng.detect_decorrelations(matrix)
    except Exception as e:
        log.warning("correlation unavailable: %s", e)
        return {"status": "unavailable", "error": str(e)}

    lines = []
    # Pull out the most relevant pairs: BTC↔SPY, BTC↔ETH, SPY↔VIX, BTC↔DXY
    syms = matrix.symbols
    idx = {s: i for i, s in enumerate(syms)}
    highlight = [
        ("BTC", "ETH"),
        ("BTC", "SPY"),
        ("BTC", "DXY"),
        ("SPY", "VIX"),
    ]
    pair_strs = []
    for a, b in highlight:
        if a in idx and b in idx:
            v = matrix.matrix[idx[a]][idx[b]]
            pair_strs.append(f"{a}↔{b} `{v:+.2f}`")
    if pair_strs:
        lines.append("  " + " · ".join(pair_strs))

    if events:
        sev_emoji = {"severe": "🚨", "moderate": "⚠️", "mild": "📎"}
        for e in events[:3]:
            em = sev_emoji.get(e.severity, "•")
            lines.append(f"  {em} {e.note}")
    else:
        lines.append("  No decorrelation events.")

    return {
        "status": "ok",
        "events": len(events),
        "text": "\n".join(lines),
    }


def _section_portfolio() -> dict:
    """Portfolio risk metrics."""
    try:
        from lib.analytics.risk_engine import RiskEngine
        m = RiskEngine(bankroll=10000.0).compute()
    except Exception as e:
        log.warning("risk engine unavailable: %s", e)
        return {"status": "unavailable", "error": str(e)}

    lines = []
    pnl_emoji = "🟢" if m.total_pnl_usd >= 0 else "🔴"
    lines.append(f"{pnl_emoji} *Portfolio:* {_fmt_usd(m.total_pnl_usd)}  "
                 f"({m.total_trades} trades · {m.wins}W/{m.losses}L)")
    if m.win_rate is not None:
        lines.append(f"  Win rate `{m.win_rate:.0%}` · "
                     f"PF `{m.profit_factor if m.profit_factor and m.profit_factor != float('inf') else '∞'}`")
    if m.sharpe is not None:
        lines.append(f"  Sharpe `{m.sharpe}` · Sortino `{m.sortino}` · Calmar `{m.calmar}`")
    if m.max_drawdown_pct > 0:
        lines.append(f"  Max DD `{m.max_drawdown_pct:.1%}` "
                     f"({_fmt_usd(m.max_drawdown_usd)}, {m.max_drawdown_duration_days}d)")
    lines.append(f"  Recommended size: {_fmt_usd(m.recommended_size_usd)}  "
                 f"(¼-Kelly · bankroll ${m.bankroll:,.0f})")

    return {
        "status": "ok",
        "pnl": m.total_pnl_usd,
        "trades": m.total_trades,
        "text": "\n".join(lines),
    }


def _section_sentiment(chain_snapshot: dict | None = None) -> dict:
    """Fear & Greed composite — publishes sentiment.update to the event bus."""
    try:
        from lib.analytics.sentiment import compute_sentiment
        s = compute_sentiment(chain_snapshot=chain_snapshot)
    except Exception as e:
        log.warning("sentiment unavailable: %s", e)
        return {"status": "unavailable", "text": f"  (sentiment unavailable: {e})"}

    # Publish to event bus so dashboard world-state / other modules can react.
    try:
        from lib.core.event_bus import get_bus
        get_bus().publish(
            "sentiment.update",
            {
                "fear_greed": s.score,
                "label": s.label,
                "components": s.components,
            },
            source="daily_brief",
        )
    except Exception as e:
        log.debug("sentiment event publish failed: %s", e)

    emoji = {
        "extreme_fear": "🥶",
        "fear": "😟",
        "neutral": "😐",
        "greed": "😊",
        "extreme_greed": "🤑",
    }.get(s.label, "•")
    label = s.label.replace("_", " ").title()
    lines = [f"{emoji} *F&G:* `{s.score}/100` ({label})"]
    # Show the two largest-magnitude sub-score deviations from 50 (neutral).
    deviations = sorted(
        s.components.items(),
        key=lambda kv: abs(kv[1] - 50.0),
        reverse=True,
    )
    for name, val in deviations[:2]:
        arrow = "↑" if val > 50 else "↓" if val < 50 else "·"
        lines.append(f"  {arrow} {name}: {val:.0f}  — {s.explanations.get(name, '')}")
    return {"status": "ok", "score": s.score, "label": s.label, "text": "\n".join(lines)}


def _section_threats() -> dict:
    """24h threat intel summary from cyber-threat-bot snapshot."""
    today = datetime.now().strftime("%Y-%m-%d")
    path = ROOT / "data" / "intelligence" / today / "threats.json"
    if not path.exists():
        # Fall back to the newest day we have.
        intel = ROOT / "data" / "intelligence"
        if intel.exists():
            candidates = sorted(
                [p for p in intel.glob("*/threats.json") if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                path = candidates[0]
        if not path.exists():
            return {"status": "missing", "text": "  No threat snapshot."}

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"status": "error", "text": f"  Threat parse error: {e}"}

    threats = data.get("threats") or []
    kev = [t for t in threats if t.get("exploited") or "kev" in (t.get("tags") or [])]
    high = [t for t in threats if isinstance(t.get("score"), (int, float)) and t["score"] >= 8.0]

    emoji = "🚨" if kev else "🟡" if high else "🟢"
    lines = [
        f"{emoji} *Threats (24h):* `{len(threats)}` total · "
        f"`{len(kev)}` KEV-exploited · `{len(high)}` CVSS≥8"
    ]
    for t in sorted(threats, key=lambda x: x.get("score") or 0, reverse=True)[:2]:
        cid = t.get("canonical_id") or t.get("title", "")[:40]
        score = t.get("score")
        score_str = f" (CVSS {score:.1f})" if isinstance(score, (int, float)) else ""
        flag = "💣" if t.get("exploited") else "•"
        lines.append(f"  {flag} `{cid}`{score_str}")
    return {
        "status": "ok",
        "total": len(threats),
        "kev": len(kev),
        "high": len(high),
        "text": "\n".join(lines),
    }


def _section_health() -> dict:
    """System health summary via health_check tool."""
    # health_check is CLI-only (stdin JSON → stdout JSON). Shell out rather than
    # import so we isolate any module-level side effects it might have.
    health_tool = NOTIFY_DIR / "health_check.py"
    if not health_tool.exists():
        return {"status": "unavailable", "text": f"  (health tool not found: {health_tool})"}
    try:
        import subprocess
        r = subprocess.run(
            ["/usr/local/bin/python3", str(health_tool)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=20,
        )
        if r.returncode != 0:
            return {"status": "error", "text": f"  Health check exit {r.returncode}: {r.stderr[:80]}"}
        report = json.loads(r.stdout)
    except Exception as e:
        return {"status": "error", "text": f"  Health check failed: {e}"}

    # Count statuses across every grouping in the report. health_check groups
    # results under keys like "services" / "repos" / "tasks", each mapping
    # name → {"status": "green|yellow|red", "detail": "..."}.
    pass_n = warn_n = fail_n = 0
    failing: list[tuple[str, dict]] = []
    for group_name, group in report.items():
        if not isinstance(group, dict):
            continue
        for name, check in group.items():
            if not isinstance(check, dict):
                continue
            st = (check.get("status") or "").lower()
            if st in {"green", "pass", "ok", "nominal"}:
                pass_n += 1
            elif st in {"yellow", "warn", "degraded"}:
                warn_n += 1
            elif st in {"red", "fail", "critical"}:
                fail_n += 1
                failing.append((f"{group_name}/{name}", check))

    # Publish service.health so the event bus reflects reality.
    try:
        from lib.core.event_bus import get_bus
        status = "critical" if fail_n else "degraded" if warn_n else "nominal"
        get_bus().publish(
            "service.health",
            {"status": status, "pass": pass_n, "warn": warn_n, "fail": fail_n},
            source="daily_brief",
        )
    except Exception as e:
        log.debug("service.health publish failed: %s", e)

    emoji = "🟢" if not fail_n and not warn_n else "🟡" if not fail_n else "🔴"
    lines = [f"{emoji} *Health:* `{pass_n}` ok · `{warn_n}` warn · `{fail_n}` fail"]

    for name, c in failing[:2]:
        detail = c.get("detail") or c.get("error") or ""
        # Escape underscores so Telegram Markdown doesn't eat them as italic.
        safe_name = name.replace("_", r"\_")
        safe_detail = detail[:60].replace("_", r"\_")
        lines.append(f"  🔴 {safe_name}: {safe_detail}")
    return {"status": "ok", "pass": pass_n, "warn": warn_n, "fail": fail_n, "text": "\n".join(lines)}


def _section_kronos() -> dict:
    """Kronos daily predictions (if available)."""
    today = datetime.now().strftime("%Y-%m-%d")
    pred_path = ROOT / "data" / "intelligence" / today / "predictions.json"
    if not pred_path.exists():
        return {"status": "missing", "text": "  Kronos predictions not yet generated."}
    try:
        data = json.loads(pred_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"status": "error", "text": f"  Kronos parse error: {e}"}

    lines = []
    predictions = data.get("predictions") or data

    def _summarize(entry: dict, fallback_sym: str = "?") -> str:
        sym = entry.get("symbol", fallback_sym)
        direction = entry.get("direction", entry.get("prediction", "?"))
        conf = entry.get("confidence", 0.0)
        price = entry.get("current_price")
        price_str = f"  ${price:,.0f}" if isinstance(price, (int, float)) else ""
        return f"  {sym}: *{direction}*  (conf {conf:.0%}){price_str}"

    if isinstance(predictions, list):
        for p in predictions[:4]:
            if isinstance(p, dict):
                lines.append(_summarize(p))
    elif isinstance(predictions, dict):
        for sym, val in list(predictions.items())[:4]:
            if isinstance(val, dict):
                lines.append(_summarize(val, fallback_sym=sym))
            else:
                lines.append(f"  {sym}: {str(val)[:80]}")

    if not lines:
        lines.append("  (empty predictions)")
    return {"status": "ok", "text": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Compose + send
# ---------------------------------------------------------------------------


def build_brief() -> str:
    """Build the Markdown-formatted brief text."""
    now = datetime.now()
    header = f"🌅 *Sapphire Morning Brief* — {now:%a, %b %d · %H:%M}"

    # Fetch chain snapshot once and pass into downstream sections to avoid
    # duplicate API calls.
    chain_snap: dict | None = None
    try:
        from lib.chain import ChainIntelligence
        chain_snap = ChainIntelligence().snapshot()
    except Exception:
        chain_snap = None

    regime = _section_regime()
    corr = _section_correlation()
    sent = _section_sentiment(chain_snapshot=chain_snap)
    port = _section_portfolio()
    kron = _section_kronos()
    threats = _section_threats()
    health = _section_health()

    parts = [
        header,
        "",
        "*Market Regime*",
        regime.get("text") or f"  ({regime.get('status', 'unknown')})",
        "",
        "*Correlations*",
        corr.get("text") or f"  ({corr.get('status', 'unknown')})",
        "",
        "*Sentiment*",
        sent.get("text") or f"  ({sent.get('status', 'unknown')})",
        "",
        "*Portfolio*",
        port.get("text") or f"  ({port.get('status', 'unknown')})",
        "",
        "*Kronos predictions*",
        kron.get("text"),
        "",
        "*Threat intel*",
        threats.get("text") or f"  ({threats.get('status', 'unknown')})",
        "",
        "*System health*",
        health.get("text") or f"  ({health.get('status', 'unknown')})",
    ]
    return "\n".join(parts)


def persist_brief(text: str) -> Path:
    """Write brief to data/intelligence/YYYY-MM-DD/daily_brief.md."""
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = ROOT / "data" / "intelligence" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "daily_brief.md"
    path.write_text(text + "\n")
    return path


def send_brief(text: str) -> dict:
    """Send via notify.send_telegram_message. Returns API response."""
    try:
        from notify import send_telegram_message
    except ImportError as e:
        log.error("notify unavailable: %s", e)
        return {"ok": False, "error": f"notify import: {e}"}
    try:
        return send_telegram_message(text, priority="p1")
    except Exception as e:
        log.error("telegram send failed: %s", e)
        return {"ok": False, "error": str(e)}


def main() -> int:
    text = build_brief()
    out = persist_brief(text)
    log.info("daily brief persisted → %s (%d chars)", out, len(text))
    result = send_brief(text)
    if result.get("ok"):
        log.info("telegram send succeeded")
        return 0
    log.warning("telegram send failed: %s", result)
    return 1


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                   help="Print the brief to stdout without sending to Telegram")
    args = p.parse_args()

    if args.dry_run:
        text = build_brief()
        print(text)
        out = persist_brief(text)
        print(f"\n(persisted to {out})")
        sys.exit(0)

    sys.exit(main())
