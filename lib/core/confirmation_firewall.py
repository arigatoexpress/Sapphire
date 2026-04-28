"""Human Confirmation Firewall — Vitalik-inspired authorization gate.

All risky actions from agents/bots must pass through this gate before
execution. READ_ONLY and SELF_MODIFY are auto-approved. Everything else
requires explicit Telegram confirmation from the user.

Confirmation flow:
1. Classify the action → ActionRisk level
2. Auto-approve READ_ONLY / SELF_MODIFY
3. For anything riskier: send Telegram message with unique code + expiry
4. Poll ~/.sapphire/pending_confirmations/<code>.json for user reply
5. DESTRUCTIVE: enforce 30-second delay after approval
6. FINANCIAL: enforce daily $100 auto-approve limit for paper/dry-run actions only

Usage:
    fw = ConfirmationFirewall()
    risk = fw.classify_action("launchctl bootout", target="com.sapphire.inference-proxy")
    approved = fw.request_confirmation(
        action="Unload inference-proxy LaunchAgent",
        risk=risk,
        details="This will take the proxy offline immediately",
    )
    if approved:
        subprocess.run(["launchctl", "bootout", ...])
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import time
import uuid
from datetime import date
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

# ─── State Directories ────────────────────────────────────────────────────────

SAPPHIRE_STATE = Path.home() / ".sapphire"
PENDING_DIR = SAPPHIRE_STATE / "pending_confirmations"
LIMITS_FILE = SAPPHIRE_STATE / "financial_limits.json"
AUDIT_LOG = SAPPHIRE_STATE / "audit" / "confirmation_firewall.jsonl"

CONFIRMATION_TIMEOUT = 300  # 5 minutes
DESTRUCTIVE_DELAY = 30  # seconds after approval before executing
DAILY_AUTO_LIMIT = 100.0  # USD — paper/dry-run financial actions below this are auto-approved
DAILY_AUTO_LIMIT_ENV = "SAPPHIRE_FIREWALL_DAILY_AUTO_LIMIT"
AUDIT_LOG_ENV = "SAPPHIRE_CONFIRMATION_FIREWALL_AUDIT_LOG"
LIVE_FINANCIAL_AUTO_APPROVAL_ENV = "SAPPHIRE_FIREWALL_ALLOW_LIVE_FINANCIAL_AUTO_APPROVAL"

# ─── Risk Classification ──────────────────────────────────────────────────────


class ActionRisk(Enum):
    READ_ONLY = "read_only"  # File reads, health checks, log viewing
    SELF_MODIFY = "self_modify"  # Own logs, notes, self-messages
    SYSTEM_MODIFY = "system_modify"  # Service restarts, config writes
    EXTERNAL_SEND = "external_send"  # Messages to others, external API writes
    FINANCIAL = "financial"  # Trades, transfers, swaps
    DESTRUCTIVE = "destructive"  # File deletion, service unload, wipe


# Pattern sets for classify_action heuristics
_READ_PATTERNS = re.compile(
    r"^(read|cat|head|tail|ls|list|view|show|get|fetch|check|health|status|"
    r"ping|query|search|find|grep|curl.*GET|log.*view|model.*list|whoami|"
    r"ps aux|df|du|free|top|htop|lsof|netstat|ifconfig|ip addr)",
    re.IGNORECASE,
)

_SELF_MODIFY_PATTERNS = re.compile(
    r"(write.*log|append.*log|send.*self|send.*aribs|note.*self|"
    r"echo.*>>.*log|tee.*log|memory.*write|journal|diary|bookmark)",
    re.IGNORECASE,
)

_DESTRUCTIVE_PATTERNS = re.compile(
    r"(rm\s+-rf|rm\s+-r|rmdir|mkfs|dd\s+if=|shred|wipe|drop\s+table|"
    r"delete\s+all|truncate|purge|launchctl\s+bootout|launchctl\s+remove|"
    r"pkill|kill\s+-9|systemctl\s+disable|uninstall|factory.?reset)",
    re.IGNORECASE,
)

_FINANCIAL_PATTERNS = re.compile(
    r"(trade|order|buy|sell|swap|transfer|withdraw|deposit|send.*\$|"
    r"payment|invoice|charge|debit|credit|hyperliquid.*open|"
    r"place.*position|close.*position|leverage|margin|"
    r"go\s+long|go\s+short|long\s+position|short\s+position|"
    r"short.?sell|liquidate|margin.?call|position.?size|"
    r"\bpnl\b|profit.?loss|unrealized|stop.?loss|take.?profit)",
    re.IGNORECASE,
)

_EXTERNAL_SEND_PATTERNS = re.compile(
    r"(send.*message|post.*tweet|email|slack.*send|discord.*send|"
    r"curl.*POST|curl.*PUT|curl.*DELETE|webhook.*send|api.*write|"
    r"github.*push|git\s+push|deploy|publish|release)",
    re.IGNORECASE,
)

_SYSTEM_MODIFY_PATTERNS = re.compile(
    r"(restart|launchctl.*kickstart|launchctl.*start|launchctl.*stop|"
    r"launchctl.*bootstrap|systemctl.*start|systemctl.*restart|systemctl.*stop|"
    r"config.*write|config.*set|plist.*edit|env.*set|chmod|chown|"
    r"pip.*install|brew.*install|npm.*install|apt.*install|"
    r"git.*commit|git.*merge|reboot|shutdown|cron.*add|service.*start|service.*stop)",
    re.IGNORECASE,
)


def classify_action(action: str, target: str = "") -> ActionRisk:
    """Classify an action string into an ActionRisk level.

    Checks patterns from most dangerous to least; first match wins.
    Returns READ_ONLY if nothing matches (safe default).
    """
    text = f"{action} {target}"

    if _DESTRUCTIVE_PATTERNS.search(text):
        return ActionRisk.DESTRUCTIVE
    if _FINANCIAL_PATTERNS.search(text):
        return ActionRisk.FINANCIAL
    if _SELF_MODIFY_PATTERNS.search(text):  # before EXTERNAL_SEND (more specific)
        return ActionRisk.SELF_MODIFY
    if _EXTERNAL_SEND_PATTERNS.search(text):
        return ActionRisk.EXTERNAL_SEND
    if _SYSTEM_MODIFY_PATTERNS.search(text):
        return ActionRisk.SYSTEM_MODIFY
    return ActionRisk.READ_ONLY


def _current_daily_auto_limit() -> float:
    """Return the configured daily financial auto-approve limit."""
    raw = os.environ.get(DAILY_AUTO_LIMIT_ENV)
    if raw is None or raw == "":
        return DAILY_AUTO_LIMIT
    try:
        return max(0.0, float(raw))
    except ValueError:
        log.warning(
            "invalid %s=%r; using default %.2f",
            DAILY_AUTO_LIMIT_ENV,
            raw,
            DAILY_AUTO_LIMIT,
        )
        return DAILY_AUTO_LIMIT


_AUDIT_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret|private[_-]?key)\s*[:=]\s*[^,\s]+"),
    re.compile(r"(?i)\b(bearer)\s+[a-z0-9._~+/=-]+"),
)

_PAPER_FINANCIAL_PATTERNS = re.compile(
    r"\b(paper(?:[-_\s]?only)?|dry[-_\s]?run|simulat(?:e|ed|ion)|sandbox|"
    r"backtest|testnet|mock)\b",
    re.IGNORECASE,
)

_CONFIRMATION_REPLY_PATTERN = re.compile(
    r"^\s*/?(confirm|approve|deny|reject|cancel)\s+([a-z0-9]{8})\s*$",
    re.IGNORECASE,
)
_APPROVE_REPLY_WORDS = {"confirm", "approve"}


def _audit_text(value: str, max_len: int = 160) -> str:
    """Return a redacted, bounded preview safe enough for local audit logs."""
    text = str(value or "")
    for pattern in _AUDIT_SECRET_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}=<redacted>", text)
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _details_fingerprint(details: str) -> dict[str, int | str]:
    """Record evidence of details without writing raw details to disk."""
    body = str(details or "")
    return {"details_len": len(body)}


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _is_paper_or_dry_run_financial(action: str, details: str = "") -> bool:
    """Return True only when a financial action explicitly says it is non-live."""
    if _truthy_env(LIVE_FINANCIAL_AUTO_APPROVAL_ENV):
        return True
    return bool(_PAPER_FINANCIAL_PATTERNS.search(f"{action}\n{details}"))


# ─── Financial Limit Tracking ─────────────────────────────────────────────────


def _get_redis():
    """Return a connected Redis client or None if Redis is unavailable.

    Returns None immediately when SAPPHIRE_STATE has been redirected (e.g., in
    tests), so test isolation is preserved without patching Redis itself.
    Also returns None when SAPPHIRE_NO_REDIS=1 is set (explicit test escape hatch).
    """
    import os

    if os.environ.get("SAPPHIRE_NO_REDIS"):
        return None
    if Path.home() / ".sapphire" != SAPPHIRE_STATE:
        return None  # test / non-standard context — use file fallback
    try:
        import redis

        r = redis.Redis(host="127.0.0.1", port=6379, db=0, socket_connect_timeout=1)
        r.ping()
        return r
    except Exception:
        return None


def _load_daily_spend() -> float:
    """Return total USD spent today. Checks Redis first, falls back to file."""
    today = str(date.today())
    # Try Redis first (authoritative when available)
    r = _get_redis()
    if r is not None:
        try:
            val = r.get(f"sapphire:daily_spend:{today}")
            return float(val) if val is not None else 0.0
        except Exception:
            pass
    # File fallback
    if not LIMITS_FILE.exists():
        return 0.0
    try:
        data = json.loads(LIMITS_FILE.read_text())
        if data.get("date") == today:
            return float(data.get("spent", 0.0))
    except (json.JSONDecodeError, KeyError, ValueError):
        pass
    return 0.0


def _record_spend(amount: float) -> None:
    """Add amount to today's spend total.

    Primary: Redis incrbyfloat with a daily TTL (atomic, no lock needed).
    Fallback: flock-protected JSON file (if Redis is unavailable).
    """
    today = str(date.today())
    # Try Redis first
    r = _get_redis()
    if r is not None:
        try:
            key = f"sapphire:daily_spend:{today}"
            r.incrbyfloat(key, amount)
            # Expire 2 days from now so yesterday's key is cleaned up automatically
            from datetime import timedelta

            r.expire(key, int(timedelta(days=2).total_seconds()))
            return
        except Exception:
            pass  # Fall through to file-based backup

    # File-based fallback (flock-protected for multi-process safety)
    import fcntl

    SAPPHIRE_STATE.mkdir(parents=True, exist_ok=True)
    lock_path = LIMITS_FILE.with_suffix(".lock")
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            try:
                data = json.loads(LIMITS_FILE.read_text()) if LIMITS_FILE.exists() else {}
            except (json.JSONDecodeError, OSError):
                data = {}
            if data.get("date") != today:
                data = {"date": today, "spent": 0.0}
            data["spent"] = float(data.get("spent", 0.0)) + amount
            LIMITS_FILE.write_text(json.dumps(data, indent=2))
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def _try_consume_daily_budget(amount: float, limit: float) -> tuple[bool, float]:
    """Atomically reserve `amount` against today's daily spend cap.

    Returns (approved, new_total). When `approved is True`, the amount has
    already been recorded — callers must not call `_record_spend` again.
    When False, no change was committed.

    The prior `_load_daily_spend()` → compare → `_record_spend()` sequence
    was a TOCTOU race: N concurrent callers each saw spent=$0 and each
    committed, busting the cap. This helper increments first, checks the
    post-increment total, and rolls back on overage — making the limit
    a true invariant under concurrency (Redis) or process-level locking
    (file fallback).
    """
    today = str(date.today())
    key = f"sapphire:daily_spend:{today}"

    r = _get_redis()
    if r is not None:
        try:
            new_total = float(r.incrbyfloat(key, amount))
            from datetime import timedelta

            with contextlib.suppress(Exception):
                r.expire(key, int(timedelta(days=2).total_seconds()))
            if new_total > limit:
                try:
                    r.incrbyfloat(key, -amount)
                except Exception:
                    log.warning(
                        "daily-spend rollback failed; recorded $%.2f over cap",
                        new_total - limit,
                    )
                return False, new_total
            return True, new_total
        except Exception:
            pass  # fall through to file lock

    import fcntl

    SAPPHIRE_STATE.mkdir(parents=True, exist_ok=True)
    lock_path = LIMITS_FILE.with_suffix(".lock")
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            try:
                data = json.loads(LIMITS_FILE.read_text()) if LIMITS_FILE.exists() else {}
            except (json.JSONDecodeError, OSError):
                data = {}
            if data.get("date") != today:
                data = {"date": today, "spent": 0.0}
            current = float(data.get("spent", 0.0))
            new_total = current + amount
            if new_total > limit:
                return False, new_total
            data["spent"] = new_total
            LIMITS_FILE.write_text(json.dumps(data, indent=2))
            return True, new_total
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


# ─── Pending Confirmation Store ───────────────────────────────────────────────


def _write_pending(code: str, action: str, risk: ActionRisk, details: str) -> Path:
    """Write a pending confirmation record to disk."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    path = PENDING_DIR / f"{code}.json"
    path.write_text(
        json.dumps(
            {
                "code": code,
                "action": _audit_text(action, max_len=220),
                "risk": risk.value,
                "details": _audit_text(details, max_len=1200),
                "created": time.time(),
                "expires": time.time() + CONFIRMATION_TIMEOUT,
                "status": "pending",  # pending | approved | denied
            },
            indent=2,
        )
    )
    return path


def _poll_pending(code: str) -> str | None:
    """Return status ('approved' or 'denied') or None if still pending/expired."""
    path = PENDING_DIR / f"{code}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        status = data.get("status", "pending")
        if status in ("approved", "denied"):
            path.unlink(missing_ok=True)
            return status
        if time.time() > data.get("expires", 0):
            path.unlink(missing_ok=True)
            return "denied"
    except (json.JSONDecodeError, OSError):
        # Transient read race (partial write from a concurrent approver, or
        # a filesystem hiccup) — do NOT deny the request; return None so the
        # caller keeps polling. A legitimate "denied" will arrive on a
        # later successful read, or via the explicit expiry check above.
        return None
    return None


def _cleanup_expired_pending(now: float | None = None) -> int:
    """Remove expired pending confirmation files and return the count."""
    if not PENDING_DIR.exists():
        return 0
    cutoff = time.time() if now is None else now
    removed = 0
    for path in PENDING_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            expires = float(data.get("expires", 0))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            continue
        if expires and cutoff > expires:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def parse_confirmation_reply(text: str) -> tuple[str, str] | None:
    """Parse a bare confirmation reply like ``CONFIRM ABC123EF``.

    Returns (``"approve"`` | ``"deny"``, code) or None when the text is not
    a confirmation-firewall reply. The parser intentionally accepts only a
    short bare command plus code so normal conversation cannot accidentally
    approve or deny a pending action.
    """
    match = _CONFIRMATION_REPLY_PATTERN.match(str(text or ""))
    if not match:
        return None
    verb = match.group(1).lower()
    action = "approve" if verb in _APPROVE_REPLY_WORDS else "deny"
    return action, match.group(2).upper()


def handle_confirmation_reply(
    text: str,
    *,
    firewall: ConfirmationFirewall | None = None,
) -> dict[str, object] | None:
    """Approve or deny a pending confirmation from a terse user reply.

    The returned payload excludes the original action/details by design; chat
    integrations should echo only the code and status.
    """
    parsed = parse_confirmation_reply(text)
    if parsed is None:
        return None

    action, code = parsed
    fw = firewall or ConfirmationFirewall()
    if action == "approve":
        ok = fw.approve_pending(code)
        status = "approved" if ok else "not_found_or_expired"
    else:
        ok = fw.deny_pending(code)
        status = "denied" if ok else "not_found_or_expired"

    return {
        "matched": True,
        "action": action,
        "code": code,
        "ok": ok,
        "status": status,
    }


def _approve_pending(code: str) -> bool:
    """Mark a pending confirmation as approved (called by hermes-agent handler)."""
    path = PENDING_DIR / f"{code}.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        if data.get("status") != "pending":
            return False
        if time.time() > data.get("expires", 0):
            path.unlink(missing_ok=True)
            return False
        data["status"] = "approved"
        path.write_text(json.dumps(data, indent=2))
        return True
    except (json.JSONDecodeError, OSError):
        return False


def _deny_pending(code: str) -> bool:
    """Mark a pending confirmation as denied."""
    path = PENDING_DIR / f"{code}.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
        if data.get("status") != "pending":
            return False
        if time.time() > data.get("expires", 0):
            path.unlink(missing_ok=True)
            return False
        data["status"] = "denied"
        path.write_text(json.dumps(data, indent=2))
        return True
    except (json.JSONDecodeError, OSError):
        return False


# ─── Telegram Notification ────────────────────────────────────────────────────


def _send_confirmation_request(
    code: str, action: str, risk: ActionRisk, details: str, amount: float = 0.0
) -> bool:
    """Send a Telegram confirmation request. Returns True if sent successfully."""
    import os
    import ssl
    import urllib.error
    import urllib.request

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = (
        os.environ.get("TELEGRAM_CHAT_ID", "")
        or os.environ.get("ALLOWED_TELEGRAM_CHAT_IDS", "").split(",")[0].strip()
    )

    # Try file-based secrets
    if not token:
        for p in [
            Path.home() / ".config" / "sapphire-secrets" / "telegram_bot_token",
            Path.home() / ".config" / "sapphire" / "telegram_bot_token",
        ]:
            if p.exists():
                token = p.read_text().strip()
                break
    if not chat_id:
        for p in [
            Path.home() / ".config" / "sapphire-secrets" / "telegram_chat_id",
            Path.home() / ".config" / "sapphire" / "telegram_chat_id",
        ]:
            if p.exists():
                chat_id = p.read_text().strip()
                break

    if not token or not chat_id:
        log.warning("Confirmation firewall: Telegram not configured — using console fallback")
        print(f"\n{'=' * 60}")
        print(f"⚠ CONFIRMATION REQUIRED [{risk.value.upper()}]")
        print(f"Action:  {action}")
        print(f"Details: {details}")
        if amount > 0:
            print(f"Amount:  ${amount:.2f}")
        print(f"Code:    {code}")
        print(f"Expires: {CONFIRMATION_TIMEOUT}s")
        print("Approve: write 'approved' to pending confirmation file (check logs for path)")
        print(f"{'=' * 60}\n")
        log.info("Pending confirmation file: %s/%s.json", PENDING_DIR, code)
        return False

    risk_emoji = {
        ActionRisk.SYSTEM_MODIFY: "⚙️",
        ActionRisk.EXTERNAL_SEND: "📤",
        ActionRisk.FINANCIAL: "💰",
        ActionRisk.DESTRUCTIVE: "🚨",
    }.get(risk, "⚠️")

    safe_action = _audit_text(action, max_len=220)
    safe_details = _audit_text(details, max_len=1200)
    amount_line = f"\n💵 Amount: ${amount:.2f}" if amount > 0 else ""
    delay_line = (
        "\n⏱ 30-second delay enforced after approval" if risk == ActionRisk.DESTRUCTIVE else ""
    )

    text = (
        f"{risk_emoji} *ACTION REQUIRES CONFIRMATION*\n"
        f"Risk: `{risk.value.upper()}`\n\n"
        f"*Action:* `{safe_action}`\n"
        f"*Details:* {safe_details}"
        f"{amount_line}"
        f"{delay_line}\n\n"
        f"*Confirmation code:*\n`CONFIRM {code}`\n\n"
        f"⏰ Expires in {CONFIRMATION_TIMEOUT // 60} minutes. Reply with the code above to approve."
    )

    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
    ).encode()

    ssl_ctx = ssl.create_default_context()
    try:
        import certifi

        ssl_ctx.load_verify_locations(certifi.where())
    except ImportError:
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as resp:
            return resp.status == 200
    except urllib.error.URLError as e:
        log.error("Telegram send failed: %s", e)
        return False


# ─── Main Firewall Class ──────────────────────────────────────────────────────


class ConfirmationFirewall:
    """Central authorization gate for all risky agent actions.

    Thread-safe. Stateless except for pending confirmation files and
    daily spend tracking (file-backed).
    """

    def __init__(self, audit_path: str | Path | bool | None = None) -> None:
        self._audit_path = self._resolve_audit_path(audit_path)

    def classify_action(self, action: str, target: str = "") -> ActionRisk:
        """Classify action into risk level. Delegates to module-level function."""
        return classify_action(action, target)

    def request_confirmation(
        self,
        action: str,
        risk: ActionRisk,
        details: str = "",
        amount: float = 0.0,
        poll_interval: float = 2.0,
        _send_fn=None,  # Injectable for testing
        _sleep_fn=None,  # Injectable for testing
    ) -> bool:
        """Request confirmation for a risky action.

        Returns True if approved (and any required delay has elapsed).
        Returns False if denied, timed out, or risk=READ_ONLY/SELF_MODIFY auto-rejected
        via this path (they should never reach here in normal use).

        Args:
            action:    Short description of what will be executed
            risk:      ActionRisk level (from classify_action)
            details:   Human-readable detail about consequences
            amount:    USD amount for FINANCIAL actions (0 = unknown)
            poll_interval: Seconds between pending-file polls
        """
        sleep = _sleep_fn or time.sleep

        # ── Auto-approve low-risk actions ──────────────────────────────────────
        if risk in (ActionRisk.READ_ONLY, ActionRisk.SELF_MODIFY):
            log.debug("Firewall auto-approved: %s [%s]", action, risk.value)
            self._append_audit(
                "confirmation.auto_approved",
                action=action,
                risk=risk,
                details=details,
                amount=amount,
                reason="low_risk",
            )
            return True

        # ── Financial: atomically reserve against daily limit ────────────────
        # Prior impl was a TOCTOU race (load→check→record); replace with a
        # single reserve-or-rollback call so concurrent callers cannot each
        # see spent=$0 and all commit past the cap.
        if risk == ActionRisk.FINANCIAL and amount > 0:
            daily_auto_limit = _current_daily_auto_limit()
            auto_allowed = _is_paper_or_dry_run_financial(action, details)
            if not auto_allowed:
                approved, new_total = False, _load_daily_spend() + amount
                denial_reason = "requires_paper_or_dry_run"
            elif daily_auto_limit > 0:
                approved, new_total = _try_consume_daily_budget(amount, daily_auto_limit)
            else:
                approved, new_total = False, _load_daily_spend() + amount
                denial_reason = "daily_auto_limit_disabled"
            if approved:
                log.info(
                    "Firewall financial auto-approved: $%.2f (daily: $%.2f/$%.2f)",
                    amount,
                    new_total,
                    daily_auto_limit,
                )
                self._append_audit(
                    "confirmation.financial_auto_approved",
                    action=action,
                    risk=risk,
                    details=details,
                    amount=amount,
                    reason="daily_auto_limit",
                    daily_total=new_total,
                    daily_limit=daily_auto_limit,
                )
                return True
            if auto_allowed and daily_auto_limit > 0:
                denial_reason = "daily_auto_limit_exceeded"
            log.info(
                "Firewall financial auto-approve unavailable: $%.2f would bring daily to $%.2f "
                "(limit $%.2f)",
                amount,
                new_total,
                daily_auto_limit,
            )
            self._append_audit(
                "confirmation.financial_auto_approval_unavailable",
                action=action,
                risk=risk,
                details=details,
                amount=amount,
                reason=denial_reason,
                daily_total=new_total,
                daily_limit=daily_auto_limit,
            )

        # ── Generate confirmation code ─────────────────────────────────────────
        code = str(uuid.uuid4()).split("-")[0].upper()  # 8-char code
        _write_pending(code, action, risk, details)
        self._append_audit(
            "confirmation.pending_created",
            action=action,
            risk=risk,
            details=details,
            amount=amount,
            code=code,
        )

        # ── Send Telegram notification ─────────────────────────────────────────
        send_fn = _send_fn or _send_confirmation_request
        sent = send_fn(code, action, risk, details, amount)
        if not sent:
            log.warning("Firewall: Telegram send failed — console fallback active")

        log.info("Firewall waiting for confirmation [%s]: %s (code: %s)", risk.value, action, code)

        # ── Poll for response ──────────────────────────────────────────────────
        deadline = time.time() + CONFIRMATION_TIMEOUT
        while time.time() < deadline:
            sleep(poll_interval)
            status = _poll_pending(code)
            if status == "approved":
                log.info("Firewall: confirmed [%s]: %s", risk.value, action)
                if risk == ActionRisk.FINANCIAL and amount > 0:
                    _record_spend(amount)
                if risk == ActionRisk.DESTRUCTIVE:
                    log.info(
                        "Firewall: DESTRUCTIVE action — enforcing %ds delay", DESTRUCTIVE_DELAY
                    )
                    sleep(DESTRUCTIVE_DELAY)
                self._append_audit(
                    "confirmation.approved",
                    action=action,
                    risk=risk,
                    details=details,
                    amount=amount,
                    code=code,
                )
                return True
            if status == "denied":
                log.info("Firewall: denied [%s]: %s", risk.value, action)
                self._append_audit(
                    "confirmation.denied",
                    action=action,
                    risk=risk,
                    details=details,
                    amount=amount,
                    code=code,
                )
                return False

        log.warning(
            "Firewall: timed out after %ds — denying [%s]: %s",
            CONFIRMATION_TIMEOUT,
            risk.value,
            action,
        )
        self._append_audit(
            "confirmation.timed_out",
            action=action,
            risk=risk,
            details=details,
            amount=amount,
            code=code,
        )
        return False

    def auto_approve(self, action: str, target: str = "", details: str = "") -> bool:
        """Convenience: classify + auto-approve safe actions, reject unsafe ones.

        Useful for quick guard calls where you want to bail immediately if
        confirmation is required (rather than blocking to wait).
        Returns True only for READ_ONLY / SELF_MODIFY.
        """
        risk = self.classify_action(action, target)
        if risk in (ActionRisk.READ_ONLY, ActionRisk.SELF_MODIFY):
            return True
        log.warning(
            "Firewall.auto_approve: action requires confirmation [%s]: %s", risk.value, action
        )
        return False

    def approve_pending(self, code: str) -> bool:
        """Approve a pending confirmation (called by hermes-agent message handler)."""
        approved = _approve_pending(code)
        self._append_audit(
            "confirmation.pending_approved",
            code=code,
            status="approved" if approved else "not_found_or_expired",
        )
        return approved

    def deny_pending(self, code: str) -> bool:
        """Deny a pending confirmation."""
        denied = _deny_pending(code)
        self._append_audit(
            "confirmation.pending_denied",
            code=code,
            status="denied" if denied else "not_found_or_expired",
        )
        return denied

    def list_pending(self) -> list[dict]:
        """Return all non-expired pending confirmations."""
        _cleanup_expired_pending()
        if not PENDING_DIR.exists():
            return []
        results = []
        for p in PENDING_DIR.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                if data.get("status") == "pending" and time.time() < data.get("expires", 0):
                    results.append(data)
            except (json.JSONDecodeError, OSError):
                pass
        return sorted(results, key=lambda d: d.get("created", 0))

    def _append_audit(
        self,
        event_type: str,
        *,
        action: str = "",
        risk: ActionRisk | None = None,
        details: str = "",
        amount: float = 0.0,
        **extra: object,
    ) -> None:
        if self._audit_path is None:
            return
        record: dict[str, object] = {
            "event_type": event_type,
            "ts": time.time(),
        }
        if action:
            record["action"] = _audit_text(action)
        if risk is not None:
            record["risk"] = risk.value
        if details:
            record.update(_details_fingerprint(details))
        if amount > 0:
            record["amount"] = amount
        record.update(extra)
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        except Exception as e:
            log.error("confirmation firewall audit append failed: %s", e)

    @staticmethod
    def _resolve_audit_path(audit_path: str | Path | bool | None) -> Path | None:
        if audit_path is False:
            return None
        if audit_path:
            return Path(audit_path).expanduser()
        configured = os.environ.get(AUDIT_LOG_ENV)
        if configured:
            return Path(configured).expanduser()
        return AUDIT_LOG
