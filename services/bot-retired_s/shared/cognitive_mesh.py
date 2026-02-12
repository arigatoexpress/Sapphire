"""
Cognitive Mesh - Natural Language Inter-Agent Protocol

This module enables agents in the Sapphire ACTS system to communicate
using natural language reasoning rather than simple numerical signals.

Key Concepts:
- CognitiveMessage: A structured message containing reasoning, not just data
- CognitiveMesh: The communication fabric connecting all agents
- ConsensusProtocol: Multi-agent agreement before execution
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Emergent roles that agents can specialize into."""

    SCOUT = "scout"  # Market observation, pattern detection
    SNIPER = "sniper"  # Execution timing, entry/exit precision
    ORACLE = "oracle"  # Consensus arbiter, final decision authority
    GUARDIAN = "guardian"  # Risk management, position oversight
    ANALYST = "analyst"  # Deep research, fundamental analysis
    EXECUTOR = "executor"  # Trade execution on specific platform


class MessageType(str, Enum):
    """Types of cognitive messages between agents."""

    OBSERVATION = "observation"  # Raw market observation
    HYPOTHESIS = "hypothesis"  # Trading hypothesis with reasoning
    VALIDATION = "validation"  # Validation of another agent's hypothesis
    DISSENT = "dissent"  # Disagreement with reasoning
    CONSENSUS = "consensus"  # Final agreed decision
    EXECUTION = "execution"  # Trade execution report
    REFLECTION = "reflection"  # Post-trade learning/reflection


@dataclass
class CognitiveMessage:
    """
    A message in the cognitive mesh containing natural language reasoning.

    Unlike traditional signals (e.g., {signal: BUY, confidence: 0.7}),
    cognitive messages contain the full reasoning chain.
    """

    message_id: str
    agent_id: str
    agent_role: AgentRole
    message_type: MessageType

    # The natural language reasoning
    reasoning: str

    # Structured data extracted from the reasoning
    symbol: Optional[str] = None
    suggested_action: Optional[str] = None  # BUY, SELL, HOLD, CLOSE
    confidence: float = 0.0

    # Context for consensus
    references: List[str] = field(default_factory=list)  # IDs of messages being responded to

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for transmission."""
        return {
            "message_id": self.message_id,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role.value,
            "message_type": self.message_type.value,
            "reasoning": self.reasoning,
            "symbol": self.symbol,
            "suggested_action": self.suggested_action,
            "confidence": self.confidence,
            "references": self.references,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveMessage":
        """Deserialize from transmission."""
        return cls(
            message_id=data["message_id"],
            agent_id=data["agent_id"],
            agent_role=AgentRole(data["agent_role"]),
            message_type=MessageType(data["message_type"]),
            reasoning=data["reasoning"],
            symbol=data.get("symbol"),
            suggested_action=data.get("suggested_action"),
            confidence=data.get("confidence", 0.0),
            references=data.get("references", []),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )

    def get_reasoning_hash(self) -> str:
        """Generate a hash of the reasoning for on-chain audit trail."""
        content = f"{self.agent_id}:{self.reasoning}:{self.timestamp.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class ConsensusState:
    """Tracks the state of a multi-agent consensus decision."""

    consensus_id: str
    symbol: str
    initiated_by: str
    initiated_at: datetime

    # Collected votes
    votes: Dict[str, CognitiveMessage] = field(default_factory=dict)

    # Consensus thresholds
    required_agents: int = 2
    required_confidence: float = 0.6

    # Final decision
    decision: Optional[str] = None
    decision_reasoning: Optional[str] = None
    finalized_at: Optional[datetime] = None

    def add_vote(self, message: CognitiveMessage) -> None:
        """Add an agent's vote to the consensus."""
        self.votes[message.agent_id] = message

    def can_finalize(self) -> bool:
        """Check if enough votes have been collected."""
        return len(self.votes) >= self.required_agents

    def compute_consensus(self) -> Dict[str, Any]:
        """Compute the final consensus from collected votes."""
        if not self.can_finalize():
            return {"status": "pending", "votes": len(self.votes)}

        # Aggregate actions and confidences
        actions = {}
        total_confidence = 0.0

        for agent_id, msg in self.votes.items():
            action = msg.suggested_action or "HOLD"
            if action not in actions:
                actions[action] = {"count": 0, "confidence": 0.0, "reasoning": []}
            actions[action]["count"] += 1
            actions[action]["confidence"] += msg.confidence
            actions[action]["reasoning"].append(f"[{msg.agent_role.value}] {msg.reasoning}")
            total_confidence += msg.confidence

        # Find winning action
        winning_action = max(actions.items(), key=lambda x: x[1]["confidence"])
        avg_confidence = winning_action[1]["confidence"] / winning_action[1]["count"]

        if avg_confidence >= self.required_confidence:
            self.decision = winning_action[0]
            self.decision_reasoning = " | ".join(winning_action[1]["reasoning"])
            self.finalized_at = datetime.utcnow()

            return {
                "status": "consensus_reached",
                "action": self.decision,
                "confidence": avg_confidence,
                "reasoning": self.decision_reasoning,
                "votes": len(self.votes),
                "consensus_hash": self.get_consensus_hash(),
            }
        else:
            return {
                "status": "no_consensus",
                "highest_action": winning_action[0],
                "confidence": avg_confidence,
                "required": self.required_confidence,
            }

    def get_consensus_hash(self) -> str:
        """Generate hash for on-chain audit trail."""
        content = json.dumps(
            {
                "consensus_id": self.consensus_id,
                "symbol": self.symbol,
                "decision": self.decision,
                "votes": list(self.votes.keys()),
                "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:32]


class CognitiveMesh:
    """
    The communication fabric for the Autonomous Cognitive Trading Swarm.

    Enables agents to:
    - Broadcast observations and hypotheses
    - Subscribe to specific message types or symbols
    - Participate in consensus decisions
    - Record reasoning trails for explainability
    """

    def __init__(self):
        self.agents: Dict[str, Dict[str, Any]] = {}  # agent_id -> agent info
        self.message_log: List[CognitiveMessage] = []
        self.active_consensus: Dict[str, ConsensusState] = {}  # consensus_id -> state
        self.subscribers: Dict[str, List[Callable]] = {}  # topic -> callbacks
        self._lock = asyncio.Lock()

        # Pub/Sub integration
        self._pubsub_enabled = False

    async def register_agent(
        self, agent_id: str, role: AgentRole, capabilities: List[str] = None
    ) -> None:
        """Register an agent with the mesh."""
        async with self._lock:
            self.agents[agent_id] = {
                "role": role,
                "capabilities": capabilities or [],
                "registered_at": datetime.utcnow(),
                "message_count": 0,
            }
            logger.info(f"🔗 Agent registered: {agent_id} ({role.value})")

    async def broadcast(self, message: CognitiveMessage) -> None:
        """Broadcast a cognitive message to all interested agents."""
        async with self._lock:
            self.message_log.append(message)

            # Update agent stats
            if message.agent_id in self.agents:
                self.agents[message.agent_id]["message_count"] += 1

        # Notify subscribers
        topics_to_notify = [
            f"all",
            f"type:{message.message_type.value}",
            f"role:{message.agent_role.value}",
            f"symbol:{message.symbol}" if message.symbol else None,
        ]

        for topic in topics_to_notify:
            if topic and topic in self.subscribers:
                for callback in self.subscribers[topic]:
                    try:
                        await callback(message)
                    except Exception as e:
                        logger.error(f"Subscriber callback error: {e}")

        # If Pub/Sub is enabled, also broadcast there
        if self._pubsub_enabled:
            try:
                from pubsub import publish

                await publish("cognitive-mesh", message.to_dict())
            except Exception as e:
                logger.warning(f"Pub/Sub broadcast failed: {e}")

    def subscribe(self, topic: str, callback: Callable) -> None:
        """Subscribe to messages on a specific topic."""
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)
        logger.debug(f"📡 Subscribed to topic: {topic}")

    async def initiate_consensus(
        self,
        symbol: str,
        initiator_id: str,
        initial_message: CognitiveMessage,
        required_agents: int = 2,
        timeout_seconds: float = 10.0,
    ) -> ConsensusState:
        """
        Initiate a consensus decision on a trading action.

        Returns the ConsensusState which can be polled for completion.
        """
        consensus_id = f"consensus-{symbol}-{int(datetime.utcnow().timestamp())}"

        state = ConsensusState(
            consensus_id=consensus_id,
            symbol=symbol,
            initiated_by=initiator_id,
            initiated_at=datetime.utcnow(),
            required_agents=required_agents,
        )

        # Add initiator's vote
        state.add_vote(initial_message)

        async with self._lock:
            self.active_consensus[consensus_id] = state

        # Broadcast consensus request
        await self.broadcast(
            CognitiveMessage(
                message_id=f"consensus-req-{consensus_id}",
                agent_id=initiator_id,
                agent_role=initial_message.agent_role,
                message_type=MessageType.HYPOTHESIS,
                reasoning=f"CONSENSUS REQUEST: {initial_message.reasoning}",
                symbol=symbol,
                suggested_action=initial_message.suggested_action,
                confidence=initial_message.confidence,
                metadata={"consensus_id": consensus_id},
            )
        )

        logger.info(f"🗳️ Consensus initiated: {consensus_id} for {symbol}")
        return state

    async def vote_on_consensus(
        self,
        consensus_id: str,
        vote_message: CognitiveMessage,
    ) -> Dict[str, Any]:
        """Submit a vote to an active consensus decision."""
        async with self._lock:
            if consensus_id not in self.active_consensus:
                return {"error": "Consensus not found or expired"}

            state = self.active_consensus[consensus_id]
            state.add_vote(vote_message)

            # Check if we can finalize
            if state.can_finalize():
                result = state.compute_consensus()

                if result["status"] == "consensus_reached":
                    # Broadcast the decision
                    await self.broadcast(
                        CognitiveMessage(
                            message_id=f"consensus-decision-{consensus_id}",
                            agent_id="mesh",
                            agent_role=AgentRole.ORACLE,
                            message_type=MessageType.CONSENSUS,
                            reasoning=result["reasoning"],
                            symbol=state.symbol,
                            suggested_action=result["action"],
                            confidence=result["confidence"],
                            metadata={
                                "consensus_id": consensus_id,
                                "consensus_hash": result["consensus_hash"],
                            },
                        )
                    )

                    logger.info(f"✅ Consensus reached: {consensus_id} -> {result['action']}")

                return result

            return {"status": "vote_recorded", "votes": len(state.votes)}

    def get_recent_messages(
        self,
        limit: int = 50,
        message_type: Optional[MessageType] = None,
        symbol: Optional[str] = None,
    ) -> List[CognitiveMessage]:
        """Retrieve recent messages from the mesh."""
        messages = self.message_log[-limit * 10 :]  # Get more, then filter

        if message_type:
            messages = [m for m in messages if m.message_type == message_type]
        if symbol:
            messages = [m for m in messages if m.symbol == symbol]

        return messages[-limit:]

    def get_reasoning_trail(self, consensus_id: str) -> List[Dict[str, Any]]:
        """Get the full reasoning trail for a consensus decision (for explainability)."""
        if consensus_id not in self.active_consensus:
            return []

        state = self.active_consensus[consensus_id]
        trail = []

        for agent_id, msg in state.votes.items():
            trail.append(
                {
                    "agent": agent_id,
                    "role": msg.agent_role.value,
                    "reasoning": msg.reasoning,
                    "action": msg.suggested_action,
                    "confidence": msg.confidence,
                    "hash": msg.get_reasoning_hash(),
                }
            )

        if state.decision:
            trail.append(
                {
                    "agent": "CONSENSUS",
                    "role": "oracle",
                    "reasoning": state.decision_reasoning,
                    "action": state.decision,
                    "confidence": 1.0,
                    "hash": state.get_consensus_hash(),
                }
            )

        return trail


# Global mesh instance
_mesh_instance: Optional[CognitiveMesh] = None


def get_cognitive_mesh() -> CognitiveMesh:
    """Get or create the global cognitive mesh instance."""
    global _mesh_instance
    if _mesh_instance is None:
        _mesh_instance = CognitiveMesh()
    return _mesh_instance


async def init_cognitive_mesh() -> CognitiveMesh:
    """Initialize the cognitive mesh with Pub/Sub integration."""
    mesh = get_cognitive_mesh()

    try:
        from pubsub import subscribe

        async def handle_mesh_message(data: Dict[str, Any]):
            msg = CognitiveMessage.from_dict(data)
            await mesh.broadcast(msg)

        await subscribe("cognitive-mesh", handle_mesh_message)
        mesh._pubsub_enabled = True
        logger.info("🧠 Cognitive Mesh initialized with Pub/Sub")
    except Exception as e:
        logger.warning(f"Cognitive Mesh running in local mode: {e}")

    return mesh
