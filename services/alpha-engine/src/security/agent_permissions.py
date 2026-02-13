"""Agent capability-based permission system.

Each agent persona (Sapphire, Obsidian, Emerald, Scout) is assigned a set of
capabilities that control what operations they may perform.  The ``AgentGate``
enforcer is a thin runtime guard — call ``gate.require(agent_id, capability)``
before executing a privileged operation.  It raises ``PermissionDenied`` if the
agent lacks the required capability.

Scout is intentionally the most restricted agent: it has NO access to secrets,
credentials, execution, portfolio, or direct system control.  It communicates
exclusively through the Forum.

Design goals:
- Minimal overhead — dict lookups, no database
- Fail-closed — unknown agents have zero capabilities
- Auditable — every permission check is logged
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, FrozenSet, List, Optional, Set


class Capability(Enum):
    """Atomic permissions that an agent can hold."""

    # ── Execution ──
    TRADE_EXECUTE = auto()       # Send trade commands to venues
    TRADE_READ = auto()          # Read trade history and fill data
    PORTFOLIO_READ = auto()      # Read open positions and P&L
    PORTFOLIO_WRITE = auto()     # Modify portfolio (close positions, reset)
    VENUE_CONTROL = auto()       # Pause/resume/allocate venues
    KILL_SWITCH = auto()         # Activate emergency halt

    # ── Intelligence ──
    COGNITION_READ = auto()      # Read cognition state and metrics
    COGNITION_WRITE = auto()     # Trigger cognition evaluations
    MEMORY_READ = auto()         # Read episodic memory
    MEMORY_WRITE = auto()        # Record to episodic memory
    MARKET_DATA_READ = auto()    # Read live market prices

    # ── Forum / Communication ──
    FORUM_READ = auto()          # Read forum posts and topics
    FORUM_WRITE = auto()         # Create forum posts and comments
    FORUM_MODERATE = auto()      # Delete/edit any forum content

    # ── External ──
    EXTERNAL_API_CALL = auto()   # Make HTTP calls to external services
    MOLTBOOK_READ = auto()       # Read from Moltbook/Molthub
    MOLTBOOK_WRITE = auto()      # Post to Moltbook/Molthub

    # ── System ──
    SECRET_ACCESS = auto()       # Access env vars containing secrets
    SYSTEM_CONFIG = auto()       # Modify runtime configuration
    AUTONOMY_DISPATCH = auto()   # Dispatch autonomy cycles
    TELEGRAM_SEND = auto()       # Send messages to Telegram
    SKILL_AUDIT = auto()         # Run security audits on skills
    AI_PROMPT = auto()           # Send prompts to LLM (Gemini)

    # ── Media ──
    MEDIA_PUBLISH = auto()       # Publish media content


# ── Agent Role Definitions ──────────────────────────────────────────

# Sapphire 💎: Trading & execution ops — full access to execution and market
SAPPHIRE_CAPABILITIES: FrozenSet[Capability] = frozenset({
    Capability.TRADE_EXECUTE,
    Capability.TRADE_READ,
    Capability.PORTFOLIO_READ,
    Capability.PORTFOLIO_WRITE,
    Capability.VENUE_CONTROL,
    Capability.KILL_SWITCH,
    Capability.COGNITION_READ,
    Capability.COGNITION_WRITE,
    Capability.MEMORY_READ,
    Capability.MEMORY_WRITE,
    Capability.MARKET_DATA_READ,
    Capability.FORUM_READ,
    Capability.FORUM_WRITE,
    Capability.SECRET_ACCESS,
    Capability.SYSTEM_CONFIG,
    Capability.TELEGRAM_SEND,
    Capability.AI_PROMPT,
    Capability.MEDIA_PUBLISH,
})

# Obsidian 🖤: Infrastructure & deployments — system control, no direct trading
OBSIDIAN_CAPABILITIES: FrozenSet[Capability] = frozenset({
    Capability.TRADE_READ,
    Capability.PORTFOLIO_READ,
    Capability.VENUE_CONTROL,
    Capability.KILL_SWITCH,
    Capability.COGNITION_READ,
    Capability.MEMORY_READ,
    Capability.MARKET_DATA_READ,
    Capability.FORUM_READ,
    Capability.FORUM_WRITE,
    Capability.SECRET_ACCESS,
    Capability.SYSTEM_CONFIG,
    Capability.AUTONOMY_DISPATCH,
    Capability.TELEGRAM_SEND,
    Capability.AI_PROMPT,
})

# Emerald 💚: Strategy & improvement — cognition, memory, auditing, no secrets
EMERALD_CAPABILITIES: FrozenSet[Capability] = frozenset({
    Capability.TRADE_READ,
    Capability.PORTFOLIO_READ,
    Capability.COGNITION_READ,
    Capability.COGNITION_WRITE,
    Capability.MEMORY_READ,
    Capability.MEMORY_WRITE,
    Capability.MARKET_DATA_READ,
    Capability.FORUM_READ,
    Capability.FORUM_WRITE,
    Capability.FORUM_MODERATE,
    Capability.SKILL_AUDIT,
    Capability.TELEGRAM_SEND,
    Capability.AI_PROMPT,
})

# Scout 🔍: External-facing — MOST RESTRICTED, Forum-only communication
SCOUT_CAPABILITIES: FrozenSet[Capability] = frozenset({
    Capability.FORUM_READ,
    Capability.FORUM_WRITE,
    Capability.MOLTBOOK_READ,
    Capability.MOLTBOOK_WRITE,
    Capability.EXTERNAL_API_CALL,
    Capability.SKILL_AUDIT,
    # Scout explicitly CANNOT: access secrets, execute trades, read portfolio,
    # control venues, send Telegram messages, access AI prompts, or modify system config.
})

# Mapping from agent ID to capabilities
AGENT_CAPABILITY_MAP: Dict[str, FrozenSet[Capability]] = {
    "SAPPHIRE": SAPPHIRE_CAPABILITIES,
    "OBSIDIAN": OBSIDIAN_CAPABILITIES,
    "EMERALD": EMERALD_CAPABILITIES,
    "SCOUT": SCOUT_CAPABILITIES,
}


class PermissionDenied(Exception):
    """Raised when an agent attempts an operation it lacks capability for."""

    def __init__(self, agent_id: str, capability: Capability, detail: str = ""):
        self.agent_id = agent_id
        self.capability = capability
        self.detail = detail
        msg = f"Agent '{agent_id}' lacks capability {capability.name}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


@dataclass
class PermissionCheckRecord:
    """Audit log entry for a permission check."""
    agent_id: str
    capability: str
    granted: bool
    timestamp: float
    detail: str = ""


class AgentGate:
    """Runtime permission enforcer for agent operations.

    Usage::

        gate = AgentGate()
        gate.require("SCOUT", Capability.TRADE_EXECUTE)  # raises PermissionDenied
        gate.require("SAPPHIRE", Capability.TRADE_EXECUTE)  # passes silently

    Call ``check()`` for a non-raising boolean test.
    """

    def __init__(self, max_audit_log: int = 500):
        self._capabilities = dict(AGENT_CAPABILITY_MAP)
        self._audit_log: List[PermissionCheckRecord] = []
        self._max_audit_log = max(50, max_audit_log)
        self._denied_count: Dict[str, int] = {}

    def check(self, agent_id: str, capability: Capability) -> bool:
        """Return True if the agent has the capability, False otherwise."""
        agent_key = str(agent_id or "").strip().upper()
        caps = self._capabilities.get(agent_key, frozenset())
        granted = capability in caps
        self._record(agent_key, capability, granted)
        return granted

    def require(self, agent_id: str, capability: Capability, detail: str = "") -> None:
        """Raise PermissionDenied if the agent lacks the capability."""
        if not self.check(agent_id, capability):
            agent_key = str(agent_id or "").strip().upper()
            key = f"{agent_key}:{capability.name}"
            self._denied_count[key] = self._denied_count.get(key, 0) + 1
            raise PermissionDenied(agent_key, capability, detail)

    def agent_capabilities(self, agent_id: str) -> FrozenSet[Capability]:
        """Return the set of capabilities for an agent."""
        agent_key = str(agent_id or "").strip().upper()
        return self._capabilities.get(agent_key, frozenset())

    def register_agent(self, agent_id: str, capabilities: FrozenSet[Capability]) -> None:
        """Register or override capabilities for an agent."""
        agent_key = str(agent_id or "").strip().upper()
        if not agent_key:
            raise ValueError("agent_id must be non-empty")
        self._capabilities[agent_key] = frozenset(capabilities)

    def stats(self) -> Dict[str, Any]:
        """Return permission check statistics."""
        total = len(self._audit_log)
        granted = sum(1 for r in self._audit_log if r.granted)
        denied = total - granted
        return {
            "total_checks": total,
            "granted": granted,
            "denied": denied,
            "denied_breakdown": dict(self._denied_count),
            "registered_agents": sorted(self._capabilities.keys()),
        }

    def recent_denials(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent denial records."""
        denials = [r for r in self._audit_log if not r.granted]
        return [
            {
                "agent_id": r.agent_id,
                "capability": r.capability,
                "timestamp": r.timestamp,
                "detail": r.detail,
            }
            for r in denials[-limit:]
        ]

    def _record(self, agent_id: str, capability: Capability, granted: bool) -> None:
        self._audit_log.append(
            PermissionCheckRecord(
                agent_id=agent_id,
                capability=capability.name,
                granted=granted,
                timestamp=time.time(),
            )
        )
        if len(self._audit_log) > self._max_audit_log:
            self._audit_log = self._audit_log[-self._max_audit_log:]


# Singleton gate
gate = AgentGate()
