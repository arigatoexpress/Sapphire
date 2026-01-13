"""
Emergency Close All Positions - Safety Kill Switch.

Provides functions to close all open positions across all integrated platforms:
- Aster (Spot & Perps)
- Symphony (Swaps & Perps)
- Drift (Perps)
- Hyperliquid (Perps)

Usage:
    # From API endpoint
    await close_all_positions()
    
    # From CLI
    python -m cloud_trader.emergency_close
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EmergencyClose:
    """Emergency position closer for all integrated platforms."""
    
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        
    async def close_all_positions(self, dry_run: bool = False) -> Dict[str, Any]:
        """Close all open positions across all platforms.
        
        Args:
            dry_run: If True, only report positions without closing
            
        Returns:
            Dict with results from each platform
        """
        logger.warning("🚨 EMERGENCY CLOSE ALL POSITIONS INITIATED")
        
        results = {
            "aster": await self._close_aster_positions(dry_run),
            "symphony": await self._close_symphony_positions(dry_run),
            "drift": await self._close_drift_positions(dry_run),
            "hyperliquid": await self._close_hyperliquid_positions(dry_run),
            "total_closed": 0,
            "total_errors": 0,
            "dry_run": dry_run,
        }
        
        # Aggregate totals
        for platform in ["aster", "symphony", "drift", "hyperliquid"]:
            results["total_closed"] += results[platform].get("closed", 0)
            results["total_errors"] += results[platform].get("errors", 0)
        
        status = "DRY RUN" if dry_run else "EXECUTED"
        logger.warning(
            f"🚨 EMERGENCY CLOSE {status}: "
            f"{results['total_closed']} positions closed, "
            f"{results['total_errors']} errors"
        )
        
        return results
    
    async def _close_aster_positions(self, dry_run: bool) -> Dict[str, Any]:
        """Close all positions on Aster (main CEX)."""
        result = {"platform": "aster", "positions": [], "closed": 0, "errors": 0}
        
        try:
            from .exchange import AsterClient
            from .config import get_settings
            
            settings = get_settings()
            client = AsterClient(
                api_key=settings.aster_api_key or "",
                api_secret=settings.aster_secret_key or "",
            )
            
            # Get all open positions
            positions = await client.get_account_positions()
            
            for pos in positions:
                symbol = pos.get("symbol", "")
                qty = float(pos.get("positionAmt", 0) or pos.get("quantity", 0))
                
                if abs(qty) < 0.0001:
                    continue
                    
                result["positions"].append({
                    "symbol": symbol,
                    "quantity": qty,
                    "side": "LONG" if qty > 0 else "SHORT",
                })
                
                if not dry_run:
                    try:
                        # Close by placing opposite order
                        side = "SELL" if qty > 0 else "BUY"
                        await client.place_market_order(
                            symbol=symbol,
                            side=side,
                            quantity=abs(qty),
                        )
                        result["closed"] += 1
                        logger.info(f"✅ Closed Aster position: {symbol} {abs(qty)}")
                    except Exception as e:
                        result["errors"] += 1
                        logger.error(f"❌ Failed to close Aster {symbol}: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Aster emergency close error: {e}")
            result["error"] = str(e)
            
        return result
    
    async def _close_symphony_positions(self, dry_run: bool) -> Dict[str, Any]:
        """Close all positions on Symphony (Monad chain)."""
        result = {"platform": "symphony", "positions": [], "closed": 0, "errors": 0}
        
        try:
            from .symphony_client import SymphonyClient
            from .symphony_config import AGENTS_CONFIG
            
            client = SymphonyClient()
            
            # Close positions for each agent (MILF, AGDG)
            for agent_name, agent_config in AGENTS_CONFIG.items():
                agent_id = agent_config["agent_id"]
                
                try:
                    positions = await client.get_perpetual_positions(agent_id=agent_id)
                    
                    for pos in positions:
                        symbol = pos.get("symbol", "")
                        size = float(pos.get("size", 0))
                        
                        if abs(size) < 0.0001:
                            continue
                            
                        result["positions"].append({
                            "symbol": symbol,
                            "quantity": size,
                            "agent": agent_name,
                        })
                        
                        if not dry_run:
                            try:
                                await client.close_perpetual_position(
                                    symbol=symbol,
                                    agent_id=agent_id,
                                )
                                result["closed"] += 1
                                logger.info(f"✅ Closed Symphony position: {agent_name}/{symbol}")
                            except Exception as e:
                                result["errors"] += 1
                                logger.error(f"❌ Failed to close Symphony {agent_name}/{symbol}: {e}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not fetch Symphony positions for {agent_name}: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Symphony emergency close error: {e}")
            result["error"] = str(e)
            
        return result
    
    async def _close_drift_positions(self, dry_run: bool) -> Dict[str, Any]:
        """Close all positions on Drift (Solana DEX)."""
        result = {"platform": "drift", "positions": [], "closed": 0, "errors": 0}
        
        try:
            from .drift_client import DriftClient
            
            client = DriftClient()
            
            if not client.initialized:
                result["error"] = "Drift client not initialized"
                return result
            
            # Get open positions
            positions = await client.get_positions()
            
            for pos in positions:
                symbol = pos.get("symbol", "")
                size = float(pos.get("base_asset_amount", 0))
                
                if abs(size) < 0.0001:
                    continue
                    
                result["positions"].append({
                    "symbol": symbol,
                    "quantity": size,
                })
                
                if not dry_run:
                    try:
                        await client.close_position(symbol)
                        result["closed"] += 1
                        logger.info(f"✅ Closed Drift position: {symbol}")
                    except Exception as e:
                        result["errors"] += 1
                        logger.error(f"❌ Failed to close Drift {symbol}: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Drift emergency close error: {e}")
            result["error"] = str(e)
            
        return result
    
    async def _close_hyperliquid_positions(self, dry_run: bool) -> Dict[str, Any]:
        """Close all positions on Hyperliquid."""
        result = {"platform": "hyperliquid", "positions": [], "closed": 0, "errors": 0}
        
        try:
            from .hyperliquid_client import HyperliquidClient
            
            client = HyperliquidClient()
            
            # Get open positions
            positions = await client.get_positions()
            
            for pos in positions:
                symbol = pos.get("coin", pos.get("symbol", ""))
                size = float(pos.get("szi", pos.get("size", 0)))
                
                if abs(size) < 0.0001:
                    continue
                    
                result["positions"].append({
                    "symbol": symbol,
                    "quantity": size,
                })
                
                if not dry_run:
                    try:
                        await client.close_position(symbol)
                        result["closed"] += 1
                        logger.info(f"✅ Closed Hyperliquid position: {symbol}")
                    except Exception as e:
                        result["errors"] += 1
                        logger.error(f"❌ Failed to close Hyperliquid {symbol}: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Hyperliquid emergency close error: {e}")
            result["error"] = str(e)
            
        return result


# Convenience function
async def close_all_positions(dry_run: bool = False) -> Dict[str, Any]:
    """Close all open positions across all platforms.
    
    Args:
        dry_run: If True, only report positions without closing
        
    Returns:
        Dict with results from each platform
    """
    closer = EmergencyClose()
    return await closer.close_all_positions(dry_run)


async def get_all_positions() -> Dict[str, Any]:
    """Get all open positions without closing (dry run)."""
    return await close_all_positions(dry_run=True)


# CLI entry point
if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Emergency close all positions")
    parser.add_argument("--dry-run", action="store_true", help="Only show positions, don't close")
    parser.add_argument("--confirm", action="store_true", help="Confirm closing positions")
    args = parser.parse_args()
    
    async def main():
        if not args.dry_run and not args.confirm:
            print("⚠️  This will close ALL positions across ALL platforms!")
            print("    Run with --dry-run to see positions first")
            print("    Run with --confirm to actually close positions")
            return
        
        result = await close_all_positions(dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
    
    asyncio.run(main())
