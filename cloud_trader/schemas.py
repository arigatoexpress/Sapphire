"""Pydantic schemas for external integrations and telemetry."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from pydantic import ConfigDict


class MarketContext(BaseModel):
    symbol: str
    price: float = Field(ge=0)
    change_24h: float
    volume: float = Field(ge=0)
    current_price: Optional[float] = None
    current_position: Optional[Dict[str, Any]] = None


class TradingDecision(BaseModel):
    side: Optional[str] = Field(None, description="BUY, SELL, HOLD, or CLOSE")

class TradingContext(BaseModel):
    symbol: str
    price: float
    current_position: Optional[dict] = None

class ReasoningSlice(BaseModel):
    source: str
    rationale: str

class InferenceRequest(BaseModel):
    bot_id: str
    decision: TradingDecision
    context: TradingContext
    confidence: Optional[float] = None
    reasoning: Optional[List[ReasoningSlice]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DecisionEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    side: Literal["BUY", "SELL", "HOLD", "CLOSE"] = Field(alias="action")
    size: Optional[float] = Field(default=None, ge=0)
    take_profit: Optional[float] = Field(default=None, gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)


class ReasoningSlice(BaseModel):
    role: Literal["observation", "thought", "action"] = "thought"
    content: str


class InferenceRequest(BaseModel):
    bot_id: str
    context: MarketContext
    decision: DecisionEnvelope
    reasoning: List[ReasoningSlice] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StreamEvent(BaseModel):
    kind: Literal["decision", "position", "reasoning", "health"]
    payload: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "gemini-1.5-flash"  # Google Cloud AI default
    messages: List[ChatMessage]
    max_tokens: int = Field(default=256, ge=1, le=2048)
    temperature: float = Field(default=0.2, ge=0, le=2)
    endpoint: Optional[str] = None

