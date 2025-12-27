from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from .logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ===================================================================
# SYMPHONY / MONAD INTEGRATION ENDPOINTS
# ===================================================================


@router.get("/api/symphony/status")
async def get_symphony_status() -> Dict[str, Any]:
    """
    Get Symphony (Monad) MIT fund status and activation progress.

    Returns activation status and fund information for the MIT dashboard.
    """
    try:
        from .symphony_client import get_symphony_client
        from .symphony_config import validate_symphony_config

        # Check if Symphony is configured
        if not validate_symphony_config():
            return {
                "configured": False,
                "error": "Symphony API not configured. Add SYMPHONY_API_KEY to environment.",
                "fund": {
                    "name": "Sapphire MIT Agent",
                    "balance": 0,
                    "is_activated": False,
                    "trades_count": 0,
                },
                "trades_count": 0,
                "is_activated": False,
                "activation_progress": {
                    "current": 0,
                    "required": 5,
                    "percentage": 0,
                    "activated": False,
                },
            }

        # Get Symphony client and fetch account info
        client = get_symphony_client()
        account = await client.get_account_info()

        return {
            "configured": True,
            "fund": {
                "id": account.get("id"),
                "name": account.get("name", "Sapphire MIT Agent"),
                "balance": account.get("balance", {}).get("USDC", 0),
                "is_activated": account.get("is_activated", False),
                "trades_count": account.get("trades_count", 0),
            },
            "trades_count": account.get("trades_count", 0),
            "is_activated": account.get("is_activated", False),
            "activation_progress": client.activation_progress,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Symphony status check failed: {e}")
        return {
            "configured": False,
            "error": str(e),
            "fund": {
                "name": "Sapphire MIT Agent",
                "balance": 0,
                "is_activated": False,
                "trades_count": 0,
            },
            "trades_count": 0,
            "is_activated": False,
            "activation_progress": {
                "current": 0,
                "required": 5,
                "percentage": 0,
                "activated": False,
            },
        }


@router.post("/api/symphony/activate-demo")
async def activate_symphony_demo() -> Dict[str, Any]:
    """
    Execute 5 small trades to activate the Symphony fund for demo purposes.

    This endpoint does NOT require authentication and is for development only.
    Each trade is a minimal size to meet the activation threshold.

    Returns:
        Activation progress and trade results.
    """
    try:
        from .symphony_client import get_symphony_client

        client = get_symphony_client()

        # Check current activation status
        progress = client.activation_progress
        if progress["activated"]:
            return {
                "success": True,
                "already_activated": True,
                "message": "Fund is already activated!",
                "activation_progress": progress,
            }

        trades_needed = 5 - progress["current"]
        trade_results = []

        # Execute minimal trades to activate
        symbols = ["BTC-USDC", "ETH-USDC", "SOL-USDC", "BTC-USDC", "ETH-USDC"]
        sides = ["LONG", "SHORT", "LONG", "SHORT", "LONG"]

        for i in range(min(trades_needed, 5)):
            try:
                result = await client.open_perpetual_position(
                    symbol=symbols[i % len(symbols)],
                    side=sides[i % len(sides)],
                    size=10.0,  # Minimum $10 trade
                    leverage=1,
                )
                trade_results.append(
                    {
                        "trade_number": i + 1,
                        "symbol": symbols[i % len(symbols)],
                        "side": sides[i % len(sides)],
                        "result": result,
                        "success": True,
                    }
                )
                logger.info(
                    f"✅ Activation trade {i + 1}/{trades_needed}: {symbols[i % len(symbols)]} {sides[i % len(sides)]}"
                )
            except Exception as trade_error:
                trade_results.append(
                    {
                        "trade_number": i + 1,
                        "symbol": symbols[i % len(symbols)],
                        "side": sides[i % len(sides)],
                        "error": str(trade_error),
                        "success": False,
                    }
                )
                logger.warning(f"⚠️ Activation trade {i + 1} failed: {trade_error}")

        return {
            "success": True,
            "trades_executed": len([t for t in trade_results if t.get("success")]),
            "trades_needed": trades_needed,
            "trade_results": trade_results,
            "activation_progress": client.activation_progress,
            "message": f"Executed {len(trade_results)} activation trades",
        }
    except Exception as e:
        logger.error(f"Symphony activation failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/api/symphony/trade/perpetual")
async def execute_symphony_perpetual(request: Request) -> Dict[str, Any]:
    """
    Execute a perpetual futures trade on Symphony/Monad.

    Body:
    {
        "symbol": "BTC-USDC",
        "side": "LONG" | "SHORT",
        "size": 100,
        "leverage": 3,
        "stop_loss": 42000 (optional),
        "take_profit": 45000 (optional)
    }
    """
    try:
        from .symphony_client import get_symphony_client
        from .symphony_config import MIT_DEFAULT_LEVERAGE, MIT_MAX_POSITION_SIZE_USDC

        # Require authentication
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        body = await request.json()
        symbol = body.get("symbol")
        side = body.get("side")
        size = float(body.get("size", 0))
        leverage = int(body.get("leverage", MIT_DEFAULT_LEVERAGE))
        stop_loss = body.get("stop_loss")
        take_profit = body.get("take_profit")

        # Validation
        if not symbol or not side:
            raise HTTPException(status_code=400, detail="symbol and side are required")
        if size <= 0:
            raise HTTPException(status_code=400, detail="size must be positive")
        if size > MIT_MAX_POSITION_SIZE_USDC:
            raise HTTPException(
                status_code=400, detail=f"size exceeds maximum of ${MIT_MAX_POSITION_SIZE_USDC}"
            )

        # Execute trade
        client = get_symphony_client()
        position = await client.open_perpetual_position(
            symbol=symbol,
            side=side,
            size=size,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        logger.info(f"Symphony perpetual opened: {symbol} {side} {size} @ {leverage}x by {uid}")

        return {
            "success": True,
            "position": position,
            "message": f"Perpetual position opened: {side} {symbol}",
            "activation_progress": client.activation_progress,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Symphony perpetual trade failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/api/symphony/trade/spot")
async def execute_symphony_spot(request: Request) -> Dict[str, Any]:
    """
    Execute a spot trade on Symphony/Monad.

    Body:
    {
        "symbol": "BTC-USDC",
        "side": "BUY" | "SELL",
        "quantity": 0.01,
        "order_type": "market" | "limit"
    }
    """
    try:
        from .symphony_client import get_symphony_client

        # Require authentication
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        body = await request.json()
        symbol = body.get("symbol")
        side = body.get("side")
        quantity = float(body.get("quantity", 0))
        order_type = body.get("order_type", "market")

        # Validation
        if not symbol or not side:
            raise HTTPException(status_code=400, detail="symbol and side are required")
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="quantity must be positive")

        # Execute trade
        client = get_symphony_client()
        order = await client.execute_spot_trade(
            symbol=symbol, side=side, quantity=quantity, order_type=order_type
        )

        logger.info(f"Symphony spot trade: {side} {quantity} {symbol} by {uid}")

        return {
            "success": True,
            "order": order,
            "message": f"Spot trade executed: {side} {quantity} {symbol}",
            "activation_progress": client.activation_progress,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Symphony spot trade failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/api/symphony/positions")
async def get_symphony_positions() -> Dict[str, Any]:
    """Get all open Symphony perpetual positions."""
    try:
        from .symphony_client import get_symphony_client

        client = get_symphony_client()
        positions = await client.get_perpetual_positions()

        return {"success": True, "positions": positions, "count": len(positions)}
    except Exception as e:
        logger.error(f"Failed to get Symphony positions: {e}")
        return {"success": False, "error": str(e), "positions": []}


@router.post("/api/symphony/fund/create")
async def create_symphony_fund(request: Request) -> Dict[str, Any]:
    """
    Create a new agentic fund on Symphony.

    Body:
    {
        "name": "My Trading Fund",
        "description": "AI-powered autonomous trading",
        "fund_type": "perpetuals",
        "autosubscribe": true
    }
    """
    try:
        from .symphony_client import get_symphony_client

        # Require authentication
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        body = await request.json()
        name = body.get("name", "Sapphire MIT Agent")
        description = body.get("description", "Autonomous AI trading on Monad")
        fund_type = body.get("fund_type", "perpetuals")
        autosubscribe = body.get("autosubscribe", True)

        client = get_symphony_client()
        fund = await client.create_agentic_fund(
            name=name, description=description, fund_type=fund_type, autosubscribe=autosubscribe
        )

        logger.info(f"MIT fund created: {name} by {uid}")

        return {
            "success": True,
            "fund": fund,
            "message": f"Agentic fund '{name}' created successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Symphony fund creation failed: {e}")
        return {"success": False, "error": str(e)}
