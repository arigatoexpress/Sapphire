from typing import Literal, Optional

from pydantic import BaseModel, Field


class OrderIntent(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    type: Literal["MARKET", "LIMIT"]
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    reduce_only: bool = False
    time_in_force: Literal["GTC", "IOC", "FOK"] = "GTC"


class RiskCheckResponse(BaseModel):
    approved: bool
    reason: Optional[str] = None
    order_id: Optional[str] = None
