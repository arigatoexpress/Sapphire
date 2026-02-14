"""
API Route Handlers for Sapphire Alpha Engine.

These are standalone handler functions that accept the engine as a parameter.
Called from AlphaEngine via thin wrapper methods and passed to start_health_server.

This module was extracted from main.py to improve maintainability.
All handlers are pure request-in/response-out with read access to engine state.
"""

import time
from typing import Any, Dict, List

from loguru import logger
from src.execution.dispatcher import dispatcher
from src.security.agent_permissions import gate, Capability


# ---------------------------------------------------------------------------
# Market Data Endpoints
# ---------------------------------------------------------------------------


async def handle_market_ohlc(engine: Any, query: Dict[str, Any]) -> Dict[str, Any]:
    """Return OHLC candle data for a venue/symbol pair."""
    venue = engine._normalize_platform(str(query.get("venue", "ASTER")))
    if venue not in {"ASTER", "LIGHTER"}:
        return {
            "error": "unsupported_venue",
            "message": "venue must be ASTER or LIGHTER",
            "venue": venue,
            "candles": [],
        }

    symbol = str(query.get("symbol", "SOL")).strip().upper() or "SOL"
    interval = str(query.get("interval", "1m")).strip().lower() or "1m"
    limit_raw = query.get("limit", "120")
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = 120
    limit = max(10, min(limit, 500))

    ohlc = await engine.market_data.fetch_ohlc(
        venue=venue,
        symbol=symbol,
        interval=interval,
        limit=limit,
    )
    ohlc["generated_at"] = int(time.time())
    return ohlc


# ---------------------------------------------------------------------------
# Platform & Routing Endpoints
# ---------------------------------------------------------------------------


async def handle_platform_status(engine: Any, _: Dict[str, Any]) -> Dict[str, Any]:
    """Return per-venue health status."""
    snapshot = engine.market_data.get_market_snapshot(symbol="SOL")
    control_state = dispatcher.get_control_state()
    strategy_state = engine.strategy.execution_state()
    platforms: Dict[str, Dict[str, Any]] = {}

    for venue in ("ASTER", "LIGHTER"):
        venue_state = control_state.get(
            venue, {"paused": True, "allocation": 0.0, "cooldown_until": 0.0}
        )
        market = snapshot.get(
            venue,
            {"price": 0.0, "status": "offline", "age_seconds": None, "last_tick_ts": None},
        )
        paused = bool(
            venue_state.get("paused", False) or venue_state.get("allocation", 0.0) <= 0
        )
        feed_status = str(market.get("status", "offline")).lower()

        if engine._kill_switch_active:
            status = "degraded"
            mode = "Kill-switch halted"
        elif paused:
            status = "degraded" if feed_status in {"healthy", "degraded"} else "offline"
            mode = "Paused allocation"
        else:
            status = "healthy" if feed_status == "healthy" else "degraded"
            mode = "Autonomous ready" if status == "healthy" else "Awaiting fresh market ticks"

        note = (
            f"Allocation {float(venue_state.get('allocation', 0.0)) * 100:.0f}% | "
            f"Tick age {market.get('age_seconds', 'n/a')}s"
        )
        platforms[venue.lower()] = {
            "status": status,
            "health": status,
            "mode": mode,
            "routing": "autonomous",
            "note": note,
            "price": market.get("price", 0.0),
            "last_tick_ts": market.get("last_tick_ts"),
            "age_seconds": market.get("age_seconds"),
            "allocation": float(venue_state.get("allocation", 0.0)),
            "paused": paused,
        }

    return {
        "platforms": platforms,
        "kill_switch_active": engine._kill_switch_active,
        "dex_execution_stage": strategy_state.get("dex_execution_stage", "paper"),
        "dex_live_dispatch": bool(strategy_state.get("stage_multiplier", 0) > 0),
        "dex_effective_quantity": float(strategy_state.get("effective_quantity", 0.0)),
        "timestamp": int(time.time()),
    }


async def handle_routing_info(engine: Any, _: Dict[str, Any]) -> Dict[str, Any]:
    """Return routing confidence and venue allocation data."""
    state = dispatcher.get_control_state()
    strategy_state = engine.strategy.execution_state()
    active = [
        venue
        for venue, item in state.items()
        if not item.get("paused") and item.get("allocation", 0) > 0
    ]
    paused = [
        venue
        for venue, item in state.items()
        if item.get("paused") or item.get("allocation", 0) <= 0
    ]
    failure_pressure = int(sum(engine._failure_counts.values()))
    snapshot = engine.market_data.get_market_snapshot(symbol="SOL")

    if engine._kill_switch_active:
        confidence = 0.0
        mode = "halted"
    else:
        healthy_active = sum(
            1 for venue in active if snapshot.get(venue, {}).get("status") == "healthy"
        )
        confidence = 0.92
        confidence -= min(0.45, failure_pressure * 0.08)
        if len(active) < max(1, engine._trading_gate_min_active_venues):
            confidence -= 0.25
        elif len(active) < 2:
            confidence -= 0.08
        if active and healthy_active < len(active):
            confidence -= 0.15
        confidence = max(0.05, min(0.99, confidence))
        mode = "autonomous" if confidence >= 0.7 else "guarded"

    return {
        "mode": mode,
        "strategy": "policy-gated",
        "confidence": float(round(confidence, 4)),
        "data": {
            "confidence": float(round(confidence, 4)),
        },
        "routing": {
            "confidence": float(round(confidence, 4)),
            "active_venues": active,
            "paused_venues": paused,
            "failure_pressure": failure_pressure,
            "kill_switch_active": engine._kill_switch_active,
            "dex_execution_stage": strategy_state.get("dex_execution_stage", "paper"),
            "dex_live_dispatch": bool(strategy_state.get("stage_multiplier", 0) > 0),
        },
        "timestamp": int(time.time()),
    }


# ---------------------------------------------------------------------------
# Performance & Logs Endpoints
# ---------------------------------------------------------------------------


async def handle_performance_stats(engine: Any, _: Dict[str, Any]) -> Dict[str, Any]:
    """Return system performance metrics."""
    total_trades = int(engine._trade_metrics["total_trades"])
    wins = int(engine._trade_metrics["wins"])
    losses = int(engine._trade_metrics["losses"])
    win_rate = float((wins / total_trades) * 100.0) if total_trades > 0 else 0.0
    uptime_seconds = int(max(0, time.time() - engine._started_at))
    failure_pressure = int(sum(engine._failure_counts.values()))

    return {
        "metrics": {
            "system": {
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 2),
                "realized_pnl": float(round(engine._trade_metrics["realized_pnl"], 6)),
                "uptime_seconds": uptime_seconds,
                "failure_pressure": failure_pressure,
                "autonomy_dispatch_count": int(engine._autonomy_dispatch_count),
            }
        },
        "timestamp": int(time.time()),
    }


async def handle_system_logs(engine: Any, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return recent system log entries."""
    limit_raw = payload.get("limit", 80)
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = 80
    limit = max(1, min(limit, engine._system_log_max_entries))
    return list(engine._system_logs)[-limit:]


async def handle_control_status(engine: Any, _: Dict[str, Any]) -> Dict[str, Any]:
    """Return control plane snapshot."""
    return engine._control_snapshot()





# ---------------------------------------------------------------------------
# Security Endpoints
# ---------------------------------------------------------------------------


async def handle_security_skills_status(engine: Any, _: Dict[str, Any]) -> Dict[str, Any]:
    """Return VirusTotal skill scanner status."""
    status = engine.vt_scanner.status()
    status["timestamp"] = int(time.time())
    return status


async def handle_security_skill_scan(engine: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Trigger a VirusTotal skill scan."""
    requested_skill = str(payload.get("skill", "")).strip()
    upload_if_missing_raw = payload.get(
        "upload_if_missing", engine.vt_scanner.upload_if_missing_default
    )
    upload_if_missing = str(upload_if_missing_raw).strip().lower() in {"1", "true", "yes", "on"}

    if requested_skill and requested_skill.lower() != "all":
        result = await engine.vt_scanner.scan_skill(
            requested_skill,
            upload_if_missing=upload_if_missing,
        )
        if result.get("ok"):
            security = result.get("security", {})
            engine._record_system_log(
                f"VirusTotal scan completed for {requested_skill}",
                level="info",
                tags=["security", "virustotal", "skills"],
                metadata={
                    "skill": requested_skill,
                    "verdict": security.get("verdict", "unknown"),
                    "policy_blocked": bool(
                        (security.get("policy", {}) or {}).get("blocked", False)
                    ),
                },
            )
        return result

    batch_result = await engine.vt_scanner.scan_all_skills(
        upload_if_missing=upload_if_missing
    )
    if batch_result.get("ok"):
        engine._record_system_log(
            "VirusTotal batch scan completed",
            level="info",
            tags=["security", "virustotal", "skills"],
            metadata={
                "skills_scanned": int(batch_result.get("skills_scanned", 0)),
                "counts": batch_result.get("counts", {}),
                "blocked_count": int(batch_result.get("blocked_count", 0)),
            },
        )
    return batch_result


# ---------------------------------------------------------------------------
# Forum Endpoints
# ---------------------------------------------------------------------------


async def handle_forum_topics(engine: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """List forum topics."""
    board = engine.forum.list_topics(payload)
    control = engine._control_snapshot()
    return {
        **board,
        "control": {
            "pending_autonomy_decisions": int(control.get("pending_autonomy_decisions", 0)),
            "owner_directive": str(control.get("owner_directive", "") or ""),
            "failure_pressure": int(control.get("failure_pressure", 0)),
        },
        "timestamp": int(time.time()),
    }


async def handle_forum_topic_detail(engine: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Get a single forum topic by ID."""
    topic_id = str(payload.get("topic_id", "")).strip()
    if not topic_id:
        return {"error": "topic_id_required"}
    topic = engine.forum.get_topic_detail(topic_id)
    if not topic:
        return {"error": "topic_not_found", "topic_id": topic_id}
    return {"topic": topic, "timestamp": int(time.time())}


async def handle_forum_create_topic(engine: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new forum topic."""
    author = str(payload.get("author", "SAPPHIRE")).strip().upper()
    gate.require(author, Capability.FORUM_WRITE, f"create_topic(author={author})")
    try:
        topic = engine.forum.create_topic(
            {
                "title": payload.get("title", ""),
                "body": payload.get("body", ""),
                "lane": payload.get("lane", "research"),
                "category": payload.get("category", "general"),
                "state": payload.get("state", "open"),
                "priority": payload.get("priority", "medium"),
                "author": payload.get("author", "SAPPHIRE"),
                "tags": payload.get("tags", []),
                "source": payload.get("source", "internal"),
            }
        )
    except ValueError as exc:
        return {"error": str(exc)}

    engine._record_system_log(
        f"Forum topic created: {topic.get('topic_id', 'unknown')}",
        level="info",
        tags=["forum", "topic"],
        metadata={
            "topic_id": topic.get("topic_id", ""),
            "lane": topic.get("lane", ""),
            "priority": topic.get("priority", ""),
        },
    )
    return {"topic": topic, "timestamp": int(time.time())}


async def handle_forum_replies(engine: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Add a reply to a forum topic."""
    topic_id = str(payload.get("topic_id", "")).strip()
    if not topic_id:
        return {"error": "topic_id_required"}

    body = str(payload.get("body", "")).strip()
    if not body:
        return {"error": "body_required"}

    try:
        reply = engine.forum.add_reply(
            topic_id,
            {
                "body": body,
                "author": payload.get("author", "SAPPHIRE"),
                "kind": payload.get("kind", "comment"),
                "state": payload.get("state", ""),
                "source": payload.get("source", "internal"),
                "parent_reply_id": payload.get("parent_reply_id", ""),
            },
        )
    except ValueError as exc:
        return {"error": str(exc)}

    engine._record_system_log(
        f"Forum reply added to {topic_id}",
        level="info",
        tags=["forum", "reply"],
        metadata={"topic_id": topic_id, "reply_id": reply.get("reply_id", "")},
    )
    return {"reply": reply, "timestamp": int(time.time())}


async def handle_forum_scout_status(engine: Any, _: Dict[str, Any]) -> Dict[str, Any]:
    """Return forum scout status."""
    return engine.forum.scout_status()


async def handle_forum_scout_register(engine: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Register a scout account and dispatch Telegram notification."""
    result = await engine.forum.register_scout_account(payload)
    if result.get("ok"):
        dispatch = result.get("dispatch", {}) or {}
        mode = str(dispatch.get("mode", "none")).strip() or "none"
        metadata = dispatch.get("metadata", {}) if isinstance(dispatch, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        username = result.get("registration", {}).get("username", "unknown")
        if dispatch.get("dispatched"):
            lines = [
                "🛰️ Scout registration processed.",
                f"Mode: `{mode}`",
                f"User: `@{username}`",
                "Outcome: least-privilege external collaboration scout is active.",
            ]
            if metadata.get("claim_url"):
                lines.append(
                    f"Action: complete claim in Moltbook once using `{metadata.get('claim_url')}`."
                )
            elif metadata.get("already_registered"):
                lines.append(
                    "Action: existing claimed scout account detected; no re-registration needed."
                )
            await engine.telegram.send_message(
                "\n".join(lines),
                priority="medium",
            )
        else:
            lines = [
                "🛰️ Scout registration prepared locally; external provider blocked dispatch.",
                f"Mode: `{mode}`",
                f"Reason: `{dispatch.get('reason', 'not_configured')}`",
                "Benefit preserved: local SapphireBook record exists for retry/audit "
                "without exposing sensitive data.",
            ]
            if metadata.get("hint"):
                lines.append(f"Hint: {metadata.get('hint')}")
            await engine.telegram.send_message(
                "\n".join(lines),
                priority="medium",
            )
    return result


async def handle_forum_scout_publish(engine: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Publish a scout note externally."""
    result = await engine.forum.publish_scout_note(payload)
    if result.get("ok"):
        dispatch = result.get("dispatch", {}) or {}
        if not dispatch.get("dispatched"):
            engine._record_system_log(
                "Scout outbound note stored locally; external publish pending",
                level="warning",
                tags=["forum", "scout"],
                metadata={"reason": dispatch.get("reason", "not_configured")},
            )
    return result
