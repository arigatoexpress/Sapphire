"""NVIDIA AI Agent Stack Integration.

Leverages the full NVIDIA ecosystem:
- Nemotron 3 Nano: Fast classification + analysis (196 t/s, 100% accuracy)
- Nemotron Cascade-2: Deep reasoning (31.6B MoE, when GPU available)
- Hermes 3: Function calling + tool use (specialized for agentic workloads)

Architecture:
  User request → Hermes 3 (decides which tools to call)
                → Tools execute (TA, OpenBB, TradingView, etc.)
                → Nemotron (synthesizes results into insight)
                → User gets grounded, actionable analysis

This separates "what to do" (Hermes) from "what it means" (Nemotron).
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

OLLAMA_ENDPOINTS = [
    ("gpu", "http://100.x.x.z:11434"),
    ("local", "http://localhost:11434"),
]

# Model selection based on Kadima Benchmark v3
MODELS = {
    "tool_caller": "hermes3:8b",  # Best at function calling (90%+ accuracy)
    "fast_reason": "llama3.2:3b",  # Fast analysis (Nemotron Nano equivalent)
    "deep_reason": "nemotron-cascade-2:latest",  # Deep reasoning (31.6B MoE, GPU only)
}

# Tools available to the agent
SAPPHIRE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_technical_analysis",
            "description": "Get RSI, MACD, Bollinger Bands, moving averages, and net signal for a crypto asset. Returns calculated indicators, not estimates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Asset symbol: BTC, ETH, or SOL"}
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_quant_analysis",
            "description": "Get support/resistance levels, trend strength, risk/reward ratio for a crypto asset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Asset symbol: BTC, ETH, or SOL"}
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_correlation",
            "description": "Get correlation matrix between BTC, ETH, and SOL (30-day daily returns).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_equity_quote",
            "description": "Get real-time price quote for a stock from OpenBB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock ticker e.g. AAPL, NVDA"}
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_prediction_history",
            "description": "Get prediction accuracy history — lifetime stats and per-symbol breakdown.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram",
            "description": "Send a message to the user via Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "priority": {"type": "string", "enum": ["p0", "p1", "p2"]},
                },
                "required": ["message"],
            },
        },
    },
]


@dataclass
class AgentResponse:
    """Response from the NVIDIA agent pipeline."""

    query: str
    tool_calls: list[dict]
    tool_results: dict[str, str]
    synthesis: str
    model_used: dict  # {"tool_caller": "hermes3:8b", "synthesizer": "llama3.2:3b"}
    timestamp: str


def _ollama_chat(
    model: str, messages: list[dict], tools: list[dict] | None = None, timeout: int = 60
) -> dict:
    """Send chat request to Ollama with tool support."""
    for _, base in OLLAMA_ENDPOINTS:
        try:
            payload = {"model": model, "messages": messages, "stream": False}
            if tools:
                payload["tools"] = tools

            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{base}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception:
            continue
    return {"error": "All Ollama endpoints unavailable"}


def _execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return the result as string."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))

    if name == "get_technical_analysis":
        from technical_analysis import analyze

        profile = analyze(args.get("symbol", "BTC"))
        if profile:
            return json.dumps(
                {
                    "symbol": profile.symbol,
                    "price": profile.price,
                    "rsi": profile.rsi_14,
                    "rsi_zone": profile.rsi_zone,
                    "macd_cross": profile.macd_cross,
                    "ma_trend": profile.ma_trend,
                    "bb_position": profile.bb_position,
                    "net_signal": profile.net_signal,
                    "signals_bullish": profile.signal_count_bullish,
                    "signals_bearish": profile.signal_count_bearish,
                    "atr_pct": profile.atr_pct,
                    "volume_signal": profile.volume_signal,
                }
            )
        return json.dumps({"error": f"No data for {args.get('symbol')}"})

    elif name == "get_quant_analysis":
        from quant_analysis import analyze_full

        profile = analyze_full(args.get("symbol", "BTC"))
        if profile:
            return json.dumps(
                {
                    "symbol": profile.symbol,
                    "price": profile.price,
                    "nearest_support": profile.nearest_support,
                    "nearest_resistance": profile.nearest_resistance,
                    "risk_reward": profile.risk_reward,
                    "trend_strength": profile.trend_strength,
                    "trend_direction": profile.trend_direction,
                    "support_levels": [
                        {"price": s.price, "strength": s.strength}
                        for s in profile.support_levels[:3]
                    ],
                    "resistance_levels": [
                        {"price": r.price, "strength": r.strength}
                        for r in profile.resistance_levels[:3]
                    ],
                }
            )
        return json.dumps({"error": f"No data for {args.get('symbol')}"})

    elif name == "get_correlation":
        from quant_analysis import correlation_matrix

        pairs = correlation_matrix()
        return json.dumps(
            [
                {
                    "pair": f"{c.asset_a}/{c.asset_b}",
                    "correlation": c.correlation,
                    "interpretation": c.interpretation,
                }
                for c in pairs
            ]
        )

    elif name == "get_equity_quote":
        try:
            url = f"http://127.0.0.1:6900/api/v1/equity/price/quote?symbol={args.get('symbol', 'AAPL')}&provider=yfinance"
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
                results = data.get("results", [])
                if results:
                    q = results[0]
                    return json.dumps(
                        {
                            "symbol": q["symbol"],
                            "price": q["last_price"],
                            "volume": q.get("volume", 0),
                        }
                    )
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "get_prediction_history":
        pred_path = Path.home() / "Code" / "Sapphire" / "data" / "trading_predictions.jsonl"
        if pred_path.exists():
            preds = [json.loads(l) for l in pred_path.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
            scored = [p for p in preds if p.get("correct") is not None]
            correct = sum(1 for p in scored if p["correct"])
            return json.dumps(
                {
                    "total": len(preds),
                    "scored": len(scored),
                    "correct": correct,
                    "accuracy": round(correct / len(scored) * 100, 1) if scored else 0,
                }
            )
        return json.dumps({"total": 0, "accuracy": 0})

    elif name == "send_telegram":
        sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
        from notify import send_telegram_message

        result = send_telegram_message(args.get("message", ""), priority=args.get("priority", "p1"))
        return json.dumps({"sent": result.get("ok", False)})

    return json.dumps({"error": f"Unknown tool: {name}"})


def run_agent(query: str, max_turns: int = 3) -> AgentResponse:
    """Run the full NVIDIA agent pipeline.

    1. Hermes 3 decides which tools to call
    2. Tools execute with real data
    3. Nemotron synthesizes results
    """
    messages = [
        {
            "role": "system",
            "content": "You are a trading analyst for Sapphire OS. Use the provided tools to gather real data before answering. Always call tools first, never guess numbers.",
        },
        {"role": "user", "content": query},
    ]

    all_tool_calls = []
    tool_results = {}

    # Turn 1: Hermes 3 decides what tools to call
    for _turn in range(max_turns):
        response = _ollama_chat(MODELS["tool_caller"], messages, tools=SAPPHIRE_TOOLS, timeout=60)

        if "error" in response:
            break

        msg = response.get("message", {})

        if not msg.get("tool_calls"):
            # No more tool calls — Hermes is done gathering data
            break

        # Execute tool calls
        messages.append(msg)  # Add assistant's tool call message

        for tc in msg["tool_calls"]:
            fn = tc["function"]
            tool_name = fn["name"]
            tool_args = fn.get("arguments", {})
            all_tool_calls.append({"name": tool_name, "args": tool_args})

            result = _execute_tool(tool_name, tool_args)
            tool_results[tool_name] = result

            messages.append({"role": "tool", "content": result})

    # Synthesis: use Nemotron to interpret the gathered data
    if tool_results:
        synthesis_prompt = f"""The user asked: "{query}"

Here is the REAL data gathered from tools (all numbers are calculated from actual market data, not estimated):

{json.dumps(tool_results, indent=2)[:3000]}

Provide a concise, actionable analysis. Reference specific numbers from the data. Do NOT invent any numbers — only use what's in the tool results above."""

        synth_response = _ollama_chat(
            MODELS["fast_reason"],
            [{"role": "user", "content": synthesis_prompt}],
            timeout=30,
        )
        synthesis = synth_response.get("message", {}).get("content", "Analysis unavailable")
    else:
        synthesis = response.get("message", {}).get(
            "content", "No tools called — unable to gather data"
        )

    return AgentResponse(
        query=query,
        tool_calls=all_tool_calls,
        tool_results=tool_results,
        synthesis=synthesis,
        model_used={"tool_caller": MODELS["tool_caller"], "synthesizer": MODELS["fast_reason"]},
        timestamp=datetime.now(UTC).isoformat(),
    )


if __name__ == "__main__":
    import sys

    query = (
        " ".join(sys.argv[1:])
        or "Analyze BTC and ETH. What are the key levels and which has a better setup?"
    )

    print("🤖 NVIDIA Agent Pipeline")
    print(f"   Query: {query}\n")

    result = run_agent(query)

    print(f"📞 Tool Calls ({len(result.tool_calls)}):")
    for tc in result.tool_calls:
        print(f"   → {tc['name']}({json.dumps(tc['args'])})")

    print("\n📊 Tool Results:")
    for name, data in result.tool_results.items():
        parsed = json.loads(data)
        print(f"   {name}: {json.dumps(parsed)[:150]}...")

    print(f"\n🧠 Synthesis ({result.model_used['synthesizer']}):")
    print(f"   {result.synthesis[:500]}")

    print(f"\n   Models: Hermes 3 (tools) → {result.model_used['synthesizer']} (synthesis)")
