#!/usr/bin/env python3
"""Run backtest validation for trading strategies."""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from cloud_trader.backtest import run_strategy_validation


async def main():
    """Run the backtest validation."""
    print("Starting strategy backtest validation...")
    print("-" * 60)
    
    results = await run_strategy_validation()
    
    # Save results to file
    results_file = Path("backtest_results.json")
    
    # Create summary
    summary = {
        "total_trades": results.total_trades,
        "win_rate": results.win_rate,
        "total_return": results.total_return,
        "annualized_return": results.annualized_return,
        "max_drawdown": results.max_drawdown,
        "sharpe_ratio": results.sharpe_ratio,
        "profit_factor": results.profit_factor,
        "meets_target": results.annualized_return >= 0.49,
        "strategy_performance": results.strategy_performance
    }
    
    import json
    with open(results_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nResults saved to {results_file}")
    
    # Exit code based on whether we meet targets
    sys.exit(0 if summary["meets_target"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
