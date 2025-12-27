#!/usr/bin/env python3
"""
Sapphire AI Trading System - Connectivity Verification Tool
============================================================
A professional-grade diagnostic tool to verify connectivity to all
core trading platforms (Aster, Symphony, Drift) before cloud deployment.

Usage:
    python tools/verify_connectivity.py
"""

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

# =============================================================================
# Data Models
# =============================================================================

@dataclass
class ConnectivityResult:
    """Result of a single connectivity check."""
    service: str
    test_name: str
    passed: bool
    latency_ms: float = 0.0
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ServiceReport:
    """Aggregated results for a single service."""
    service: str
    is_healthy: bool
    results: List[ConnectivityResult] = field(default_factory=list)
    overall_latency_ms: float = 0.0

# =============================================================================
# Aster Connectivity Checks
# =============================================================================

async def check_aster_public_ping() -> ConnectivityResult:
    """
    Verify Aster API is publicly accessible (unauthenticated).
    Test: GET /fapi/v1/time
    """
    url = "https://fapi.asterdex.com/fapi/v1/time"
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            latency = (time.perf_counter() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                return ConnectivityResult(
                    service="Aster",
                    test_name="Public API Ping",
                    passed=True,
                    latency_ms=latency,
                    message=f"Server Time: {data.get('serverTime')}",
                    details=data
                )
            else:
                return ConnectivityResult(
                    service="Aster",
                    test_name="Public API Ping",
                    passed=False,
                    latency_ms=latency,
                    message=f"HTTP {resp.status_code}"
                )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ConnectivityResult(
            service="Aster",
            test_name="Public API Ping",
            passed=False,
            latency_ms=latency,
            message=str(e)
        )

async def check_aster_authenticated() -> ConnectivityResult:
    """
    Verify Aster API credentials (authenticated request).
    Test: GET /fapi/v2/balance (signed)
    """
    from cloud_trader.config import get_settings
    from cloud_trader.credentials import Credentials
    from cloud_trader.exchange import AsterClient

    settings = get_settings()
    
    if not settings.aster_api_key or not settings.aster_api_secret:
        return ConnectivityResult(
            service="Aster",
            test_name="Authenticated Balance Check",
            passed=False,
            message="❌ ASTER_API_KEY or ASTER_SECRET_KEY not configured."
        )

    creds = Credentials(
        api_key=settings.aster_api_key,
        api_secret=settings.aster_api_secret
    )
    client = AsterClient(credentials=creds)
    start = time.perf_counter()
    try:
        balance = await client.get_account_balance()
        latency = (time.perf_counter() - start) * 1000
        await client.close()
        
        # Extract USDC balance
        usdc_balance = 0.0
        for asset in balance:
            if asset.get("asset") == "USDC":
                usdc_balance = float(asset.get("availableBalance", 0))
                break
        
        return ConnectivityResult(
            service="Aster",
            test_name="Authenticated Balance Check",
            passed=True,
            latency_ms=latency,
            message=f"USDC Balance: ${usdc_balance:,.2f}",
            details={"usdc_balance": usdc_balance, "raw": balance[:2]}  # Truncate for report
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        await client.close()
        return ConnectivityResult(
            service="Aster",
            test_name="Authenticated Balance Check",
            passed=False,
            latency_ms=latency,
            message=str(e)
        )

async def check_aster_exchange_info() -> ConnectivityResult:
    """
    Verify Aster Exchange Info endpoint.
    Test: GET /fapi/v1/exchangeInfo
    """
    from cloud_trader.exchange import AsterClient
    
    client = AsterClient()
    start = time.perf_counter()
    try:
        info = await client.get_exchange_info()
        latency = (time.perf_counter() - start) * 1000
        await client.close()
        
        symbols = info.get("symbols", [])
        return ConnectivityResult(
            service="Aster",
            test_name="Exchange Info",
            passed=True,
            latency_ms=latency,
            message=f"{len(symbols)} trading pairs available.",
            details={"symbol_count": len(symbols)}
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        await client.close()
        return ConnectivityResult(
            service="Aster",
            test_name="Exchange Info",
            passed=False,
            latency_ms=latency,
            message=str(e)
        )


# =============================================================================
# Symphony Connectivity Checks
# =============================================================================

async def check_symphony_ping() -> ConnectivityResult:
    """
    Verify Symphony API is accessible.
    Test: GET /health or a public endpoint.
    """
    from cloud_trader.symphony_config import SYMPHONY_BASE_URL
    
    url = f"{SYMPHONY_BASE_URL}/health"
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            latency = (time.perf_counter() - start) * 1000
            # Symphony may not have a /health, so accept 2xx or 404 as "reachable"
            if resp.status_code < 500:
                return ConnectivityResult(
                    service="Symphony",
                    test_name="API Ping",
                    passed=True,
                    latency_ms=latency,
                    message=f"Status: {resp.status_code} (Reachable)"
                )
            else:
                return ConnectivityResult(
                    service="Symphony",
                    test_name="API Ping",
                    passed=False,
                    latency_ms=latency,
                    message=f"HTTP {resp.status_code}"
                )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ConnectivityResult(
            service="Symphony",
            test_name="API Ping",
            passed=False,
            latency_ms=latency,
            message=str(e)
        )

async def check_symphony_authenticated() -> ConnectivityResult:
    """
    Verify Symphony authentication by fetching account info.
    """
    from cloud_trader.symphony_client import get_symphony_client
    from cloud_trader.symphony_config import SYMPHONY_API_KEY

    if not SYMPHONY_API_KEY:
        return ConnectivityResult(
            service="Symphony",
            test_name="Authenticated Account Info",
            passed=False,
            message="❌ SYMPHONY_API_KEY not configured."
        )

    client = get_symphony_client()
    start = time.perf_counter()
    try:
        account_info = await client.get_account_info()
        latency = (time.perf_counter() - start) * 1000
        await client.close()
        
        return ConnectivityResult(
            service="Symphony",
            test_name="Authenticated Account Info",
            passed=True,
            latency_ms=latency,
            message=f"Account Status: {account_info.get('status', 'N/A')}",
            details={"account_info": account_info}
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        await client.close()
        return ConnectivityResult(
            service="Symphony",
            test_name="Authenticated Account Info",
            passed=False,
            latency_ms=latency,
            message=str(e)
        )

async def check_symphony_strategy_subscription() -> ConnectivityResult:
    """
    Verify Symphony Strategy Subscription capability.
    """
    from cloud_trader.symphony_client import get_symphony_client
    from cloud_trader.symphony_config import SYMPHONY_API_KEY

    if not SYMPHONY_API_KEY:
        return ConnectivityResult(
            service="Symphony",
            test_name="Strategy Subscription",
            passed=False,
            message="❌ API Key not configured."
        )

    client = get_symphony_client()
    start = time.perf_counter()
    try:
        result = await client.subscribe_strategy("sapphire-connectivity-test")
        latency = (time.perf_counter() - start) * 1000
        await client.close()
        
        return ConnectivityResult(
            service="Symphony",
            test_name="Strategy Subscription",
            passed=True,
            latency_ms=latency,
            message="Subscription OK"
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        await client.close()
        return ConnectivityResult(
            service="Symphony",
            test_name="Strategy Subscription",
            passed=False,
            latency_ms=latency,
            message=str(e)
        )


# =============================================================================
# Drift Connectivity Checks
# =============================================================================

async def check_drift_rpc() -> ConnectivityResult:
    """
    Verify Solana RPC connectivity (for Drift).
    """
    rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
            )
            latency = (time.perf_counter() - start) * 1000
            data = resp.json()
            
            if "result" in data and data["result"] == "ok":
                return ConnectivityResult(
                    service="Drift (Solana RPC)",
                    test_name="RPC Health Check",
                    passed=True,
                    latency_ms=latency,
                    message=f"RPC OK: {rpc_url[:40]}..."
                )
            else:
                return ConnectivityResult(
                    service="Drift (Solana RPC)",
                    test_name="RPC Health Check",
                    passed=False,
                    latency_ms=latency,
                    message=f"RPC Error: {data.get('error', 'Unknown')}"
                )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ConnectivityResult(
            service="Drift (Solana RPC)",
            test_name="RPC Health Check",
            passed=False,
            latency_ms=latency,
            message=str(e)
        )

async def check_drift_market_data() -> ConnectivityResult:
    """
    Verify Drift market data fetch.
    """
    from cloud_trader.drift_client import get_drift_client

    client = get_drift_client()
    start = time.perf_counter()
    try:
        await client.initialize()
        market = await client.get_perp_market("SOL-PERP")
        latency = (time.perf_counter() - start) * 1000
        
        price = market.get("oracle_price", 0)
        return ConnectivityResult(
            service="Drift",
            test_name="Market Data (SOL-PERP)",
            passed=price > 0,
            latency_ms=latency,
            message=f"SOL Price: ${price:,.2f}" if price > 0 else "Price unavailable",
            details=market
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return ConnectivityResult(
            service="Drift",
            test_name="Market Data (SOL-PERP)",
            passed=False,
            latency_ms=latency,
            message=str(e)
        )


# =============================================================================
# Report Generation
# =============================================================================

def print_report(reports: List[ServiceReport]):
    """Print a formatted connectivity report."""
    print("\n" + "=" * 70)
    print("🔌 SAPPHIRE AI - CONNECTIVITY VERIFICATION REPORT")
    print("=" * 70)
    
    all_passed = True
    total_latency = 0.0
    test_count = 0
    
    for report in reports:
        emoji = "✅" if report.is_healthy else "❌"
        print(f"\n{emoji} {report.service} (Avg Latency: {report.overall_latency_ms:.0f}ms)")
        print("-" * 50)
        
        for result in report.results:
            status = "✓" if result.passed else "✗"
            latency_str = f"[{result.latency_ms:.0f}ms]" if result.latency_ms > 0 else ""
            print(f"  {status} {result.test_name}: {result.message} {latency_str}")
            
            if not result.passed:
                all_passed = False
            total_latency += result.latency_ms
            test_count += 1
    
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("-" * 50)
    status = "READY FOR DEPLOYMENT ✅" if all_passed else "ISSUES DETECTED ❌"
    avg_latency = total_latency / test_count if test_count > 0 else 0
    print(f"  Overall Status: {status}")
    print(f"  Average Latency: {avg_latency:.0f}ms")
    print(f"  Tests Run: {test_count}")
    print("=" * 70 + "\n")
    
    return all_passed


async def run_all_checks() -> List[ServiceReport]:
    """Run all connectivity checks for all services."""
    
    # ===== Aster =====
    print("🔍 Checking Aster Connectivity...", flush=True)
    aster_results = [
        await check_aster_public_ping(),
        await check_aster_exchange_info(),
        await check_aster_authenticated(),
    ]
    aster_latency = sum(r.latency_ms for r in aster_results) / len(aster_results) if aster_results else 0
    aster_healthy = all(r.passed for r in aster_results)
    aster_report = ServiceReport(
        service="Aster DEX",
        is_healthy=aster_healthy,
        results=aster_results,
        overall_latency_ms=aster_latency
    )
    
    # ===== Symphony =====
    print("🔍 Checking Symphony Connectivity...", flush=True)
    symphony_results = [
        await check_symphony_ping(),
        await check_symphony_authenticated(),
        await check_symphony_strategy_subscription(),
    ]
    symphony_latency = sum(r.latency_ms for r in symphony_results) / len(symphony_results) if symphony_results else 0
    symphony_healthy = all(r.passed for r in symphony_results)
    symphony_report = ServiceReport(
        service="Symphony (Monad)",
        is_healthy=symphony_healthy,
        results=symphony_results,
        overall_latency_ms=symphony_latency
    )
    
    # ===== Drift =====
    print("🔍 Checking Drift Connectivity...", flush=True)
    drift_results = [
        await check_drift_rpc(),
        await check_drift_market_data(),
    ]
    drift_latency = sum(r.latency_ms for r in drift_results) / len(drift_results) if drift_results else 0
    drift_healthy = all(r.passed for r in drift_results)
    drift_report = ServiceReport(
        service="Drift (Solana)",
        is_healthy=drift_healthy,
        results=drift_results,
        overall_latency_ms=drift_latency
    )
    
    return [aster_report, symphony_report, drift_report]


async def main():
    """Main entry point for connectivity verification."""
    print("\n🚀 Starting Sapphire AI Connectivity Verification...\n")
    
    reports = await run_all_checks()
    success = print_report(reports)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
