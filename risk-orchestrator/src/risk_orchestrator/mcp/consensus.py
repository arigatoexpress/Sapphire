"""MCP consensus voting algorithm for multi-agent proposals."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from .schemas import MCPConsensusPayload


@dataclass
class ProposalVote:
    """Vote on a proposal."""

    agent_id: str
    approved: bool
    confidence: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProposalState:
    """State of a proposal awaiting consensus."""

    proposal_id: str
    proposal: MCPProposalPayload
    proposer_id: str
    votes: Dict[str, ProposalVote] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    timeout: float = 30.0  # 30 seconds to reach consensus
    min_votes: int = 3  # Minimum 3 agents must agree
    consensus_threshold: float = 0.67  # 67% approval needed


class ConsensusEngine:
    """Engine for managing consensus voting on MCP proposals."""

    def __init__(self):
        self._proposals: Dict[str, ProposalState] = {}
        self._lock = asyncio.Lock()

    async def register_proposal(
        self,
        proposal_id: str,
        proposal: MCPProposalPayload,
        proposer_id: str,
    ) -> ProposalState:
        """Register a new proposal for consensus voting."""
        async with self._lock:
            state = ProposalState(
                proposal_id=proposal_id,
                proposal=proposal,
                proposer_id=proposer_id,
            )
            self._proposals[proposal_id] = state
        return state

    async def cast_vote(
        self,
        proposal_id: str,
        agent_id: str,
        approved: bool,
        confidence: float = 0.5,
    ) -> Optional[MCPConsensusPayload]:
        """Cast a vote on a proposal and return consensus if reached."""
        async with self._lock:
            state = self._proposals.get(proposal_id)
            if not state:
                return None

            # Don't allow proposer to vote on their own proposal
            if agent_id == state.proposer_id:
                return None

            # Register vote
            state.votes[agent_id] = ProposalVote(
                agent_id=agent_id,
                approved=approved,
                confidence=confidence,
            )

            # Check if consensus reached
            return await self._check_consensus(state)

    async def _check_consensus(self, state: ProposalState) -> Optional[MCPConsensusPayload]:
        """Check if consensus has been reached on a proposal."""
        if len(state.votes) < state.min_votes:
            return None

        # Calculate approval rate
        approved_votes = sum(1 for vote in state.votes.values() if vote.approved)
        approval_rate = approved_votes / len(state.votes)

        # Check timeout
        elapsed = time.time() - state.created_at
        if elapsed > state.timeout:
            # Timeout reached, use current votes
            consensus_reached = approval_rate >= state.consensus_threshold
            participants = [vote.agent_id for vote in state.votes.values()]
            notes = f"Consensus {'reached' if consensus_reached else 'not reached'} after timeout ({len(state.votes)} votes, {approval_rate:.1%} approval)"

            # Clean up
            self._proposals.pop(state.proposal_id, None)

            return MCPConsensusPayload(
                approved=consensus_reached,
                consensus_score=approval_rate,
                participants=participants,
                notes=notes,
            )

        # Check if consensus threshold met
        if approval_rate >= state.consensus_threshold:
            consensus_reached = True
            participants = [vote.agent_id for vote in state.votes.values()]
            notes = f"Consensus reached with {len(state.votes)} votes ({approval_rate:.1%} approval)"

            # Clean up
            self._proposals.pop(state.proposal_id, None)

            return MCPConsensusPayload(
                approved=consensus_reached,
                consensus_score=approval_rate,
                participants=participants,
                notes=notes,
            )

        return None

    async def get_proposal_state(self, proposal_id: str) -> Optional[ProposalState]:
        """Get current state of a proposal."""
        async with self._lock:
            return self._proposals.get(proposal_id)

    async def cleanup_expired(self) -> None:
        """Clean up expired proposals."""
        current_time = time.time()
        async with self._lock:
            expired = [
                proposal_id
                for proposal_id, state in self._proposals.items()
                if current_time - state.created_at > state.timeout
            ]
            for proposal_id in expired:
                self._proposals.pop(proposal_id, None)


# Global consensus engine instance
_consensus_engine = ConsensusEngine()


async def get_consensus_engine() -> ConsensusEngine:
    """Get the global consensus engine instance."""
    return _consensus_engine

