# 🎯 SAPPHIRE AI - WORLD-CLASS MULTI-CHAIN TRADING PLATFORM
## Comprehensive Implementation Plan

---

## 📊 **EXECUTIVE SUMMARY**

**Vision**: Build the most advanced AI-powered multi-chain trading platform integrating:
- **Monad** (via Symphony) - High-performance L1 perpetuals
- **Solana** (via Jupiter + Drift) - DEX aggregation + perp trading
- **Unified AI** - Cross-chain intelligence and portfolio management

**Timeline**: 2-3 weeks for full implementation
**Architecture**: Microservices backend, React TypeScript frontend, real-time WebSocket data

---

## 🏗️ **ARCHITECTURE OVERVIEW**

```
┌─────────────────────────────────────────────────────────────┐
│                    SAPPHIRE AI PLATFORM                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   FRONTEND   │  │   BACKEND    │  │   AI ENGINE  │      │
│  │              │  │              │  │              │      │
│  │ • React/TS   │  │ • FastAPI    │  │ • Consensus  │      │
│  │ • Multi-chain│  │ • Python SDK │  │ • Agents     │      │
│  │ • Real-time  │  │ • WebSocket  │  │ • Analytics  │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
├─────────┼──────────────────┼──────────────────┼─────────────┤
│         ▼                  ▼                  ▼              │
│  ┌──────────────────────────────────────────────────┐       │
│  │            BLOCKCHAIN INTEGRATIONS                 │       │
│  ├──────────────┬──────────────┬──────────────┐     │       │
│  │   MONAD      │   SOLANA     │   SOLANA     │     │       │
│  │  (Symphony)  │  (Jupiter)   │  (Drift)     │     │       │
│  │              │              │              │     │       │
│  │ • Perpetuals │ • DEX Swap   │ • Perp Trade │     │       │
│  │ • Spot       │ • Routing    │ • Spot Trade │     │       │
│  │ • MIT Fund   │ • Price Feed │ • Orderbook  │     │       │
│  └──────────────┴──────────────┴──────────────┘     │       │
│                                                       │       │
└───────────────────────────────────────────────────────┘       │
```

---

## ✅ **PHASE 1: SYMPHONY (MONAD) - COMPLETE MIT ACTIVATION**

### **Current Status**: 90% Complete
- ✅ API client built
- ✅ Frontend dashboard
- ✅ Backend endpoints
- ⏳ Need: Agent ID to activate

### **Immediate Actions** (30 minutes)

**1.1 Get Agent ID from Symphony**
```bash
# User action required:
# 1. Visit https://app.symphony.io/agentic-funds
# 2. Find "MIT" fund
# 3. Copy Agent ID
```

**1.2 Execute Activation Trades**
```python
# File: scripts/activate_symphony.py (already created)
# Run with: SYMPHONY_API_KEY=sk_live_*** python3 scripts/activate_symphony.py

# Executes 5 trades:
# 1. LONG BTC $10 @ 1x
# 2. LONG ETH $10 @ 1x
# 3. LONG SOL $10 @ 1x
# 4. SHORT BTC $10 @ 1x
# 5. SHORT ETH $10 @ 1x
```

**1.3 Verify Activation**
```bash
curl https://cloud-trader-267358751314.europe-west1.run.app/api/symphony/status
# Should show: "is_activated": true, "trades_count": 5
```

### **Files** (All created ✅)
- `cloud_trader/symphony_client.py` - API integration
- `cloud_trader/symphony_config.py` - Configuration
- `cloud_trader/api.py` - Backend endpoints (lines 398-667)
- `trading-dashboard/src/pages/MonadMIT.tsx` - Frontend UI
- `trading-dashboard/src/components/SymphonyTradeForm.tsx` - Trading interface

---

## 🚀 **PHASE 2: JUPITER (SOLANA) - DEX AGGREGATION**

### **Objective**: Add Solana token swaps via Jupiter's Ultra Swap API

### **Implementation Plan** (1 week)

#### **2.1 Backend: Jupiter Client** (2 days)

**File**: `cloud_trader/jupiter_client.py`

```python
"""
Jupiter Ultra Swap API Integration for Solana DEX Aggregation
Documentation: https://dev.jup.ag/docs/ultra
"""

import httpx
from typing import Dict, Any, Optional
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
import base64

class JupiterClient:
    """
    Jupiter API client for Solana token swaps using Ultra Swap API.

    Features:
    - Quote fetching with best routes
    - Transaction building
    - Slippage protection
    - Priority fee optimization (handled by Jupiter)
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Jupiter client.

        Args:
            api_key: Jupiter API key (optional for higher rate limits)
        """
        self.base_url = "https://api.jup.ag"
        self.api_key = api_key

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Sapphire-AI/1.0"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=30.0
        )

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,  # in smallest unit (lamports for SOL)
        slippage_bps: int = 50  # 0.5% default
    ) -> Dict[str, Any]:
        """Get best swap quote from Jupiter."""
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount,
            "slippageBps": slippage_bps,
            "onlyDirectRoutes": False,  # Allow multi-hop
            "asLegacyTransaction": False  # Use versioned transactions
        }

        response = await self.client.get("/v6/quote", params=params)
        response.raise_for_status()
        return response.json()

    async def get_swap_transaction(
        self,
        quote: Dict[str, Any],
        user_public_key: str,
        wrap_unwrap_sol: bool = True,
        priority_level: str = "medium"  # low, medium, high, veryHigh
    ) -> Dict[str, Any]:
        """Get swap transaction from quote."""
        payload = {
            "quoteResponse": quote,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": wrap_unwrap_sol,
            "priorityLevelWithMaxLamports": {
                "priorityLevel": priority_level
            },
            "dynamicComputeUnitLimit": True  # Auto-optimize CU
        }

        response = await self.client.post("/v6/swap", json=payload)
        response.raise_for_status()
        return response.json()

    async def execute_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        wallet_keypair: Keypair,
        slippage_bps: int = 50
    ) -> Dict[str, Any]:
        """
        Complete swap execution flow.

        Returns transaction signature and swap details.
        """
        # 1. Get quote
        quote = await self.get_quote(input_mint, output_mint, amount, slippage_bps)

        # 2. Get swap transaction
        swap_result = await self.get_swap_transaction(
            quote,
            str(wallet_keypair.pubkey()),
            priority_level="medium"
        )

        # 3. Deserialize and sign transaction
        tx_bytes = base64.b64decode(swap_result["swapTransaction"])
        tx = VersionedTransaction.from_bytes(tx_bytes)
        tx.sign([wallet_keypair])

        # 4. Submit to Jupiter's execute endpoint (handles RPC submission)
        signed_tx_base64 = base64.b64encode(bytes(tx)).decode('utf-8')

        execute_response = await self.client.post(
            "/v6/swap/execute",
            json={"swapTransaction": signed_tx_base64}
        )
        execute_response.raise_for_status()

        return execute_response.json()
```

**Dependencies**:
```bash
pip install httpx solders solana
```

#### **2.2 Backend: API Endpoints** (1 day)

**File**: `cloud_trader/api.py` (add new section)

```python
# ===================================================================
# JUPITER (SOLANA) INTEGRATION ENDPOINTS
# ===================================================================

@app.get("/api/jupiter/quote")
async def get_jupiter_quote(
    input_mint: str,
    output_mint: str,
    amount: int,
    slippage_bps: int = 50
) -> Dict[str, Any]:
    """
    Get Jupiter swap quote.

    Example: BTC → USDC
    input_mint: So11111111111111111111111111111111111111112 (SOL)
    output_mint: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v (USDC)
    """
    try:
        from .jupiter_client import get_jupiter_client

        client = get_jupiter_client()
        quote = await client.get_quote(input_mint, output_mint, amount, slippage_bps)

        return {
            "success": True,
            "quote": quote,
            "input_amount": amount,
            "output_amount": quote.get("outAmount"),
            "price_impact": quote.get("priceImpactPct"),
            "route_plan": quote.get("routePlan")
        }
    except Exception as e:
        logger.error(f"Jupiter quote failed: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/jupiter/swap")
async def execute_jupiter_swap(request: Request) -> Dict[str, Any]:
    """
    Execute Jupiter swap.

    Body:
    {
        "input_mint": "So11...",
        "output_mint": "EPj...",
        "amount": 1000000,  // lamports
        "slippage_bps": 50
    }
    """
    try:
        from .jupiter_client import get_jupiter_client

        # Require authentication
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        body = await request.json()
        input_mint = body.get("input_mint")
        output_mint = body.get("output_mint")
        amount = int(body.get("amount"))
        slippage_bps = int(body.get("slippage_bps", 50))

        # Get user's Solana wallet (implement wallet management)
        wallet_keypair = get_user_solana_wallet(uid)

        client = get_jupiter_client()
        result = await client.execute_swap(
            input_mint,
            output_mint,
            amount,
            wallet_keypair,
            slippage_bps
        )

        logger.info(f"Jupiter swap executed by {uid}: {result.get('signature')}")

        return {
            "success": True,
            "signature": result.get("signature"),
            "message": f"Swap executed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Jupiter swap failed: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/jupiter/tokens")
async def get_jupiter_tokens() -> Dict[str, Any]:
    """Get list of supported Jupiter tokens."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://token.jup.ag/all")
            tokens = response.json()

        return {
            "success": True,
            "tokens": tokens,
            "count": len(tokens)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

#### **2.3 Frontend: Jupiter Swap UI** (2 days)

**File**: `trading-dashboard/src/pages/JupiterSwap.tsx`

```tsx
import React, { useState, useEffect } from 'react';
import { Wallet, ArrowDownUp, TrendingUp, Zap } from 'lucide-react';
import { motion } from 'framer-motion';
import { useConnection, useWallet } from '@solana/wallet-adapter-react';
import { WalletMultiButton } from '@solana/wallet-adapter-react-ui';

interface Token {
    address: string;
    symbol: string;
    name: string;
    decimals: number;
    logoURI?: string;
}

interface Quote {
    inputMint: string;
    outputMint: string;
    inAmount: string;
    outAmount: string;
    priceImpactPct: number;
    routePlan: any[];
}

export const JupiterSwap: React.FC = () => {
    const { connection } = useConnection();
    const { publicKey, signTransaction } = useWallet();

    const [tokens, setTokens] = useState<Token[]>([]);
    const [inputToken, setInputToken] = useState<Token | null>(null);
    const [outputToken, setOutputToken] = useState<Token | null>(null);
    const [inputAmount, setInputAmount] = useState('');
    const [quote, setQuote] = useState<Quote | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        fetchTokens();
    }, []);

    const fetchTokens = async () => {
        const response = await fetch(`${import.meta.env.VITE_API_URL}/api/jupiter/tokens`);
        const data = await response.json();
        if (data.success) {
            setTokens(data.tokens);
            // Set defaults: SOL → USDC
            const sol = data.tokens.find(t => t.symbol === 'SOL');
            const usdc = data.tokens.find(t => t.symbol === 'USDC');
            setInputToken(sol);
            setOutputToken(usdc);
        }
    };

    const getQuote = async () => {
        if (!inputToken || !outputToken || !inputAmount) return;

        setLoading(true);
        try {
            const amount = parseFloat(inputAmount) * Math.pow(10, inputToken.decimals);
            const response = await fetch(
                `${import.meta.env.VITE_API_URL}/api/jupiter/quote?` +
                `input_mint=${inputToken.address}&` +
                `output_mint=${outputToken.address}&` +
                `amount=${Math.floor(amount)}&` +
                `slippage_bps=50`
            );
            const data = await response.json();
            if (data.success) {
                setQuote(data.quote);
            }
        } finally {
            setLoading(false);
        }
    };

    const executeSwap = async () => {
        if (!publicKey || !inputToken || !outputToken || !inputAmount) return;

        setLoading(true);
        try {
            const amount = parseFloat(inputAmount) * Math.pow(10, inputToken.decimals);
            const response = await fetch(
                `${import.meta.env.VITE_API_URL}/api/jupiter/swap`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        input_mint: inputToken.address,
                        output_mint: outputToken.address,
                        amount: Math.floor(amount),
                        slippage_bps: 50
                    })
                }
            );
            const data = await response.json();
            if (data.success) {
                alert(`Swap executed! Signature: ${data.signature}`);
                setInputAmount('');
                setQuote(null);
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-[#0a0a0f] via-[#16102e] to-[#0a0a0f] text-white p-8">
            <div className="max-w-2xl mx-auto">
                {/* Header */}
                <motion.div
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="text-center mb-8"
                >
                    <div className="inline-flex items-center gap-3 mb-4">
                        <Zap className="w-10 h-10 text-cyan-400" />
                        <h1 className="text-5xl font-bold bg-gradient-to-r from-cyan-400 via-blue-300 to-purple-500 bg-clip-text text-transparent">
                            Jupiter Swap
                        </h1>
                    </div>
                    <p className="text-xl text-gray-400">
                        Best prices across all Solana DEXs
                    </p>
                </motion.div>

                {/* Wallet Connection */}
                {!publicKey && (
                    <div className="mb-8 text-center">
                        <WalletMultiButton />
                    </div>
                )}

                {/* Swap Interface */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="bg-gradient-to-br from-cyan-900/20 via-blue-800/20 to-purple-900/20 backdrop-blur-xl border border-cyan-500/30 rounded-2xl p-8"
                >
                    {/* Input Token */}
                    <div className="mb-4">
                        <label className="block text-sm text-gray-400 mb-2">You Pay</label>
                        <div className="flex gap-4">
                            <select
                                value={inputToken?.address || ''}
                                onChange={(e) => {
                                    const token = tokens.find(t => t.address === e.target.value);
                                    setInputToken(token || null);
                                }}
                                className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white"
                            >
                                {tokens.map(token => (
                                    <option key={token.address} value={token.address}>
                                        {token.symbol}
                                    </option>
                                ))}
                            </select>
                            <input
                                type="number"
                                value={inputAmount}
                                onChange={(e) => setInputAmount(e.target.value)}
                                onBlur={getQuote}
                                placeholder="0.00"
                                className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white text-right"
                            />
                        </div>
                    </div>

                    {/* Swap Arrow */}
                    <div className="flex justify-center my-4">
                        <button
                            onClick={() => {
                                const temp = inputToken;
                                setInputToken(outputToken);
                                setOutputToken(temp);
                            }}
                            className="p-2 bg-cyan-600 hover:bg-cyan-700 rounded-full transition-all"
                        >
                            <ArrowDownUp className="w-6 h-6" />
                        </button>
                    </div>

                    {/* Output Token */}
                    <div className="mb-6">
                        <label className="block text-sm text-gray-400 mb-2">You Receive</label>
                        <div className="flex gap-4">
                            <select
                                value={outputToken?.address || ''}
                                onChange={(e) => {
                                    const token = tokens.find(t => t.address === e.target.value);
                                    setOutputToken(token || null);
                                }}
                                className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white"
                            >
                                {tokens.map(token => (
                                    <option key={token.address} value={token.address}>
                                        {token.symbol}
                                    </option>
                                ))}
                            </select>
                            <div className="flex-1 px-4 py-3 bg-gray-800/50 border border-gray-700 rounded-lg text-white text-right">
                                {quote ? (
                                    (parseInt(quote.outAmount) / Math.pow(10, outputToken?.decimals || 6)).toFixed(6)
                                ) : (
                                    '0.00'
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Quote Info */}
                    {quote && (
                        <div className="mb-6 p-4 bg-cyan-500/10 border border-cyan-500/30 rounded-lg space-y-2 text-sm">
                            <div className="flex justify-between">
                                <span className="text-gray-400">Price Impact</span>
                                <span className={quote.priceImpactPct > 1 ? 'text-red-400' : 'text-green-400'}>
                                    {quote.priceImpactPct.toFixed(2)}%
                                </span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-400">Route</span>
                                <span className="text-cyan-300">
                                    {quote.routePlan.length} hop{quote.routePlan.length > 1 ? 's' : ''}
                                </span>
                            </div>
                        </div>
                    )}

                    {/* Swap Button */}
                    <button
                        onClick={executeSwap}
                        disabled={!publicKey || !quote || loading}
                        className="w-full px-6 py-4 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-700 hover:to-blue-700 rounded-lg text-white font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                        {loading ? (
                            <>
                                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                Processing...
                            </>
                        ) : !publicKey ? (
                            <>
                                <Wallet className="w-5 h-5" />
                                Connect Wallet
                            </>
                        ) : (
                            <>
                                <ArrowDownUp className="w-5 h-5" />
                                Swap
                            </>
                        )}
                    </button>
                </motion.div>

                {/* Powered by Jupiter */}
                <div className="mt-6 text-center text-sm text-gray-500">
                    Powered by <span className="text-cyan-400 font-semibold">Jupiter</span>
                    • Best prices guaranteed
                </div>
            </div>
        </div>
    );
};

export default JupiterSwap;
```

**Dependencies** (Frontend):
```bash
cd trading-dashboard
npm install @solana/web3.js @solana/wallet-adapter-react @solana/wallet-adapter-react-ui @solana/wallet-adapter-wallets
```

#### **2.4 Wallet Adapter Setup** (1 day)

**File**: `trading-dashboard/src/contexts/SolanaWalletContext.tsx`

```tsx
import React, { useMemo } from 'react';
import { ConnectionProvider, WalletProvider } from '@solana/wallet-adapter-react';
import { WalletModalProvider } from '@solana/wallet-adapter-react-ui';
import { PhantomWalletAdapter, SolflareWalletAdapter } from '@solana/wallet-adapter-wallets';
import { clusterApiUrl } from '@solana/web3.js';

// Import styles
import '@solana/wallet-adapter-react-ui/styles.css';

export const SolanaWalletProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const endpoint = useMemo(() => clusterApiUrl('mainnet-beta'), []);

    const wallets = useMemo(
        () => [
            new PhantomWalletAdapter(),
            new SolflareWalletAdapter(),
        ],
        []
    );

    return (
        <ConnectionProvider endpoint={endpoint}>
            <WalletProvider wallets={wallets} autoConnect>
                <WalletModalProvider>
                    {children}
                </WalletModalProvider>
            </WalletProvider>
        </ConnectionProvider>
    );
};
```

Update `App.tsx`:
```tsx
import { SolanaWalletProvider } from './contexts/SolanaWalletContext';

<AuthProvider>
    <SolanaWalletProvider>
        {/* ...existing routes... */}
    </SolanaWalletProvider>
</AuthProvider>
```

---

## 💹 **PHASE 3: DRIFT (SOLANA) - PERPETUAL TRADING**

### **Objective**: Add Solana perpetual futures via Drift Protocol

### **Implementation Plan** (1 week)

#### **3.1 Backend: Drift Client** (3 days)

**File**: `cloud_trader/drift_client.py`

```python
"""
Drift Protocol Integration for Solana Perpetuals Trading
Documentation: https://docs.drift.trade
"""

import asyncio
from typing import Dict, Any, Optional, List
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from anchorpy import Provider, Wallet
from drift import DriftClient, MarketType, OrderType, OrderParams, PositionDirection

DRIFT_PROGRAM_ID = "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH"

class DriftTradingClient:
    """
    Drift Protocol client for perpetual futures trading on Solana.

    Features:
    - Perpetual position management
    - Spot trading
    - Order placement (market, limit, trigger)
    - Real-time position tracking
    """

    def __init__(
        self,
        keypair: Keypair,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        env: str = "mainnet-beta"
    ):
        """Initialize Drift client."""
        self.connection = AsyncClient(rpc_url, commitment=Confirmed)
        self.wallet = Wallet(keypair)
        self.provider = Provider(self.connection, self.wallet)

        self.drift_client = DriftClient(
            connection=self.connection,
            wallet=self.wallet,
            env=env,
            program_id=DRIFT_PROGRAM_ID
        )

    async def initialize(self):
        """Subscribe to Drift accounts."""
        await self.drift_client.subscribe()

    async def open_perp_position(
        self,
        market_index: int,
        direction: str,  # "LONG" or "SHORT"
        size: float,  # in base asset
        leverage: int = 1,
        reduce_only: bool = False
    ) -> Dict[str, Any]:
        """
        Open a perpetual position.

        Args:
            market_index: Market index (0=SOL-PERP, 1=BTC-PERP, 2=ETH-PERP, etc.)
            direction: "LONG" or "SHORT"
            size: Position size in base asset
            leverage: Leverage multiplier
            reduce_only: Whether this is a reduce-only order
        """
        perp_direction = (
            PositionDirection.Long()
            if direction == "LONG"
            else PositionDirection.Short()
        )

        order_params = OrderParams(
            order_type=OrderType.Market(),
            market_type=MarketType.Perp(),
            direction=perp_direction,
            user_order_id=0,
            base_asset_amount=int(size * 1e9),  # Convert to base units
            market_index=market_index,
            reduce_only=reduce_only
        )

        tx_sig = await self.drift_client.place_perp_order(order_params)

        return {
            "signature": str(tx_sig),
            "market_index": market_index,
            "direction": direction,
            "size": size,
            "leverage": leverage
        }

    async def close_perp_position(
        self,
        market_index: int
    ) -> Dict[str, Any]:
        """Close all positions in a perp market."""
        # Get current position
        position = self.drift_client.get_perp_position(market_index)

        if position is None or position.base_asset_amount == 0:
            return {"success": False, "message": "No position to close"}

        # Determine opposite direction
        direction = (
            PositionDirection.Short()
            if position.base_asset_amount > 0
            else PositionDirection.Long()
        )

        order_params = OrderParams(
            order_type=OrderType.Market(),
            market_type=MarketType.Perp(),
            direction=direction,
            user_order_id=0,
            base_asset_amount=abs(position.base_asset_amount),
            market_index=market_index,
            reduce_only=True
        )

        tx_sig = await self.drift_client.place_perp_order(order_params)

        return {
            "signature": str(tx_sig),
            "market_index": market_index,
            "closed_size": abs(position.base_asset_amount) / 1e9
        }

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open perpetual positions."""
        user = self.drift_client.get_user()
        positions = []

        for position in user.get_perp_positions():
            if position.base_asset_amount != 0:
                market_index = position.market_index
                unrealized_pnl = self.drift_client.get_perp_position_unrealized_pnl(
                    market_index
                )

                positions.append({
                    "market_index": market_index,
                    "base_amount": position.base_asset_amount / 1e9,
                    "quote_amount": position.quote_asset_amount / 1e6,
                    "entry_price": position.quote_entry_amount / position.base_entry_amount if position.base_entry_amount != 0 else 0,
                    "unrealized_pnl": unrealized_pnl / 1e6,
                    "leverage": position.leverage / 1e4
                })

        return positions

    async def close(self):
        """Clean shutdown."""
        await self.drift_client.unsubscribe()
        await self.connection.close()

```

**Dependencies**:
```bash
pip install driftpy anchorpy solders solana
```

#### **3.2 Backend: Drift API Endpoints** (1 day)

**File**: `cloud_trader/api.py` (add section)

```python
# ===================================================================
# DRIFT (SOLANA) PERPETUAL TRADING ENDPOINTS
# ===================================================================

@app.post("/api/drift/position/open")
async def open_drift_position(request: Request) -> Dict[str, Any]:
    """
    Open Drift perpetual position.

    Body:
    {
        "market_index": 0,  // 0=SOL, 1=BTC, 2=ETH
        "direction": "LONG",
        "size": 1.0,
        "leverage": 5
    }
    """
    try:
        from .drift_client import get_drift_client

        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        body = await request.json()
        market_index = int(body.get("market_index"))
        direction = body.get("direction")
        size = float(body.get("size"))
        leverage = int(body.get("leverage", 1))

        client = get_drift_client(uid)
        result = await client.open_perp_position(
            market_index=market_index,
            direction=direction,
            size=size,
            leverage=leverage
        )

        logger.info(f"Drift position opened by {uid}: {result['signature']}")

        return {
            "success": True,
            "position": result,
            "message": f"Opened {direction} position"
        }
    except Exception as e:
        logger.error(f"Drift position failed: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/drift/positions")
async def get_drift_positions(request: Request) -> Dict[str, Any]:
    """Get all open Drift positions."""
    try:
        from .drift_client import get_drift_client

        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")

        client = get_drift_client(uid)
        positions = await client.get_positions()

        return {
            "success": True,
            "positions": positions,
            "count": len(positions)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

#### **3.3 Frontend: Drift Trading UI** (2 days)

**File**: `trading-dashboard/src/pages/DriftPerps.tsx`

Similar structure to `JupiterSwap.tsx` but with:
- Market selection (SOL-PERP, BTC-PERP, ETH-PERP)
- Long/Short toggle
- Leverage slider (1-10x)
- Position size input
- Current positions table
- PnL display
- Close position buttons

---

## 🎨 **PHASE 4: UNIFIED MULTI-CHAIN DASHBOARD**

### **Implementation Plan** (3 days)

#### **4.1 Multi-Chain Navigation**

**File**: `trading-dashboard/src/layouts/MasterLayout.tsx`

Add chain switcher:
```tsx
const [activeChain, setActiveChain] = useState<'monad' | 'solana'>('monad');

<div className="flex gap-2">
    <button
        onClick={() => setActiveChain('monad')}
        className={activeChain === 'monad' ? 'active' : ''}
    >
        Monad (Symphony)
    </button>
    <button
        onClick={() => setActiveChain('solana')}
        className={activeChain === 'solana' ? 'active' : ''}
    >
        Solana (Jupiter + Drift)
    </button>
</div>
```

#### **4.2 Unified Portfolio View**

**File**: `trading-dashboard/src/pages/MultiChainPortfolio.tsx`

Show consolidated view:
- Total portfolio value (Monad + Solana)
- Open positions across chains
- P&L by chain
- Recent activity feed
- Asset allocation chart

#### **4.3 Cross-Chain Analytics**

**File**: `trading-dashboard/src/components/CrossChainAnalytics.tsx`

Features:
- Chain performance comparison
- Volume distribution
- Fee analysis
- Best execution routes

---

## 🔐 **PHASE 5: WALLET & SECURITY MANAGEMENT**

### **Implementation Plan** (2 days)

#### **5.1 Solana Wallet Management**

**File**: `cloud_trader/solana_wallet_manager.py`

```python
"""
Secure Solana wallet management for users.
Stores encrypted private keys in Firestore.
"""

import os
from typing import Optional
from solders.keypair import Keypair
from google.cloud import firestore
from cryptography.fernet import Fernet

class SolanaWalletManager:
    """Manage user Solana wallets securely."""

    def __init__(self):
        self.db = firestore.Client()
        self.cipher = Fernet(os.getenv("WALLET_ENCRYPTION_KEY").encode())

    def create_wallet(self, user_id: str) -> str:
        """Create new Solana wallet for user."""
        keypair = Keypair()

        # Encrypt private key
        encrypted_key = self.cipher.encrypt(bytes(keypair))

        # Store in Firestore
        self.db.collection('solana_wallets').document(user_id).set({
            'public_key': str(keypair.pubkey()),
            'encrypted_private_key': encrypted_key,
            'created_at': firestore.SERVER_TIMESTAMP
        })

        return str(keypair.pubkey())

    def get_keypair(self, user_id: str) -> Keypair:
        """Retrieve user's Solana keypair."""
        doc = self.db.collection('solana_wallets').document(user_id).get()

        if not doc.exists:
            raise ValueError(f"No wallet found for user {user_id}")

        encrypted_key = doc.to_dict()['encrypted_private_key']
        decrypted_key = self.cipher.decrypt(encrypted_key)

        return Keypair.from_bytes(decrypted_key)
```

#### **5.2 Multi-Sig Support** (Optional, advanced)

For institutional users, implement multi-sig wallets on Solana using Squads Protocol.

---

## 📊 **PHASE 6: TESTING & DEPLOYMENT**

### **6.1 Testing Strategy** (1 week)

**Unit Tests**:
```bash
# Backend
pytest cloud_trader/tests/

# Test coverage for:
- symphony_client.py
- jupiter_client.py
- drift_client.py
```

**Integration Tests**:
```bash
# Test end-to-end flows:
1. Symphony MIT activation
2. Jupiter swap SOL → USDC
3. Drift open/close perp position
4. Cross-chain portfolio sync
```

**Frontend Tests**:
```bash
cd trading-dashboard
npm test

# Test:
- Component rendering
- Wallet connection
- API integration
- User flows
```

### **6.2 Deployment Checklist**

**Environment Variables** (Cloud Run):
```bash
SYMPHONY_API_KEY=sk_live_***
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=***
WALLET_ENCRYPTION_KEY=***
```

**Frontend Deployment**:
```bash
cd trading-dashboard
npm run build
firebase deploy --only hosting
```

**Backend Deployment**:
```bash
gcloud run deploy cloud-trader \
  --source ./cloud_trader \
  --region europe-west1 \
  --memory 2Gi \
  --timeout 300
```

---

## 📈 **SUCCESS METRICS**

**Technical**:
- ✅ 99.9% uptime
- ✅ < 500ms API response time
- ✅ Zero security breaches
- ✅ 100% test coverage on critical paths

**User Experience**:
- ✅ < 3 clicks to execute trade
- ✅ Real-time position updates
- ✅ Mobile-responsive design
- ✅ One-click wallet connection

**Business**:
- ✅ Multi-chain trading support
- ✅ Best execution prices
- ✅ Comprehensive analytics

---

## 🎯 **FINAL DELIVERABLES**

1. **Monad (Symphony)**:
   - ✅ MIT fund activated
   - ✅ Perpetual + spot trading
   - ✅ Real-time status tracking

2. **Solana (Jupiter)**:
   - ✅ Token swap aggregation
   - ✅ Best price routing
   - ✅ Wallet adapter integrated

3. **Solana (Drift)**:
   - ✅ Perpetual futures trading
   - ✅ Position management
   - ✅ Real-time P&L

4. **Platform**:
   - ✅ Unified dashboard
   - ✅ Cross-chain portfolio
   - ✅ Advanced analytics
   - ✅ Secure wallet management

---

## 🚀 **START DATE**: Now
## ⏰ **COMPLETION TARGET**: 2-3 weeks
## ✅ **QUALITY**: World-class, zero mistakes

**Ready to build the future of multi-chain AI trading!** 💎
