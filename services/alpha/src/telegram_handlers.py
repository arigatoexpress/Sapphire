"""Telegram ``/command`` dispatchers for the Sapphire Alpha engine.

Handlers extracted from ``AlphaEngine._handle_control_command``. Each takes
the engine instance plus command parameters and returns ``True`` when the
action was handled, ``False`` to fall through to the next handler.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from src.execution.dispatcher import dispatcher
from src.security.agent_permissions import Capability, gate

if TYPE_CHECKING:
    from src.main import AlphaEngine

# Re-export agent identities for message routing.
# Fallback keeps the alpha service boot-safe if shared telegram module changes exports.
try:
    from telegram_bot import EMERALD, OBSIDIAN, SAPPHIRE
except Exception:
    SAPPHIRE = "SAPPHIRE"
    OBSIDIAN = "OBSIDIAN"
    EMERALD = "EMERALD"
    logger.warning(
        "telegram_bot identity constants unavailable; using built-in agent id fallbacks."
    )


# ── Media Management ──────────────────────────────────────────────────


async def handle_media_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle MEDIA_* control commands."""
    normalized = action.upper()

    if normalized in {"MEDIA_STATUS", "MEDIA_QUEUE_STATUS", "MEDIA_QUEUE", "COMMUNICATION_STATUS"}:
        report = engine.media_manager.get_status_report()
        await engine.telegram.send_message(report, priority="medium")
        return True

    if normalized in {"MEDIA_SET_MODE", "SET_MEDIA_MODE"}:
        gate.require("OBSIDIAN", Capability.SYSTEM_CONFIG, f"set_media_mode({target!r})")
        payload = engine._parse_json_payload(target)
        requested_mode = str(payload.get("mode", "")).strip() or str(target or "").strip()
        new_mode = engine.media_manager.set_mode(requested_mode)
        snapshot = engine.media_manager.get_status_snapshot()
        await engine.telegram.send_message(
            (
                f"✅ Media mode updated to `{new_mode}`.\n"
                f"X ready: `{'YES' if snapshot.get('twitter_ready') else 'NO'}` | "
                f"Substack ready: `{'YES' if snapshot.get('substack_ready') else 'NO'}`\n"
                "Expected outcome: publication workflow now follows the updated automation policy."
            ),
            priority="high",
        )
        return True

    if normalized in {"MEDIA_GENERATE", "MEDIA_AI_DRAFT"}:
        gate.require("EMERALD", Capability.AI_PROMPT, f"media_generate({target!r})")
        payload = engine._parse_json_payload(target)
        platform = str(payload.get("platform", "twitter")).strip().lower()
        topic = str(payload.get("topic", "")).strip() or str(target or "").strip()
        context = engine._collect_media_context()
        result = await engine.content_generator.generate_for_platform(platform, context, topic)
        if result.get("ok"):
            quality = result.get("quality", {})
            content = str(result.get("content", ""))
            preview = content[:500] + ("..." if len(content) > 500 else "")
            await engine.telegram.send_message(
                (
                    f"📰 AI-generated {platform} content ready.\n"
                    f"Quality: `{quality.get('score', 0)}`\n"
                    f"Topic: `{topic or 'auto'}`\n\n"
                    f"Preview:\n{preview}\n\n"
                    "Use `/media publish` to queue for delivery."
                ),
                priority="high",
            )
        else:
            reason = result.get("reason", "unknown")
            await engine.telegram.send_message(
                f"⚠️ Content generation failed: `{reason}`",
                priority="high",
            )
        return True

    if normalized in {"MEDIA_DRAFT", "PREPARE_MEDIA_DRAFT"}:
        payload = engine._parse_json_payload(target)
        topic = str(payload.get("topic", "")).strip() or str(target or "").strip()
        draft = engine._build_media_draft(topic)
        snapshot = engine.media_manager.get_status_snapshot()
        publish_note = {
            "draft_only": "Draft created only; no publish attempts will run.",
            "owner_approval": "Draft created; await owner approval before publishing.",
            "auto_post": "Draft created; auto-post is enabled when channel credentials are ready.",
        }.get(draft.get("mode", "owner_approval"), "Draft created.")
        await engine.telegram.send_message(
            (
                "📰 Sapphire media draft generated.\n"
                f"Title: `{draft.get('title', 'n/a')}`\n"
                f"Mode: `{draft.get('mode', 'owner_approval')}`\n"
                f"X ready: `{'YES' if snapshot.get('twitter_ready') else 'NO'}` | "
                f"Substack ready: `{'YES' if snapshot.get('substack_ready') else 'NO'}`\n"
                f"Policy: {publish_note}\n"
                "Use `/media status` to review channel readiness."
            ),
            priority="high",
        )
        return True

    if normalized in {"MEDIA_PUBLISH", "MEDIA_DISPATCH"}:
        gate.require("SAPPHIRE", Capability.MEDIA_PUBLISH, f"media_publish({target!r})")
        payload = engine._parse_json_payload(target)
        draft = engine._resolve_media_draft_for_publish(payload)
        targets = payload.get("targets", [])
        request = engine.media_manager.request_publish(
            topic=draft.get("topic", ""),
            title=draft.get("title", ""),
            body=draft.get("body", ""),
            targets=targets,
            source="telegram",
        )
        request_id = request.get("request_id")
        status = request.get("status")
        if status == "draft":
            await engine.telegram.send_message(
                "📰 Request ignored (mode=draft_only).", priority="high"
            )
        elif status == "pending_approval":
            await engine.telegram.send_message(
                f"📰 Request `{request_id}` is pending approval.", priority="high"
            )
        else:
            await engine.telegram.send_message(
                f"📰 Request `{request_id}` queued for delivery.", priority="high"
            )
        return True

    if normalized in {"MEDIA_APPROVE", "MEDIA_REQUEST_APPROVE"}:
        payload = engine._parse_json_payload(target)
        request_id = str(payload.get("request_id", "")).strip() or str(target or "").strip()
        if engine.media_manager.approve_request(request_id):
            await engine.telegram.send_message(f"✅ Approved `{request_id}`.", priority="high")
        else:
            await engine.telegram.send_message(
                f"❌ Failed to approve `{request_id}`.", priority="high"
            )
        return True

    if normalized in {"MEDIA_REJECT", "MEDIA_REQUEST_REJECT"}:
        payload = engine._parse_json_payload(target)
        request_id = str(payload.get("request_id", "")).strip() or str(target or "").strip()
        if engine.media_manager.reject_request(request_id):
            await engine.telegram.send_message(f"🛑 Rejected `{request_id}`.", priority="high")
        else:
            await engine.telegram.send_message(
                f"❌ Failed to reject `{request_id}`.", priority="high"
            )
        return True

    return False


# ── Security & VirusTotal ─────────────────────────────────────────────


async def handle_security_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle SECURITY_*, VT_*, SKILL_AUDIT_*, GATE_STATS commands."""
    normalized = action.upper()

    if normalized in {"SECURITY_STATUS", "VT_STATUS", "SKILL_SECURITY_STATUS"}:
        status = await engine._handle_security_skills_status_request({})
        last_scan = status.get("last_scan", {}) if isinstance(status, dict) else {}
        last_scan_type = str(last_scan.get("type", "none")).strip() or "none"
        last_scan_time = int(last_scan.get("timestamp", 0) or 0)
        last_scan_verdict = str(last_scan.get("verdict", "n/a")).strip() or "n/a"
        await engine.telegram.send_message(
            (
                "🛡️ **VIRUSTOTAL SKILL SECURITY**\n"
                f"Enabled: `{'YES' if status.get('enabled') else 'NO'}`\n"
                f"API key configured: `{'YES' if status.get('api_key_configured') else 'NO'}`\n"
                f"Policy mode: `{status.get('enforcement_mode', 'warn')}`\n"
                f"Skills dir: `{status.get('skills_dir', '')}`\n"
                f"Upload-on-miss: `{'YES' if status.get('upload_if_missing_default') else 'NO'}`\n"
                f"Last scan: `{last_scan_type}` at `{last_scan_time}` verdict `{last_scan_verdict}`"
            ),
            priority="medium",
        )
        return True

    if normalized in {"SECURITY_SCAN", "VT_SCAN", "SKILL_SECURITY_SCAN"}:
        payload = engine._parse_json_payload(target)
        requested_skill = str(payload.get("skill", "")).strip()
        if not requested_skill:
            requested_skill = str(target or "").strip()
        if requested_skill.startswith("{"):
            requested_skill = ""
        upload_if_missing = payload.get(
            "upload_if_missing", engine.vt_scanner.upload_if_missing_default
        )
        upload_bool = str(upload_if_missing).strip().lower() in {"1", "true", "yes", "on"}
        scan_scope = (
            requested_skill if requested_skill and requested_skill.lower() != "all" else "all"
        )
        await engine.telegram.send_message(
            f"🛡️ VirusTotal scan requested for `{scan_scope}` (upload-on-miss: `{'YES' if upload_bool else 'NO'}`).",
            priority="high",
        )
        result = await engine._handle_security_skill_scan_request(
            {"skill": requested_skill, "upload_if_missing": upload_bool}
        )
        if not result.get("ok"):
            await engine.telegram.send_message(
                f"❌ VirusTotal scan failed.\nReason: `{result.get('error', 'unknown')}`",
                priority="high",
            )
            return True
        if isinstance(result.get("results"), list):
            counts = result.get("counts", {})
            await engine.telegram.send_message(
                (
                    "✅ VirusTotal batch scan completed.\n"
                    f"Skills scanned: `{result.get('skills_scanned', 0)}`\n"
                    f"Benign: `{counts.get('benign', 0)}` | "
                    f"Suspicious: `{counts.get('suspicious', 0)}` | "
                    f"Malicious: `{counts.get('malicious', 0)}` | "
                    f"Unknown: `{counts.get('unknown', 0)}`\n"
                    f"Policy blocked: `{result.get('blocked_count', 0)}`"
                ),
                priority="high",
            )
        else:
            security = result.get("security", {})
            policy = security.get("policy", {}) if isinstance(security, dict) else {}
            await engine.telegram.send_message(
                (
                    f"✅ VirusTotal scan completed for `{result.get('skill', 'unknown')}`.\n"
                    f"Verdict: `{security.get('verdict', 'unknown')}` | "
                    f"Code Insight: `{security.get('code_insight_verdict', 'unknown')}`\n"
                    f"Policy: `{policy.get('mode', 'warn')}` | "
                    f"Allowed: `{'YES' if policy.get('allowed') else 'NO'}`\n"
                    f"Report: {result.get('vt', {}).get('report_url', 'n/a')}"
                ),
                priority="high",
            )
        return True

    if normalized == "SKILL_AUDIT":
        gate.require("EMERALD", Capability.SKILL_AUDIT, "telegram_skill_audit")
        content = str(target or "").strip()
        if content:
            report = engine.skill_auditor.audit_skill("telegram_submitted", content)
            formatted = engine.skill_auditor.format_community_report(report)
            engine.telegram.record_activity(
                EMERALD, "audit", f"Audited skill: {report.overall_severity.name}"
            )
            await engine.telegram.send_as(EMERALD, formatted)
        else:
            await engine.telegram.send_as(EMERALD, "Usage: /audit <skill content to scan>")
        return True

    if normalized == "SKILL_AUDIT_STATS":
        stats = engine.skill_auditor.get_stats()
        lines = ["*Skill Audit Statistics*"]
        lines.append(f"  Total audits: {stats.get('total_audits', 0)}")
        sev = stats.get("severity_breakdown", {})
        if sev:
            lines.append("  *Severity breakdown:*")
            for k, v in sorted(sev.items()):
                lines.append(f"    {k}: {v}")
        cats = stats.get("category_breakdown", {})
        if cats:
            lines.append("  *Category breakdown:*")
            for k, v in sorted(cats.items()):
                lines.append(f"    {k}: {v}")
        critical = stats.get("critical_skills", [])
        if critical:
            lines.append(f"  Critical skills: {', '.join(critical[:5])}")
        await engine.telegram.send_as(EMERALD, "\n".join(lines))
        return True

    if normalized in {"GATE_STATS", "PERMISSIONS", "PERM_STATS"}:
        stats = gate.stats()
        denials = gate.recent_denials(limit=5)
        lines = [
            "*🔐 Agent Permission Gate*",
            f"  Total checks: {stats.get('total_checks', 0)}",
            f"  Granted: {stats.get('granted', 0)}",
            f"  Denied: {stats.get('denied', 0)}",
            f"  Agents: {', '.join(stats.get('registered_agents', []))}",
        ]
        breakdown = stats.get("denied_breakdown", {})
        if breakdown:
            lines.append("  *Denial breakdown:*")
            for k, v in sorted(breakdown.items()):
                lines.append(f"    `{k}`: {v}")
        if denials:
            lines.append("  *Recent denials:*")
            for d in denials:
                lines.append(f"    `{d['agent_id']}` → `{d['capability']}`")
        await engine.telegram.send_as(OBSIDIAN, "\n".join(lines))
        return True

    return False


# ── Forum Collaboration ───────────────────────────────────────────────


async def handle_forum_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle FORUM_* control commands."""
    if getattr(engine, "forum", None) is None:
        return False
    normalized = action.upper()

    if normalized == "FORUM_TOP_TOPICS":
        payload = engine._parse_json_payload(target)
        category = str(payload.get("category", "")).strip()
        limit = int(payload.get("limit", 10) or 10)
        top = engine.forum.get_top_topics(limit=limit, category=category)
        if not top:
            await engine.telegram.send_as(
                EMERALD,
                "📭 No forum topics found"
                + (f" in category `{category}`" if category else "")
                + ".",
            )
        else:
            cat_label = f" [{category}]" if category else ""
            lines = [f"📊 **Top Forum Topics{cat_label}**\n"]
            for i, t in enumerate(top[:10], 1):
                score = float(t.get("score", 0))
                tid = t.get("topic_id", "?")
                title = str(t.get("title", "Untitled"))[:50]
                author = t.get("author", "?")
                lines.append(f"{i}. `{tid}` ⬆{score:+.0f} — *{title}* ({author})")
            await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "FORUM_VOTE_TOPIC":
        payload = engine._parse_json_payload(target)
        topic_id = str(payload.get("topic_id", "")).strip().upper()
        direction = str(payload.get("direction", "")).strip().lower()
        voter = str(payload.get("voter", "SAPPHIRE")).strip().upper()
        if not topic_id or not direction:
            await engine.telegram.send_message(
                "❌ Usage: `forum vote TOPIC-XXXXX up|down`", priority="high"
            )
            return True
        gate.require(voter, Capability.FORUM_WRITE, f"vote_topic({topic_id}, {direction})")
        result = engine.forum.vote_topic(topic_id, voter, direction)
        if result.get("ok"):
            await engine.telegram.send_message(
                f"✅ Voted `{direction}` on `{topic_id}` — score now **{result['score']:+.0f}** "
                f"(⬆{result.get('upvotes', 0)} ⬇{result.get('downvotes', 0)})",
                priority="medium",
            )
            approval_result = engine.forum.resolve_approval(topic_id)
            if approval_result.get("ok") and approval_result.get("status") in (
                "approved",
                "rejected",
            ):
                status = approval_result["status"]
                session_key = approval_result.get("session_key", "")
                emoji = "✅" if status == "approved" else "🚫"
                await engine.telegram.send_message(
                    f"{emoji} **Approval resolved:** `{topic_id}` → `{status.upper()}`\n"
                    f"Session: `{session_key}`\n"
                    f"Reason: {approval_result.get('reason', 'consensus reached')}",
                    priority="high",
                )
                engine._record_system_log(
                    f"Forum approval resolved: {topic_id} → {status}",
                    level="info",
                    tags=["forum", "approval", "governance"],
                    metadata={
                        "topic_id": topic_id,
                        "session_key": session_key,
                        "status": status,
                        "score": approval_result.get("score", 0),
                    },
                )
        else:
            await engine.telegram.send_message(
                f"❌ Vote failed: `{result.get('error', 'unknown')}`", priority="high"
            )
        return True

    if normalized == "FORUM_AGENTS":
        profiles = engine.forum.list_agent_profiles()
        lines = ["🤖 **Agent Personality Profiles**\n"]
        for _agent_id, p in profiles.items():
            lines.append(
                f"{p['emoji']} **{p['name']}** — {p['role']}\n"
                f"  Expertise: {', '.join(p['expertise'])}\n"
                f"  Voice: _{p['voice']}_\n"
                f"  Perspective: _{p['perspective']}_\n"
            )
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "FORUM_THREAD":
        payload = engine._parse_json_payload(target)
        topic_id = str(payload.get("topic_id", "")).strip().upper()
        if not topic_id:
            await engine.telegram.send_message(
                "❌ Usage: `forum thread TOPIC-XXXXX`", priority="high"
            )
            return True
        detail = engine.forum.get_topic_detail(topic_id)
        if not detail:
            await engine.telegram.send_message(f"❌ Topic `{topic_id}` not found.", priority="high")
            return True
        thread = engine.forum.get_thread(topic_id)
        lines = [
            f"🧵 **Thread: {detail.get('title', 'Untitled')}** (`{topic_id}`)\n"
            f"Author: {detail.get('author', '?')} | Score: {detail.get('score', 0):+.0f} | "
            f"Category: `{detail.get('category', 'general')}`\n"
        ]
        if not thread:
            lines.append("_No replies yet._")
        else:
            for r in thread[:15]:
                rid = r.get("reply_id", "?")
                author = r.get("author", "?")
                body_preview = str(r.get("body", ""))[:80]
                q = r.get("quality", {})
                quality_str = ""
                if q and q.get("ratings_count", 0) > 0:
                    quality_str = f" | Q:{q.get('helpfulness', 0):.1f}/{q.get('accuracy', 0):.1f}"
                lines.append(f"  💬 `{rid}` ({author}){quality_str}: {body_preview}")
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "FORUM_CREATE_TOPIC":
        payload = engine._parse_json_payload(target)
        result = await engine._handle_forum_create_topic_request(payload)
        if result.get("error"):
            await engine.telegram.send_message(
                f"❌ Topic creation failed: `{result['error']}`", priority="high"
            )
        else:
            topic = result.get("topic", {})
            await engine.telegram.send_message(
                f"✅ Topic created: `{topic.get('topic_id', '?')}` — *{topic.get('title', 'Untitled')[:50]}*\n"
                f"Category: `{topic.get('category', 'general')}` | Author: {topic.get('author', '?')}",
                priority="medium",
            )
        return True

    if normalized == "FORUM_PENDING_APPROVALS":
        pending = engine.forum.list_pending_approvals()
        if not pending:
            await engine.telegram.send_as(EMERALD, "📋 No pending approval workflows.")
        else:
            lines = [f"📋 **Pending Approvals** ({len(pending)})\n"]
            for item in pending[:10]:
                tid = item.get("topic_id", "?")
                title = str(item.get("title", ""))[:50]
                score = item.get("score", 0)
                up = item.get("upvotes", 0)
                down = item.get("downvotes", 0)
                key = item.get("session_key", "?")
                voters = ", ".join(item.get("voters", [])) or "none"
                lines.append(
                    f"• `{tid}` — *{title}*\n"
                    f"  Session: `{key}` | Score: {score:+.0f} (⬆{up} ⬇{down})\n"
                    f"  Voters: {voters}"
                )
            lines.append(f"\n_Threshold: {engine.forum.APPROVAL_THRESHOLD} votes to resolve._")
            await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    return False


# ── Bot Reputation & Points ───────────────────────────────────────────


async def handle_reputation_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle REP_* control commands."""
    if getattr(engine, "reputation", None) is None:
        return False
    normalized = action.upper()

    if normalized == "REP_LEADERBOARD":
        payload = engine._parse_json_payload(target)
        limit = max(1, min(25, int(payload.get("limit", 10))))
        board = engine.reputation.leaderboard(limit=limit)
        if not board:
            await engine.telegram.send_as(
                EMERALD, "🏆 Leaderboard is empty — no bots registered yet."
            )
        else:
            lines = [f"🏆 **Bot Leaderboard** (top {len(board)})\n"]
            for i, entry in enumerate(board, 1):
                bid = entry.get("bot_id", "?")
                comp = entry.get("composite", 0)
                score = entry.get("score", 0)
                ideas = entry.get("ideas_submitted", 0)
                accurate = entry.get("ideas_accurate", 0)
                pnl = entry.get("total_pnl", 0.0)
                status = entry.get("status", "active")
                medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
                lines.append(
                    f"{medal} `{bid}` — composite: {comp:.1f} | score: {score:.0f}\n"
                    f"   Ideas: {ideas} | Accurate: {accurate} | PnL: ${pnl:+,.2f} | {status}"
                )
            await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "REP_BOT_INFO":
        payload = engine._parse_json_payload(target)
        bot_id = str(payload.get("bot_id", "")).strip()
        if not bot_id:
            await engine.telegram.send_as(EMERALD, "⚠️ Please specify a bot ID.")
            return True
        result = engine.reputation.get_reputation(bot_id)
        if not result.get("ok"):
            await engine.telegram.send_as(EMERALD, f"⚠️ Bot `{bot_id.upper()}` not found.")
        else:
            status_emoji = {"active": "🟢", "warned": "🟡", "banned": "🔴"}.get(
                result.get("status", ""), "⚪"
            )
            lines = [
                f"📊 **Bot Reputation: `{result['bot_id']}`** {status_emoji}\n",
                f"Score: **{result.get('score', 0):.0f}** | Composite: **{result.get('composite', 0):.1f}**",
                f"Status: `{result.get('status', 'active')}`",
                f"Ideas: {result.get('ideas_submitted', 0)} "
                f"(✅ {result.get('ideas_accurate', 0)} / ❌ {result.get('ideas_inaccurate', 0)})",
                f"Profitable: {result.get('ideas_profitable', 0)} "
                f"/ Unprofitable: {result.get('ideas_unprofitable', 0)}",
                f"Total PnL: ${result.get('total_pnl', 0.0):+,.2f}",
                f"Quality avg: {result.get('quality_avg', 0.0):.2f}",
                f"Penalties: {result.get('penalties', 0)} | Rewards: {result.get('rewards', 0)}",
            ]
            if result.get("ban_reason"):
                lines.append(f"Ban reason: _{result['ban_reason']}_")
            await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "REP_BOT_COUNT":
        counts = engine.reputation.bot_count()
        total = sum(counts.values())
        await engine.telegram.send_message(
            f"🤖 **Bot Census**\n"
            f"Total: **{total}**\n"
            f"🟢 Active: {counts.get('active', 0)}\n"
            f"🟡 Warned: {counts.get('warned', 0)}\n"
            f"🔴 Banned: {counts.get('banned', 0)}",
            priority="medium",
        )
        return True

    if normalized == "REP_BAN_BOT":
        gate.require("SAPPHIRE", Capability.REPUTATION_ADMIN, "ban_bot_via_telegram")
        payload = engine._parse_json_payload(target)
        bot_id = str(payload.get("bot_id", "")).strip()
        reason = str(payload.get("reason", "manual ban via Telegram"))[:200]
        if not bot_id:
            await engine.telegram.send_as(SAPPHIRE, "⚠️ Please specify a bot ID to ban.")
            return True
        result = engine.reputation.ban(bot_id, reason)
        if result.get("ok"):
            await engine.telegram.send_as(
                SAPPHIRE,
                f"🔴 **Bot banned:** `{bot_id.upper()}`\nReason: _{reason}_\nScore: {result.get('score', 0):.0f}",
            )
        else:
            await engine.telegram.send_as(SAPPHIRE, f"⚠️ Failed to ban `{bot_id}`.")
        return True

    if normalized == "REP_PENALIZE_BOT":
        gate.require("SAPPHIRE", Capability.REPUTATION_ADMIN, "penalize_bot_via_telegram")
        payload = engine._parse_json_payload(target)
        bot_id = str(payload.get("bot_id", "")).strip()
        reason = str(payload.get("reason", "manual penalty via Telegram"))[:200]
        points = float(payload.get("points", 0))
        if not bot_id:
            await engine.telegram.send_as(SAPPHIRE, "⚠️ Please specify a bot ID to penalize.")
            return True
        result = engine.reputation.penalize(bot_id, reason, points=points)
        if result.get("ok"):
            await engine.telegram.send_as(
                SAPPHIRE,
                f"⚠️ **Bot penalized:** `{bot_id.upper()}`\n"
                f"Reason: _{reason}_ | Score: {result.get('score', 0):.0f} | Status: {result.get('status', '?')}",
            )
        else:
            await engine.telegram.send_as(SAPPHIRE, f"⚠️ Failed to penalize `{bot_id}`.")
        return True

    return False


# ── Swarm Intelligence ────────────────────────────────────────────────


async def handle_swarm_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle SWARM_* control commands."""
    if getattr(engine, "swarm", None) is None:
        return False
    normalized = action.upper()

    if normalized == "SWARM_SUBMIT_IDEA":
        payload = engine._parse_json_payload(target)
        bot_id = str(payload.get("bot_id", "")).strip()
        symbol = str(payload.get("symbol", "")).strip()
        direction = str(payload.get("direction", "")).strip()
        confidence = float(payload.get("confidence", 0.5))
        timeframe = str(payload.get("timeframe", "1h")).strip()
        rationale = str(payload.get("rationale", ""))[:500]
        target_price = float(payload.get("target_price", 0))
        stop_loss = float(payload.get("stop_loss", 0))
        result = engine.swarm.submit_idea(
            bot_id=bot_id,
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            timeframe=timeframe,
            rationale=rationale,
            target_price=target_price,
            stop_loss=stop_loss,
        )
        if result.get("ok"):
            arrow = "🟢 LONG" if result["direction"] == "LONG" else "🔴 SHORT"
            await engine.telegram.send_message(
                f"🐝 **Swarm idea received:** `{result['idea_id']}`\n"
                f"Bot: `{bot_id.upper()}` | {arrow} `{symbol}`\n"
                f"Confidence: {confidence:.0%} | Rep weight: {result['reputation_weight']:.2f}\n"
                f"Weighted score: {result['weighted_score']:.3f}",
                priority="medium",
            )
        else:
            await engine.telegram.send_as(
                EMERALD, f"⚠️ Swarm idea rejected: {result.get('error', '?')}"
            )
        return True

    if normalized == "SWARM_AGGREGATE":
        payload = engine._parse_json_payload(target)
        symbol = str(payload.get("symbol", "")).strip()
        if not symbol:
            await engine.telegram.send_as(EMERALD, "⚠️ Please specify a symbol to aggregate.")
            return True
        result = engine.swarm.aggregate(symbol)
        if not result.get("ok"):
            await engine.telegram.send_as(
                EMERALD, f"⚠️ Aggregation failed: {result.get('error', '?')}"
            )
            return True
        consensus_emoji = {
            "LONG": "🟢",
            "SHORT": "🔴",
            "LEAN_LONG": "🟡↗",
            "LEAN_SHORT": "🟡↘",
            "NEUTRAL": "⚪",
        }.get(result["consensus"], "⚪")
        lines = [
            f"🐝 **Swarm Consensus: `{symbol}`** {consensus_emoji}\n",
            f"Direction: **{result['consensus']}** | Conviction: **{result['conviction']:.0%}**",
            f"Ideas: {result['total_ideas']} (🟢 {result['long_count']} long / 🔴 {result['short_count']} short)",
            f"Weighted: Long {result['weighted_long']:.3f} | Short {result['weighted_short']:.3f}",
            f"Net score: {result['net_score']:+.3f}",
        ]
        if result.get("avg_target_price"):
            lines.append(f"Avg target: ${result['avg_target_price']:,.2f}")
        if result.get("avg_stop_loss"):
            lines.append(f"Avg stop: ${result['avg_stop_loss']:,.2f}")
        if result.get("contributors"):
            lines.append("\n**Contributors:**")
            for c in result["contributors"][:10]:
                d = "🟢" if c["direction"] == "LONG" else "🔴"
                lines.append(
                    f"  {d} `{c['bot_id']}` — conf: {c['confidence']:.0%}, "
                    f"weight: {c['reputation_weight']:.2f}, score: {c['weighted_score']:.3f}"
                )
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "SWARM_STATS":
        stats = engine.swarm.stats()
        await engine.telegram.send_message(
            f"🐝 **Swarm Statistics**\n"
            f"Total ideas submitted: {stats['total_ideas_submitted']}\n"
            f"Open: {stats['open_ideas']} | Resolved: {stats['resolved_ideas']} | Expired: {stats['expired_ideas']}\n"
            f"Active symbols: {stats['active_symbols']}",
            priority="medium",
        )
        return True

    if normalized == "SWARM_OPEN_IDEAS":
        payload = engine._parse_json_payload(target)
        symbol = str(payload.get("symbol", "")).strip()
        ideas = engine.swarm.open_ideas(symbol)
        if not ideas:
            msg = "🐝 No open swarm ideas" + (f" for `{symbol}`." if symbol else ".")
            await engine.telegram.send_as(EMERALD, msg)
        else:
            lines = [f"🐝 **Open Swarm Ideas** ({len(ideas)})\n"]
            for idea in ideas[:15]:
                d = "🟢" if idea["direction"] == "LONG" else "🔴"
                lines.append(
                    f"  {d} `{idea['idea_id']}` — `{idea['symbol']}` {idea['direction']} "
                    f"by `{idea['bot_id']}` (conf: {idea['confidence']:.0%}, weight: {idea['reputation_weight']:.2f})"
                )
            await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    return False


# ── Collaborative Learning & Outreach ─────────────────────────────────


async def handle_learning_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle LEARN_* and OUTREACH_* control commands."""
    if getattr(engine, "learning", None) is None:
        return False
    normalized = action.upper()

    if normalized == "LEARN_REPORT":
        report = engine.learning.generate_report()
        if report.get("total_records", 0) == 0:
            await engine.telegram.send_as(EMERALD, "📚 No learning data recorded yet.")
            return True
        overall = report.get("overall", {})
        lines = [
            f"📚 **Swarm Learning Report** ({report['total_records']} outcomes)\n",
            f"Win rate: **{overall.get('win_rate', 0):.0%}** | "
            f"PnL: **${overall.get('total_pnl', 0):+,.2f}** | "
            f"Avg: ${overall.get('avg_pnl', 0):+,.2f}",
        ]
        symbols = report.get("symbols", [])
        if symbols:
            lines.append("\n**Symbols:**")
            for s in symbols[:5]:
                edge_emoji = (
                    "🟢" if s["edge"] == "positive" else ("🔴" if s["edge"] == "negative" else "⚪")
                )
                lines.append(
                    f"  {edge_emoji} `{s['symbol']}` — {s['win_rate']:.0%} win "
                    f"({s['count']} trades, ${s['total_pnl']:+,.2f})"
                )
        directions = report.get("directions", {})
        if any(directions.get(d, {}).get("count", 0) > 0 for d in ("LONG", "SHORT")):
            lines.append("\n**Directions:**")
            for d in ("LONG", "SHORT"):
                dd = directions.get(d, {})
                if dd.get("count", 0) > 0:
                    lines.append(
                        f"  {'🟢' if d == 'LONG' else '🔴'} {d}: {dd['win_rate']:.0%} win ({dd['count']} trades)"
                    )
        cal = report.get("conviction_calibration", [])
        if cal:
            lines.append("\n**Conviction Calibration:**")
            for c in cal:
                cal_ok = "✅" if c.get("calibrated") else "⚠️"
                lines.append(
                    f"  {cal_ok} {c['conviction_range']}: {c['actual_win_rate']:.0%} actual ({c['count']} trades)"
                )
        synergy = report.get("bot_synergy", [])
        if synergy:
            lines.append("\n**Bot Synergy:**")
            for s in synergy[:5]:
                syn_emoji = (
                    "🤝" if s["synergy"] == "strong" else ("💥" if s["synergy"] == "weak" else "🤷")
                )
                lines.append(
                    f"  {syn_emoji} `{s['pair']}` — {s['win_rate']:.0%} ({s['count']} trades)"
                )
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "LEARN_SUMMARY":
        s = engine.learning.summary()
        await engine.telegram.send_message(
            f"📚 **Learning Summary**\n"
            f"Records: {s['total_records']} | Win rate: {s.get('overall_win_rate', 0):.0%}\n"
            f"PnL: ${s.get('total_pnl', 0):+,.2f}\n"
            f"Symbols: {s['symbols_tracked']} | "
            f"Timeframes: {s['timeframes_tracked']} | "
            f"Bot pairs: {s['bot_pairs_tracked']}",
            priority="medium",
        )
        return True

    if normalized == "LEARN_BIAS":
        payload = engine._parse_json_payload(target)
        symbol = str(payload.get("symbol", "")).strip().upper()
        direction = str(payload.get("direction", "")).strip().upper()
        timeframe = str(payload.get("timeframe", "1h")).strip()
        sym_bias = engine.learning.get_symbol_bias(symbol) if symbol else 0.0
        dir_bias = engine.learning.get_direction_bias(direction) if direction else 0.0
        tf_bias = engine.learning.get_timeframe_bias(timeframe)
        adjusted = engine.learning.adaptive_confidence(
            symbol or "?", direction or "LONG", timeframe, 0.5
        )
        lines = ["📚 **Learning Bias Check**\n"]
        if symbol:
            lines.append(f"Symbol `{symbol}`: bias = {sym_bias:+.2f}")
        if direction:
            lines.append(f"Direction `{direction}`: bias = {dir_bias:+.2f}")
        lines.append(f"Timeframe `{timeframe}`: bias = {tf_bias:+.2f}")
        lines.append(f"\nAdaptive confidence (raw 50%): **{adjusted:.0%}**")
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "OUTREACH_COMPOSE":
        payload = engine._parse_json_payload(target)
        template = str(payload.get("template", "general_invite")).strip()
        symbol = str(payload.get("symbol", "")).strip().upper()
        custom_body = str(payload.get("custom_body", ""))
        s = engine.learning.summary()
        post = engine.outreach.compose_outreach(
            template=template,
            symbol=symbol,
            custom_body=custom_body,
            total_ideas=s.get("total_records", 0),
            win_rate=round(s.get("overall_win_rate", 0) * 100, 1),
        )
        if not post.get("ok"):
            await engine.telegram.send_message(
                f"❌ Outreach compose failed: {post.get('error', 'unknown')}", priority="medium"
            )
            return True
        cooldown = engine.outreach.can_post()
        if not cooldown["allowed"]:
            await engine.telegram.send_message(
                f"⏳ Outreach on cooldown — wait {cooldown['wait_seconds']}s.", priority="medium"
            )
            return True
        dispatch_result = engine.forum.publish_scout_note(
            {
                "title": post["title"],
                "body": post["body"],
                "category": post.get("category", "trade_idea"),
                "lane": post.get("lane", "external"),
                "source": "molthub_outreach",
            }
        )
        engine.outreach.record_dispatch(post, dispatch_result)
        ok = dispatch_result.get("ok", False)
        mode = dispatch_result.get("mode", "local")
        await engine.telegram.send_message(
            f"📡 **Outreach {'dispatched' if ok else 'failed'}** "
            f"(template=`{template}`, mode=`{mode}`"
            + (f", symbol=`{symbol}`" if symbol else "")
            + ")",
            priority="medium",
        )
        return True

    if normalized == "OUTREACH_STATS":
        s = engine.outreach.stats()
        lines = [
            "📊 **Outreach Statistics**\n",
            f"Total dispatched: {s['total_dispatched']}",
            f"Successful: {s['successful']}",
            f"Failed: {s['failed']}",
        ]
        if s["total_dispatched"] > 0:
            lines.append(f"Success rate: {s.get('success_rate', 0):.0%}")
        if s.get("symbols_targeted"):
            lines.append(f"Symbols: {', '.join(s['symbols_targeted'])}")
        if s.get("total_redactions", 0) > 0:
            lines.append(f"⚠️ Redactions: {s['total_redactions']}")
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "OUTREACH_TEMPLATES":
        templates = engine.outreach.available_templates()
        lines = ["📋 **Available Outreach Templates**\n"]
        for t in templates:
            sym_note = " _(requires symbol)_" if t["requires_symbol"] else ""
            lines.append(f"• `{t['name']}` — {t['title']}{sym_note}")
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    return False


# ── Task Management ───────────────────────────────────────────────────


async def handle_task_commands(engine: AlphaEngine, target: str, action: str, value: float) -> bool:
    """Handle TASK_* control commands."""
    if getattr(engine, "tasks", None) is None:
        return False
    normalized = action.upper()

    if normalized == "TASK_CREATE":
        payload = engine._parse_json_payload(target)
        title = str(payload.get("title", "")).strip()
        if not title:
            parts = str(target or "").strip().split("|")
            title = parts[0].strip() if parts else ""
        if not title:
            await engine.telegram.send_message(
                "❌ Task title required. Use `task create <title>`.", priority="high"
            )
            return True
        phase = str(payload.get("phase", "")).strip()
        agent = str(payload.get("agent", "UNASSIGNED")).strip()
        priority = str(payload.get("priority", "medium")).strip()
        description = str(payload.get("description", "")).strip()
        tags_raw = payload.get("tags")
        tags = tags_raw if isinstance(tags_raw, list) else None
        result = engine.tasks.create_task(
            title=title,
            phase=phase,
            agent=agent,
            priority=priority,
            description=description,
            tags=tags,
        )
        if result.get("ok"):
            task = result["task"]
            engine.telegram.record_activity(
                EMERALD, "task", f"Created {task['task_id']}: {task['title']}"
            )
            await engine.telegram.send_message(
                f"✅ Task created: `{task['task_id']}`\nTitle: {task['title']}\n"
                f"Agent: {task['agent']} | Priority: {task['priority']}\nStatus: {task['status']}",
                priority="medium",
            )
        else:
            await engine.telegram.send_message(
                f"❌ Task creation failed: {result.get('error', 'unknown')}", priority="high"
            )
        return True

    if normalized == "TASK_LIST":
        payload = engine._parse_json_payload(target)
        phase = str(payload.get("phase", "")).strip()
        agent = str(payload.get("agent", "")).strip()
        status_filter = str(payload.get("status", "")).strip()
        result = engine.tasks.list_tasks(phase=phase, agent=agent, status=status_filter, limit=20)
        tasks_list = result.get("tasks", [])
        if not tasks_list:
            await engine.telegram.send_message(
                "📋 No tasks found matching filters.", priority="medium"
            )
            return True
        lines = [f"📋 **Tasks** ({result['showing']}/{result['total']})\n"]
        status_emoji = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅",
            "blocked": "🚫",
            "cancelled": "❌",
        }
        for t in tasks_list:
            emoji = status_emoji.get(t["status"], "•")
            lines.append(
                f"{emoji} `{t['task_id']}` — {t['title']}\n   Agent: {t['agent']} | {t['priority']} | {t['status']}"
            )
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "TASK_UPDATE":
        payload = engine._parse_json_payload(target)
        task_id = str(payload.get("task_id", "")).strip()
        if not task_id:
            parts = str(target or "").strip().split()
            task_id = parts[0] if parts else ""
        if not task_id:
            await engine.telegram.send_message(
                "❌ Task ID required. Use `task update <TASK-ID> <status>`.", priority="high"
            )
            return True
        new_status = str(payload.get("status", "")).strip()
        new_priority = str(payload.get("priority", "")).strip()
        new_agent = str(payload.get("agent", "")).strip()
        result = engine.tasks.update_task(
            task_id=task_id, status=new_status, priority=new_priority, agent=new_agent
        )
        if result.get("ok"):
            task = result["task"]
            engine.telegram.record_activity(
                EMERALD, "task", f"Updated {task['task_id']}: status={task['status']}"
            )
            await engine.telegram.send_message(
                f"✅ Task updated: `{task['task_id']}`\nStatus: {task['status']} | Priority: {task['priority']}\nAgent: {task['agent']}",
                priority="medium",
            )
        else:
            await engine.telegram.send_message(
                f"❌ Update failed: {result.get('error', 'unknown')}", priority="high"
            )
        return True

    if normalized == "TASK_REPORT":
        payload = engine._parse_json_payload(target)
        phase = str(payload.get("phase", "")).strip()
        agent = str(payload.get("agent", "")).strip()
        result = engine.tasks.progress_report(phase=phase, agent=agent)
        if result["total"] == 0:
            await engine.telegram.send_message("📊 No tasks to report on.", priority="medium")
            return True
        ms = result["milestones_summary"]
        dlv = result["deliverables_summary"]
        lines = [
            "📊 **Task Progress Report**\n",
            f"Total tasks: {result['total']}",
            f"Completion: {result['completion_rate'] * 100:.1f}%\n",
            "**By status:**",
        ]
        for s, count in sorted(result["by_status"].items()):
            lines.append(f"  • {s}: {count}")
        lines.append("\n**By agent:**")
        for a, info in sorted(result["by_agent"].items()):
            lines.append(
                f"  • {a}: {info['completed']}/{info['total']} done"
                + (f" ({info['in_progress']} active)" if info.get("in_progress") else "")
            )
        lines.append(f"\nMilestones: {ms['completed']}/{ms['total']} done")
        lines.append(f"Deliverables: {dlv['verified']}/{dlv['total']} verified")
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "TASK_SUMMARY":
        result = engine.tasks.summary()
        lines = [
            "📋 **Task Summary**\n",
            f"Tasks: {result['total_tasks']}",
            f"Milestones: {result['total_milestones']}",
            f"Deliverables: {result['total_deliverables']}",
        ]
        if result.get("by_status"):
            lines.append("\n**Status:**")
            for s, c in sorted(result["by_status"].items()):
                lines.append(f"  • {s}: {c}")
        if result.get("agents"):
            lines.append("\n**Agents:**")
            for a, c in sorted(result["agents"].items()):
                lines.append(f"  • {a}: {c}")
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized == "TASK_AGENT_REPORT":
        payload = engine._parse_json_payload(target)
        agent = str(payload.get("agent", "")).strip().upper()
        if not agent:
            agent = str(target or "").strip().upper().split()[0] if target else ""
        if not agent:
            await engine.telegram.send_message(
                "❌ Agent name required. Use `task agent <AGENT>`.", priority="high"
            )
            return True
        result = engine.tasks.agent_report(agent)
        if not result.get("ok"):
            await engine.telegram.send_message(
                f"❌ {result.get('error', 'Agent report failed.')}", priority="high"
            )
            return True
        if result["total"] == 0:
            await engine.telegram.send_message(
                f"📊 No tasks assigned to {agent}.", priority="medium"
            )
            return True
        lines = [
            f"📊 **{agent} Task Report**\n",
            f"Total: {result['total']} | Done: {result['completed']} | Active: {result['in_progress']}",
            f"Blocked: {result['blocked']} | Completion: {result['completion_rate'] * 100:.1f}%\n",
        ]
        status_emoji = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅",
            "blocked": "🚫",
            "cancelled": "❌",
        }
        for t in result["tasks"][:15]:
            emoji = status_emoji.get(t["status"], "•")
            ms_str = (
                f" MS:{t['milestones_done']}/{t['milestones_total']}"
                if t["milestones_total"]
                else ""
            )
            lines.append(f"{emoji} `{t['task_id']}` {t['title']}{ms_str}")
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    return False


# ── Scout/Forum Publishing ────────────────────────────────────────────


async def handle_scout_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle SCOUT_* and FORUM_SCOUT_* control commands."""
    if getattr(engine, "forum", None) is None:
        return False
    normalized = action.upper()

    if normalized in {"SCOUT_STATUS", "FORUM_SCOUT_STATUS"}:
        status = engine.forum.scout_status()
        profile = status.get("profile", {}) if isinstance(status, dict) else {}
        registration = status.get("registration", {}) if isinstance(status, dict) else {}
        bridge = status.get("external_bridge", {}) if isinstance(status, dict) else {}
        await engine.telegram.send_message(
            (
                "🛰️ **SCOUT STATUS**\n"
                f"Agent: `{profile.get('agent_id', 'SAPPHIRE_SCOUT')}`\n"
                f"Sensitive access: `{profile.get('sensitive_data_access', 'none')}`\n"
                f"Registered: `{'YES' if registration.get('registered') else 'NO'}`"
                + (f" (@{registration.get('username')})" if registration.get("username") else "")
                + "\n"
                f"Dispatch mode: `{bridge.get('dispatch_mode', 'none')}`\n"
                f"External register URL: `{'YES' if bridge.get('register_url_configured') else 'NO'}`\n"
                f"External post URL: `{'YES' if bridge.get('post_url_configured') else 'NO'}`\n"
                f"Fallback hook ready: `{'YES' if bridge.get('fallback_hook_token_configured') and bridge.get('fallback_hook_url_configured') and bridge.get('fallback_chat_id_configured') else 'NO'}`"
            ),
            priority="medium",
        )
        return True

    if normalized in {"SCOUT_REGISTER", "FORUM_SCOUT_REGISTER"}:
        payload = engine._parse_json_payload(target)
        username = str(payload.get("username", "")).strip()
        if not username:
            fallback_username = str(target or "").strip().split(" ", 1)[0]
            username = fallback_username.strip()
        if not username:
            await engine.telegram.send_message(
                "❌ Scout register requires a username. Use `/scout register <username> [display_name]`.",
                priority="high",
            )
            return True
        display_name = str(payload.get("display_name", "")).strip()
        if not display_name:
            chunks = str(target or "").strip().split(" ", 1)
            display_name = chunks[1].strip() if len(chunks) > 1 else "Sapphire Scout"
        bio = (
            str(payload.get("bio", "")).strip()
            or "Least-privilege scout for public collaboration. No secrets, no trading actions."
        )
        result = await engine._handle_forum_scout_register_request(
            {"username": username, "display_name": display_name, "bio": bio}
        )
        if not result.get("ok"):
            await engine.telegram.send_message(
                f"❌ Scout registration failed.\nReason: `{result.get('error', 'unknown')}`",
                priority="high",
            )
        return True

    if normalized in {"SCOUT_PUBLISH", "FORUM_SCOUT_PUBLISH"}:
        payload = engine._parse_json_payload(target)
        body = str(payload.get("body", "")).strip()
        if not body:
            body = str(target or "").strip()
        if not body:
            await engine.telegram.send_message(
                "❌ Scout publish requires message body text. Use `/scout publish <note>`.",
                priority="high",
            )
            return True
        result = await engine._handle_forum_scout_publish_request(
            {
                "topic_id": str(payload.get("topic_id", "")).strip(),
                "post_id": str(payload.get("post_id", "")).strip(),
                "title": str(payload.get("title", "")).strip(),
                "body": body,
                "author": str(payload.get("author", "")).strip() or "SAPPHIRE_SCOUT",
                "kind": str(payload.get("kind", "")).strip() or "note",
                "lane": str(payload.get("lane", "")).strip() or "external",
                "state": str(payload.get("state", "")).strip() or "open",
                "priority": str(payload.get("priority", "")).strip() or "medium",
                "tags": payload.get("tags", ["scout", "external"]),
            }
        )
        if not result.get("ok"):
            await engine.telegram.send_message(
                f"❌ Scout publish failed.\nReason: `{result.get('error', 'unknown')}`",
                priority="high",
            )
            return True
        dispatch = result.get("dispatch", {}) if isinstance(result, dict) else {}
        metadata = dispatch.get("metadata", {}) if isinstance(dispatch, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        reason = str(dispatch.get("reason", "unknown")).strip() or "unknown"
        dispatch_action = str(result.get("dispatch_action", "publish")).strip() or "publish"
        outcome = "external post accepted."
        if reason == "ok_verified":
            outcome = "accepted and verification challenge solved automatically; content should be publicly visible."
        elif reason == "ok_pending_verification" or metadata.get("verification_required"):
            outcome = "accepted by Moltbook, pending verification before full feed visibility."
        elif reason == "moltbook_rate_limited":
            retry_after_minutes = int(metadata.get("retry_after_minutes", 0) or 0)
            retry_after_seconds = int(metadata.get("retry_after_seconds", 0) or 0)
            if retry_after_minutes > 0:
                outcome = f"provider cooldown active; retry in about {retry_after_minutes} minutes."
            elif retry_after_seconds > 0:
                outcome = f"provider cooldown active; retry in about {retry_after_seconds} seconds."
            else:
                outcome = "provider cooldown active; retry after the next rate-limit window."
        elif reason == "moltbook_pending_claim":
            outcome = (
                "account is pending claim; owner claim completion is required before publishing."
            )
        elif reason == "moltbook_already_registered":
            outcome = "provider already has this scout account registered."
        elif not dispatch.get("dispatched"):
            outcome = "external publish blocked; note remains stored locally for retry."
        await engine.telegram.send_message(
            (
                f"🛰️ Scout {dispatch_action} processed for topic `{result.get('topic_id', 'n/a')}`.\n"
                f"Dispatch mode: `{dispatch.get('mode', 'none')}` | "
                f"Dispatch: `{'YES' if dispatch.get('dispatched') else 'NO'}`\n"
                f"Reason: `{reason}`\n"
                f"Outcome: {outcome}\n"
                "Benefit: external collaboration remains sanitized and auditable."
            ),
            priority="high",
        )
        return True

    return False


# ── Execution & Trading Configuration ─────────────────────────────────


async def handle_execution_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle execution stage, TradingView config, autonomy session, and venue allocation commands."""
    normalized = action.upper()

    if normalized in {"SET_EXECUTION_STAGE", "SET_DEX_EXECUTION_STAGE", "PROMOTION_STAGE"}:
        requested = engine._parse_execution_stage_token(target)
        if not requested:
            await engine.telegram.send_message(
                "❌ Invalid stage. Use one of: `paper`, `staged_live`, `full_live`.",
                priority="high",
            )
            return True
        applied = engine._set_execution_stage(requested, source="telegram")
        await engine.telegram.send_message(
            (
                f"✅ DEX execution stage set to `{applied.get('dex_execution_stage', requested)}`.\n"
                f"Live dispatch: `{'ON' if applied.get('stage_multiplier', 0) > 0 else 'OFF'}` | "
                f"Effective qty: `{applied.get('effective_quantity', 0.0)}`"
            ),
            priority="high",
        )
        return True

    if normalized in {"SET_TRADING_EXECUTION", "SET_EXECUTION"}:
        if not engine._tradingview_integration_enabled:
            engine._tradingview_execution_enabled = False
            await engine.telegram.send_message(
                (
                    "ℹ️ TradingView integration is disabled by policy (`SAPPHIRE_TRADINGVIEW_INTEGRATION_ENABLED=false`).\n"
                    "No TradingView signal mode changes were applied.\n"
                    "Core runtime focus remains ASTER/LIGHTER execution + autonomy operations."
                ),
                priority="medium",
            )
            return True
        mode = str(target or "").strip().upper()
        if mode not in {"ON", "OFF", "TRUE", "FALSE", "1", "0"}:
            await engine.telegram.send_message(
                "❌ Invalid TradingView signal mode. Use `/trade on [qty]` or `/trade off`.",
                priority="high",
            )
            return True
        enable_execution = mode in {"ON", "TRUE", "1"}
        quantity_value = max(0.0, float(value or 0.0))
        quantity_result: dict[str, Any] | None = None
        engine._tradingview_execution_enabled = enable_execution
        if enable_execution:
            if quantity_value > 0:
                quantity_result = engine._set_tradingview_default_quantity(quantity_value)
            elif engine._tradingview_default_quantity <= 0:
                quantity_result = engine._set_tradingview_default_quantity(
                    engine._recommended_default_trade_quantity()
                )
        engine._record_system_log(
            f"TradingView signal mode set to {'LIVE' if enable_execution else 'WORKBENCH_DRY-RUN'}"
            + (f" (qty={engine._tradingview_default_quantity})" if enable_execution else ""),
            level="warning",
            tags=["control", "execution_mode"],
            metadata={
                "execution_enabled": enable_execution,
                "default_quantity": engine._tradingview_default_quantity,
            },
        )
        if enable_execution:
            qty_note = f"Default qty `{engine._tradingview_default_quantity}`."
            if quantity_result and quantity_result.get("capped"):
                qty_note = (
                    f"Default qty capped to `{quantity_result.get('applied')}` "
                    f"(cap `{quantity_result.get('cap')}`)."
                )
            await engine.telegram.send_message(
                f"✅ TradingView signal mode: `LIVE`. {qty_note}", priority="high"
            )
        else:
            await engine.telegram.send_message(
                "🧪 TradingView signal mode: `WORKBENCH_DRY-RUN` (signals captured for research/backtests only).",
                priority="high",
            )
        return True

    if normalized in {"SET_TRADINGVIEW_DEFAULT_QUANTITY", "SET_DEFAULT_QUANTITY"}:
        if not engine._tradingview_integration_enabled:
            await engine.telegram.send_message(
                "ℹ️ TradingView integration is disabled, so default TradingView quantity is not active.\n"
                "To re-enable later, set `SAPPHIRE_TRADINGVIEW_INTEGRATION_ENABLED=true` and redeploy alpha.",
                priority="medium",
            )
            return True
        result = engine._set_tradingview_default_quantity(float(value or 0.0))
        if not result.get("ok"):
            await engine.telegram.send_message(
                "❌ Default quantity must be greater than zero.", priority="high"
            )
            return True
        engine._record_system_log(
            "TradingView default quantity updated",
            level="warning",
            tags=["control", "execution_mode"],
            metadata={
                "requested_quantity": result.get("requested"),
                "applied_quantity": result.get("applied"),
                "capped": bool(result.get("capped")),
                "cap": result.get("cap"),
            },
        )
        if result.get("capped"):
            await engine.telegram.send_message(
                f"⚠️ Default quantity capped to `{result.get('applied')}` "
                f"(requested `{result.get('requested')}`, cap `{result.get('cap')}`).",
                priority="high",
            )
        else:
            live_note = "LIVE" if engine._tradingview_execution_enabled else "DRY-RUN"
            await engine.telegram.send_message(
                f"✅ Default TradingView quantity set to `{result.get('applied')}` (mode `{live_note}`).",
                priority="high",
            )
        return True

    if normalized == "APPROVE_ALL_SESSIONS":
        decision_payload = engine._parse_session_decision_payload(target)
        note = str(decision_payload.get("note", "")).strip()[:400]
        pending_keys = engine._pending_autonomy_session_keys()
        if not pending_keys:
            await engine.telegram.send_message(
                "ℹ️ No pending autonomy sessions to approve.", priority="high"
            )
            return True
        success_count = 0
        failed: list[str] = []
        for session_key in pending_keys:
            result = await engine._apply_autonomy_session_decision(
                session_key=session_key,
                decision="APPROVE",
                note=note,
                source="owner_bulk",
            )
            if result.get("dispatched"):
                success_count += 1
            else:
                failed.append(
                    f"{result.get('session_key', session_key)}:{result.get('reason', 'unknown')}"
                )
        if failed:
            await engine.telegram.send_message(
                f"⚠️ Bulk approval completed with partial failures.\n"
                f"Approved: `{success_count}` / `{len(pending_keys)}`\n"
                f"Failed: `{'; '.join(failed[:5])}`\n"
                "Expected outcome: successful sessions continue without owner delay.\n"
                "Next step: re-run `/approve_all` after resolving listed failures.",
                priority="high",
            )
        else:
            await engine.telegram.send_message(
                f"✅ Bulk approval completed. Approved `{success_count}` pending session(s).\n"
                "Expected outcome: queued autonomy changes move immediately into execution.",
                priority="high",
            )
        return True

    if normalized in {"APPROVE_SESSION", "REJECT_SESSION"}:
        decision_payload = engine._parse_session_decision_payload(target)
        session_key = engine._resolve_autonomy_session_key(decision_payload.get("session_key", ""))
        note = str(decision_payload.get("note", "")).strip()
        decision = "APPROVE" if normalized == "APPROVE_SESSION" else "REJECT"
        if not session_key:
            await engine.telegram.send_message(
                "⚠️ No pending autonomy session found. Trigger one with `/autonomy` first.",
                priority="high",
            )
            return True
        result = await engine._apply_autonomy_session_decision(
            session_key=session_key,
            decision=decision,
            note=note,
            source="owner_manual",
        )
        if result.get("dispatched"):
            await engine.telegram.send_message(
                f"✅ Session `{session_key}` marked `{decision}`.\n"
                f"Dispatch: `{result.get('dispatch_session_key', 'n/a')}`\n"
                "Expected outcome: session state is synchronized and downstream action is unblocked.",
                priority="high",
            )
        else:
            await engine.telegram.send_message(
                f"⚠️ Session decision captured locally but dispatch failed for `{session_key}`.\n"
                f"Reason: `{result.get('reason', 'unknown')}`\n"
                "Benefit: decision is preserved locally for controlled retry.",
                priority="high",
            )
        return True

    if normalized == "SET_ALLOCATION":
        normalized_target = engine._normalize_platform(target or "ALL")
        gate.require("OBSIDIAN", Capability.VENUE_CONTROL, f"set_allocation({value})")
        allocation = max(0.0, min(1.0, float(value)))
        targets = (
            list(dispatcher.bot_urls.keys())
            if normalized_target == "ALL"
            else [engine._normalize_platform(normalized_target)]
        )
        unknown = [venue for venue in targets if venue not in dispatcher.bot_urls]
        if unknown:
            await engine.telegram.send_message(
                f"❌ Unknown venue(s): `{', '.join(unknown)}`", priority="high"
            )
            return True
        for venue in targets:
            dispatcher.set_venue_allocation(venue, allocation)
            if allocation <= 0:
                dispatcher.pause_venue(
                    venue,
                    reason="Manual deallocation via Telegram",
                    cooldown_seconds=max(engine._deallocation_cooldown_seconds, 3600),
                )
            else:
                dispatcher.resume_venue(venue)
                engine._failure_counts[venue] = 0
                engine._auto_deallocated.discard(venue)
                engine._manual_review_venues.discard(venue)
        if allocation <= 0:
            engine._record_system_log(
                f"Manual deallocation applied to {', '.join(targets)}",
                level="warning",
                tags=["control", "allocation"],
                metadata={"allocation": allocation},
            )
            await engine._publish_risk_alert(
                action="halt_trading",
                severity="warning",
                alert_type="manual_deallocation",
                message=f"Manual deallocation: {', '.join(targets)} set to 0%",
                platforms=targets,
                metadata={"source": "telegram", "allocation": allocation},
            )
            await engine.telegram.send_message(
                f"🧯 Deallocated `{', '.join(targets)}` to `0%` and halted trading on those venues.",
                priority="high",
            )
        else:
            engine._record_system_log(
                f"Manual allocation set for {', '.join(targets)} to {allocation*100:.0f}%",
                level="info",
                tags=["control", "allocation"],
                metadata={"allocation": allocation},
            )
            await engine._publish_risk_alert(
                action="resume_trading",
                severity="warning",
                alert_type="manual_allocation",
                message=f"Manual allocation update: {', '.join(targets)} set to {allocation*100:.0f}%",
                platforms=targets,
                metadata={"source": "telegram", "allocation": allocation},
            )
            await engine.telegram.send_message(
                f"✅ Allocation for `{', '.join(targets)}` set to `{allocation*100:.0f}%`.",
                priority="high",
            )
        return True

    return False


# ── Core Control (kill switch, status, portfolio, etc.) ───────────────


async def handle_core_control_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle core control commands: kill switch, status, portfolio, memory, focus, promotion, autonomy, owner chat."""
    normalized = action.upper()

    if normalized in {"KILL", "HALT", "HALT_TRADING"}:
        await engine._activate_kill_switch("Manual command from Telegram")
        return True

    if normalized in {"RESUME", "RESUME_TRADING"}:
        await engine._resume_from_kill_switch("Manual command from Telegram")
        return True

    if normalized in {"HEARTBEAT", "PING"}:
        await engine._send_heartbeat("manual")
        return True

    if normalized in {"STATUS", "CONTROL_STATUS"}:
        await engine._send_control_status()
        return True

    if normalized in {"MARKET_PRICES", "PRICES"}:
        await engine._send_market_prices()
        return True

    if normalized in {"PORTFOLIO", "POSITIONS"}:
        await engine._send_portfolio_status()
        return True

    if normalized in {"MEMORY_STATUS", "COGNITION_STATUS"}:
        await engine._send_cognitive_status()
        return True

    if normalized in {"FOCUS", "CONTROL_FOCUS"}:
        await engine._send_focus_snapshot()
        return True

    if normalized in {"PROMOTION_GATE", "STRATEGY_GATE", "PROMOTION", "GATE"}:
        requested_stage = engine._parse_execution_stage_token(target)
        if requested_stage:
            applied = engine._set_execution_stage(requested_stage, source="promotion_gate")
            await engine.telegram.send_message(
                (
                    f"🚀 Promotion stage updated to `{applied.get('dex_execution_stage', requested_stage)}`.\n"
                    f"Live dispatch: `{'ON' if applied.get('stage_multiplier', 0) > 0 else 'OFF'}` | "
                    f"Effective qty: `{applied.get('effective_quantity', 0.0)}`"
                ),
                priority="high",
            )
            await engine._send_promotion_gate_report(
                f"promotion:{applied.get('dex_execution_stage', requested_stage)}"
            )
        else:
            await engine._send_promotion_gate_report("manual")
        return True

    if normalized in {"AUTONOMY", "AUTONOMY_CYCLE"}:
        await engine._dispatch_full_autonomy_cycle(trigger="manual_telegram", force=True)
        return True

    if normalized == "OWNER_CHAT":
        message = str(target or "").strip()
        if not message:
            return True
        strategy_state = engine.strategy.execution_state()
        ctrl = engine._control_snapshot()
        context_lines = [
            f"Execution stage: {strategy_state.get('dex_execution_stage', 'paper')}",
            f"Stage multiplier: {strategy_state.get('stage_multiplier', 0)}",
            f"Kill switch: {'ACTIVE' if ctrl.get('kill_switch_active') else 'inactive'}",
            f"Preferred symbols: {', '.join(strategy_state.get('preferred_symbols', [])[:5])}",
        ]
        for venue, info in ctrl.get("venues", {}).items():
            status = "PAUSED" if info.get("paused") else "LIVE"
            context_lines.append(
                f"Venue {venue}: {status}, allocation {info.get('allocation', 1.0)*100:.0f}%"
            )
        port_snap = engine.portfolio.snapshot()
        if port_snap["open_count"] > 0 or port_snap["total_trades"] > 0:
            context_lines.append(
                f"Portfolio: {port_snap['open_count']} open positions, {port_snap['total_trades']} total fills"
            )
            context_lines.append(
                f"Realized PnL: {port_snap['total_realized_pnl']:+.4f}, "
                f"Unrealized PnL: {port_snap['total_unrealized_pnl']:+.4f}"
            )
            if port_snap["wins"] + port_snap["losses"] > 0:
                context_lines.append(
                    f"Win rate: {port_snap['win_rate']}% ({port_snap['wins']}W / {port_snap['losses']}L)"
                )
        if engine._memory_enabled:
            try:
                mem_stats = engine.memory.get_stats()
                if mem_stats.get("total_episodes", 0) > 0:
                    context_lines.append(
                        f"Memory: {mem_stats['total_episodes']} episodes, {mem_stats['total_trades']} trades recorded"
                    )
                temporal = engine.memory.get_temporal_insights()
                if temporal.get("best_hours"):
                    context_lines.append(f"Best trading hours: {temporal['best_hours'][:3]}")
            except Exception:
                pass
        if engine._cognition_enabled:
            try:
                cog_metrics = engine.cognition.get_metrics()
                if cog_metrics.get("system1_calls", 0) > 0:
                    context_lines.append(
                        f"Cognition: {cog_metrics['system1_calls']} decisions, "
                        f"{cog_metrics.get('overrides', 0)} overrides ({cog_metrics.get('override_rate', 0):.0f}%)"
                    )
            except Exception:
                pass
        system_context = "\n".join(context_lines)
        agent = engine.telegram._route_agent(message)
        gate.require(agent, Capability.AI_PROMPT, "chat_with_owner")
        reply = await engine.ai.chat_with_owner(message, system_context=system_context)
        if reply:
            await engine.telegram.send_as(agent, reply)
        else:
            engine._owner_directive = message[:500]
            engine._owner_directive_updated_at = int(time.time())
            await engine.telegram.send_as(agent, "Noted — I'll factor that into our next cycle.")
        lowered = message.lower()
        if any(
            kw in lowered
            for kw in (
                "focus",
                "prioritize",
                "try",
                "make sure",
                "please",
                "want",
                "should",
                "need",
                "let's",
                "stop",
                "start",
                "switch",
            )
        ):
            engine._owner_directive = message[:500]
            engine._owner_directive_updated_at = int(time.time())
        return True

    if normalized in {"DEAD_LETTER", "DLQ", "DEAD_LETTERS", "UNCONFIRMED"}:
        msg = dispatcher.dead_letters.format_telegram_status()
        await engine.telegram.send_message(msg, priority="medium")
        return True

    if normalized in {"RATE_LIMIT", "RATE_LIMITS", "DISPATCH_RATES", "VENUE_RATES"}:
        status = dispatcher.rate_limiter.get_status()
        if not status:
            await engine.telegram.send_message(
                "📊 **Venue Rate Limits**\n\nNo dispatch activity yet.", priority="medium"
            )
            return True
        lines = ["📊 **Venue Rate Limits**\n"]
        for venue, info in status.items():
            lines.append(
                f"• {venue}: {info['requests_last_60s']}/{info['limit_per_minute']} "
                f"(headroom: {info['headroom']})"
            )
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized in {"DISPATCH_STATUS", "DISPATCHER_STATUS", "DISPATCH_HEALTH"}:
        hardening = dispatcher.get_hardening_status()
        rl = hardening["rate_limiter"]
        dl = hardening["dead_letters"]
        lines = [
            "🔧 **Dispatcher Health**\n",
            f"Pending confirmations: {hardening['pending_confirmations']}",
            f"Dead letters: {dl['unreconciled']} unreconciled / {dl['total']} total",
        ]
        if rl:
            for venue, info in rl.items():
                lines.append(
                    f"Rate [{venue}]: {info['requests_last_60s']}/{info['limit_per_minute']}"
                )
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized in {"OWNER_STEER", "STEER"}:
        directive = str(target or "").strip()
        if not directive:
            await engine.telegram.send_message(
                "❌ Owner steering directive is empty. Use `/steer <directive>` or `/answer <response>`.",
                priority="high",
            )
            return True
        if len(directive) > 500:
            directive = directive[:500]
        engine._owner_directive = directive
        engine._owner_directive_updated_at = int(time.time())
        agent = (
            EMERALD
            if any(w in directive.lower() for w in ("strategy", "optimize", "improve", "review"))
            else SAPPHIRE
        )
        await engine.telegram.send_as(agent, f"Got it — steering updated: *{directive[:100]}*")
        hook_result = (
            await engine.tv_autonomy.dispatch_owner_instruction(directive)
            if engine.tv_autonomy
            else {"dispatched": False}
        )
        if hook_result.get("dispatched"):
            await engine.telegram.send_message(
                f"Dispatched to OpenClaw agents (`{hook_result.get('session_key', 'n/a')}`).",
                priority="medium",
            )
        else:
            await engine.telegram.send_as(
                OBSIDIAN,
                f"OpenClaw dispatch unavailable ({hook_result.get('reason', 'unknown')}). Directive saved for next cycle.",
            )
        return True

    return False


# ── Prediction Market Intelligence ────────────────────────────────────


async def handle_prediction_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle /predictions and /prediction commands (Phase 8)."""
    if getattr(engine, "prediction_aggregator", None) is None:
        return False
    normalized = action.upper()

    if normalized in {"PREDICTIONS", "PREDICTION_STATUS", "PM_STATUS"}:
        msg = engine.prediction_aggregator.format_telegram_status()
        await engine.telegram.send_message(msg, priority="medium")
        return True

    if normalized in {"PREDICTION", "PM_SIGNAL", "PM_SIGNALS"}:
        symbol = str(target or "").strip().upper() or None
        msg = engine.prediction_aggregator.format_telegram_signals(symbol=symbol)
        await engine.telegram.send_message(msg, priority="medium")
        return True

    if normalized in {"PREDICTION_SENTIMENT", "PM_SENTIMENT"}:
        symbol = str(target or "").strip().upper() or "BTC"
        sent = engine.prediction_aggregator.get_symbol_sentiment(symbol)
        lines = [
            f"🔮 **{symbol} Prediction Sentiment**\n",
            f"Consensus: {sent['sentiment']}",
            f"Weighted probability: {sent['weighted_probability']:.1%}",
            f"Confidence: {sent['confidence']:.2f}",
            f"Signal count: {sent['signal_count']}",
            f"Total volume: ${sent['total_volume_usd']:,.0f}",
            f"Sources: {', '.join(sent['sources']) or 'none'}",
        ]
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    if normalized in {"PREDICTION_ARB", "PM_ARB", "PM_ARBITRAGE", "ARBITRAGE"}:
        msg = engine.prediction_aggregator.format_telegram_arbitrage()
        await engine.telegram.send_message(msg, priority="high")
        return True

    if normalized in {"PREDICTION_ACCURACY", "PM_ACCURACY"}:
        msg = engine.prediction_aggregator.format_telegram_accuracy()
        await engine.telegram.send_message(msg, priority="medium")
        return True

    if normalized in {"PM_WHALE", "PM_WHALES", "PREDICTION_WHALE", "PM_MANIPULATION"}:
        msg = engine.prediction_aggregator.format_telegram_whale_alerts()
        await engine.telegram.send_message(msg, priority="high")
        return True

    if normalized in {"PREDICTION_HIGH", "PM_HIGH", "PM_CONVICTION"}:
        signals = engine.prediction_aggregator.get_high_conviction_signals()
        if not signals:
            await engine.telegram.send_message(
                "🔮 No high-conviction prediction signals at this time.", priority="medium"
            )
            return True
        lines = [f"🔮 **High-Conviction Prediction Signals** ({len(signals)})\n"]
        for sig in signals[:8]:
            lines.append(
                f"• [{sig.source.value}] {sig.question[:55]}\n"
                f"  {sig.probability:.1%} | ${sig.volume_usd:,.0f} vol | {sig.sentiment}"
            )
        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    return False


# ── Proposal & Operations Commands ─────────────────────────────────────


async def handle_proposal_commands(
    engine: AlphaEngine, target: str, action: str, value: float
) -> bool:
    """Handle proposal, health, roadmap, and CI commands.

    Commands:
      /proposals        — list pending proposals
      /diff <key>       — show compact diff for a proposal
      /approve_proposal — approve a pending proposal
      /reject_proposal  — reject a pending proposal
      /health           — run health diagnostics
      /roadmap_sync     — sync roadmap items to tasks
      /ci_status        — show CI feedback processor status
      /openclaw_status  — show OpenClaw dispatcher status
      /openclaw_smoke   — ping all 3 agents and report results
      /agent_status     — show per-agent dispatch stats and rotation
    """
    normalized = action.upper()

    # ── /proposals ─────────────────────────────────────────────
    if normalized in {"PROPOSALS", "PENDING_PROPOSALS", "LIST_PROPOSALS"}:
        pending = engine._pending_proposals()
        if not pending:
            await engine.telegram.send_message("✅ No pending proposals.", priority="medium")
            return True
        lines = [f"📋 **Pending Proposals** ({len(pending)})\n"]
        for p in pending[:10]:
            risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(
                p.get("risk_tier", "medium"), "🟡"
            )
            lines.append(
                f"{risk_emoji} `{p['proposal_key']}` — {p['description'][:80]}\n"
                f"  Agent: {p['agent_id']} | Capability: {p['capability']}\n"
                f"  `/approve_proposal {p['proposal_key']}` | `/reject_proposal {p['proposal_key']}`"
            )
        await engine.telegram.send_message("\n".join(lines), priority="high")
        return True

    # ── /diff <key> ────────────────────────────────────────────
    if normalized in {"DIFF", "SHOW_DIFF", "PROPOSAL_DIFF"}:
        key = str(target or "").strip()
        if not key:
            await engine.telegram.send_message("Usage: `/diff <proposal_key>`", priority="high")
            return True
        proposal = engine._proposals.get(key)
        if not proposal:
            await engine.telegram.send_message(f"❌ Proposal `{key}` not found.", priority="high")
            return True
        diff_text = proposal.get("diff", "")
        if not diff_text:
            await engine.telegram.send_message(
                f"📄 Proposal `{key}`: {proposal['description']}\n\nNo diff attached.",
                priority="medium",
            )
            return True
        # Compact diff — truncate for Telegram readability
        diff_lines = diff_text.splitlines()
        for line in diff_lines:
            if line.startswith("diff --git") or line.startswith("--- ") or line.startswith("+++ "):
                continue
            if line.startswith("@@"):
                continue
        # Show first 30 lines of diff
        preview = "\n".join(diff_lines[:30])
        if len(diff_lines) > 30:
            preview += f"\n... ({len(diff_lines) - 30} more lines)"
        await engine.telegram.send_message(
            f"📄 Diff for `{key}`:\n```\n{preview}\n```",
            priority="high",
        )
        return True

    # ── /approve_proposal ──────────────────────────────────────
    if normalized in {"APPROVE_PROPOSAL", "APPROVE_CODE"}:
        key = str(target or "").strip()
        if not key:
            await engine.telegram.send_message(
                "Usage: `/approve_proposal <proposal_key>`", priority="high"
            )
            return True
        result = engine._apply_proposal_decision(key, "APPROVE", note="Approved via Telegram")
        if result.get("ok"):
            await engine.telegram.send_as(
                OBSIDIAN,
                f"✅ Proposal `{key}` **approved**.",
            )
        else:
            await engine.telegram.send_message(
                f"❌ Could not approve: `{result.get('reason', 'unknown')}`",
                priority="high",
            )
        return True

    # ── /reject_proposal ───────────────────────────────────────
    if normalized in {"REJECT_PROPOSAL", "REJECT_CODE"}:
        key = str(target or "").strip()
        if not key:
            await engine.telegram.send_message(
                "Usage: `/reject_proposal <proposal_key>`", priority="high"
            )
            return True
        result = engine._apply_proposal_decision(key, "REJECT", note="Rejected via Telegram")
        if result.get("ok"):
            await engine.telegram.send_as(
                OBSIDIAN,
                f"🚫 Proposal `{key}` **rejected**.",
            )
        else:
            await engine.telegram.send_message(
                f"❌ Could not reject: `{result.get('reason', 'unknown')}`",
                priority="high",
            )
        return True

    # ── /health ────────────────────────────────────────────────
    if normalized in {"HEALTH", "HEALTH_CHECK", "DIAGNOSTICS", "SYSTEM_HEALTH"}:
        diagnostics = await engine._run_health_diagnostics()
        issues = diagnostics.get("issues", [])
        if not issues:
            await engine.telegram.send_message(
                "✅ All health checks passed. No issues detected.", priority="medium"
            )
            return True
        lines = [f"⚠️ **Health Issues** ({len(issues)})\n"]
        severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        for issue in issues:
            emoji = severity_emoji.get(issue.get("severity", "medium"), "🟡")
            lines.append(
                f"{emoji} `{issue['type']}` — severity: {issue.get('severity', '?')}\n"
                f"  Agent: {issue.get('agent', '?')}"
            )
            if "venue" in issue:
                lines[-1] += f" | Venue: {issue['venue']}"
            if "pressure" in issue:
                lines[-1] += f" | Pressure: {issue['pressure']}/{issue.get('threshold', '?')}"
        await engine.telegram.send_message("\n".join(lines), priority="high")
        return True

    # ── /roadmap_sync ──────────────────────────────────────────
    if normalized in {"ROADMAP_SYNC", "SYNC_ROADMAP", "ROADMAP"}:
        try:
            from src.collaboration.task_manager import RoadmapParser

            parser = RoadmapParser()
            result = parser.generate_tasks(engine.tasks)
            await engine.telegram.send_message(
                (
                    f"📋 Roadmap sync complete.\n"
                    f"Items found: `{result.get('items_found', 0)}`\n"
                    f"Tasks created: `{result.get('created', 0)}`\n"
                    f"Skipped (duplicates): `{result.get('skipped', 0)}`"
                ),
                priority="high",
            )
        except Exception as exc:
            await engine.telegram.send_message(
                f"❌ Roadmap sync failed: `{str(exc)[:200]}`", priority="high"
            )
        return True

    # ── /ci_status ─────────────────────────────────────────────
    if normalized in {"CI_STATUS", "CI", "BUILD_STATUS"}:
        if hasattr(engine, "ci_feedback") and engine.ci_feedback:
            await engine.telegram.send_message(
                "✅ CI Feedback Processor is active.\n"
                "Test failures → EMERALD tasks\n"
                "Build failures → OBSIDIAN tasks",
                priority="medium",
            )
        else:
            await engine.telegram.send_message(
                "⚠️ CI Feedback Processor not initialized.", priority="medium"
            )
        return True

    # ── /openclaw_status ───────────────────────────────────────
    if normalized in {"OPENCLAW_STATUS", "OPENCLAW", "GATEWAY_STATUS"}:
        if hasattr(engine, "openclaw_dispatcher"):
            status = engine.openclaw_dispatcher.status()
            lines = [
                "🤖 **OpenClaw Gateway Status**\n",
                f"Enabled: `{status['enabled']}`",
                f"URL: `{status['gateway_url']}`",
                f"Token: `{'configured' if status['token_configured'] else 'MISSING'}`",
                f"Dispatches: `{status['dispatch_count']}`",
            ]
            if status["last_error"]:
                lines.append(f"Last error: `{status['last_error'][:100]}`")
            lines.append(f"Repos: `{', '.join(status['allowed_repo_scope'])}`")
            await engine.telegram.send_message("\n".join(lines), priority="medium")
        else:
            await engine.telegram.send_message(
                "⚠️ OpenClaw dispatcher not initialized.", priority="medium"
            )
        return True

    # ── /openclaw_smoke ───────────────────────────────────────
    if normalized in {"OPENCLAW_SMOKE", "SMOKE_TEST", "AGENT_PING", "PING_AGENTS"}:
        if not hasattr(engine, "openclaw_dispatcher"):
            await engine.telegram.send_message(
                "⚠️ OpenClaw dispatcher not initialized.", priority="medium"
            )
            return True

        d = engine.openclaw_dispatcher
        if not d.enabled:
            await engine.telegram.send_message(
                "⚠️ OpenClaw dispatcher disabled (token not configured).", priority="medium"
            )
            return True

        agents = ["OBSIDIAN", "EMERALD", "SAPPHIRE"]
        lines = ["🔬 **OpenClaw Smoke Test**\n"]
        for agent in agents:
            try:
                result = await d.dispatch_instruction(
                    agent_id=agent,
                    instruction="Health check ping — respond with agent identity.",
                    trigger="smoke_test",
                )
                if result.get("dispatched"):
                    lines.append(
                        f"✅ {agent}: dispatched (session `{result.get('session_key', '?')[:8]}…`)"
                    )
                else:
                    reason = result.get("reason", "unknown")
                    error = result.get("error", "")[:80]
                    lines.append(f"❌ {agent}: {reason}" + (f" — {error}" if error else ""))
            except Exception as exc:
                lines.append(f"💥 {agent}: exception — {str(exc)[:80]}")

        lines.append(f"\nGateway: `{d.gateway_url}`")
        await engine.telegram.send_message("\n".join(lines), priority="high")
        return True

    # ── /agent_status ─────────────────────────────────────────
    if normalized in {"AGENT_STATUS", "AGENTS", "AGENT_STATS", "DISPATCH_STATS"}:
        import time as _time

        dispatch_count = getattr(engine, "_autonomy_dispatch_count", 0)
        history = getattr(engine, "_agent_dispatch_history", {})
        agent_emojis = {"OBSIDIAN": "🖤", "EMERALD": "💚", "SAPPHIRE": "💎"}
        lines = [
            "🤖 **Multi-Agent Dispatch Status**\n",
            f"Total dispatches: `{dispatch_count}`",
            f"Rotation cycle: `{dispatch_count % 3}` (0=OBSIDIAN, 1=EMERALD, 2=SAPPHIRE)\n",
        ]
        for agent_id in ["OBSIDIAN", "EMERALD", "SAPPHIRE"]:
            emoji = agent_emojis.get(agent_id, "")
            agent_history = history.get(agent_id, [])
            count = len(agent_history)
            if agent_history:
                last = agent_history[-1]
                last_trigger = last.get("trigger", "?")
                last_ts = last.get("ts", 0)
                ago = int(_time.time() - last_ts)
                if ago < 60:
                    ago_text = f"{ago}s ago"
                elif ago < 3600:
                    ago_text = f"{ago // 60}m ago"
                else:
                    ago_text = f"{ago // 3600}h ago"
                lines.append(
                    f"{emoji} **{agent_id}**: `{count}` dispatches | last: `{last_trigger}` ({ago_text})"
                )
            else:
                lines.append(f"{emoji} **{agent_id}**: `{count}` dispatches | last: never")

        if hasattr(engine, "openclaw_dispatcher"):
            status = engine.openclaw_dispatcher.status()
            lines.append(f"\nGateway: `{status['gateway_url']}`")
            lines.append(
                f"Enabled: `{status['enabled']}` | Token: `{'✅' if status['token_configured'] else '❌'}`"
            )

        await engine.telegram.send_message("\n".join(lines), priority="medium")
        return True

    return False


# ── Master Dispatch Table ─────────────────────────────────────────────

# Ordered list of handler functions. Each is tried in order;
# first one returning True wins.
CONTROL_HANDLER_CHAIN = [
    handle_proposal_commands,
    handle_media_commands,
    handle_security_commands,
    handle_forum_commands,
    handle_reputation_commands,
    handle_swarm_commands,
    handle_learning_commands,
    handle_task_commands,
    handle_scout_commands,
    handle_prediction_commands,
    handle_execution_commands,
    handle_core_control_commands,
]


async def dispatch_control_command(
    engine: AlphaEngine, target: str, action: str, value: float
) -> None:
    """
    Master dispatcher for all control commands.
    Replaces AlphaEngine._handle_control_command.

    Each handler is wrapped in try/except so a failure in one sub-service
    (e.g. forum offline) does not crash the entire command router.
    """
    for handler in CONTROL_HANDLER_CHAIN:
        try:
            if await handler(engine, target, action, value):
                return
        except AttributeError as exc:
            # Sub-service not initialised (e.g. engine.forum is None)
            svc = getattr(handler, "__name__", str(handler))
            logger.warning(f"Handler {svc} skipped — sub-service unavailable: {exc}")
            continue
        except Exception as exc:
            svc = getattr(handler, "__name__", str(handler))
            logger.error(f"Handler {svc} raised {type(exc).__name__}: {exc}")
            try:
                await engine.telegram.send_message(
                    f"⚠️ Command `{action.upper()}` failed in *{svc}*: {exc}",
                    priority="high",
                )
            except Exception:
                pass  # Don't let error-reporting itself crash the dispatcher
            return

    # Fallback: unknown action
    await engine.telegram.send_message(
        f"❌ Unknown control action `{action.upper()}`", priority="high"
    )
