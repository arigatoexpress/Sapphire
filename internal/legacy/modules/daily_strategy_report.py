"""Automated daily strategy performance report with charts."""

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend for server use
import io
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


async def generate_daily_report(trading_service) -> bytes:
    """Generate daily strategy report with charts."""

    try:
        # Gather data from trading service
        agents = (
            trading_service._serialize_agents()
            if hasattr(trading_service, "_serialize_agents")
            else []
        )

        if not agents:
            logger.warning("No agent data available for daily report")
            return b""

        # Create figure with subplots
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        fig.suptitle(
            f'Sapphire AI Daily Report - {datetime.utcnow().strftime("%Y-%m-%d")}', fontsize=16
        )

        # Plot 1: Agent P&L comparison
        agent_names = [a.get("id", "unknown")[:15] for a in agents]
        agent_pnls = [a.get("total_pnl", 0) for a in agents]
        colors = ["green" if pnl >= 0 else "red" for pnl in agent_pnls]
        axes[0, 0].barh(agent_names, agent_pnls, color=colors)
        axes[0, 0].set_title("Agent P&L (USD)")
        axes[0, 0].set_xlabel("P&L ($)")
        axes[0, 0].axvline(x=0, color="black", linestyle="--", linewidth=0.5)

        # Plot 2: Win rates
        win_rates = [a.get("win_rate", 0) * 100 if a.get("win_rate") else 50 for a in agents]
        axes[0, 1].barh(agent_names, win_rates, color="skyblue")
        axes[0, 1].set_title("Agent Win Rates")
        axes[0, 1].set_xlabel("Win Rate (%)")
        axes[0, 1].axvline(x=50, color="black", linestyle="--", linewidth=0.5)
        axes[0, 1].set_xlim(0, 100)

        # Plot 3: Trade counts
        trade_counts = [a.get("total_trades", 0) for a in agents]
        axes[1, 0].barh(agent_names, trade_counts, color="orange")
        axes[1, 0].set_title("Total Trades")
        axes[1, 0].set_xlabel("Trade Count")

        # Plot 4: Active positions
        active_positions = [len(a.get("open_positions", {})) for a in agents]
        axes[1, 1].barh(agent_names, active_positions, color="purple")
        axes[1, 1].set_title("Active Positions")
        axes[1, 1].set_xlabel("Position Count")

        plt.tight_layout()

        # Save to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        plt.close()

        return buf.getvalue()

    except Exception as e:
        logger.error(f"Failed to generate daily report: {e}")
        return b""


async def send_daily_report_to_telegram(telegram_service, trading_service):
    """Send daily report via Telegram with charts."""

    try:
        chart_image = await generate_daily_report(trading_service)

        if not chart_image:
            logger.warning("No chart image generated, skipping Telegram report")
            return

        # Generate text summary
        agents = (
            trading_service._serialize_agents()
            if hasattr(trading_service, "_serialize_agents")
            else []
        )
        total_pnl = sum(a.get("total_pnl", 0) for a in agents)
        total_trades = sum(a.get("total_trades", 0) for a in agents)

        # Find top performer
        top_agent = (
            max(agents, key=lambda a: a.get("total_pnl", 0))
            if agents
            else {"id": "none", "total_pnl": 0}
        )

        caption = f"""📊 *Sapphire AI Daily Report*

💰 Total P&L: ${total_pnl:.2f}
📈 Total Trades: {total_trades}
🤖 Active Agents: {len(agents)}
⚡ Grok Overrides: {getattr(trading_service, '_grok', {'override_count': 0}).override_count if hasattr(trading_service, '_grok') else 0}

🏆 Top Performer: {top_agent['id']} (${top_agent.get('total_pnl', 0):.2f})

_Report generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_
"""

        await telegram_service.send_photo(photo=chart_image, caption=caption)

        logger.info("✅ Daily report sent to Telegram")

    except Exception as e:
        logger.error(f"Failed to send daily report: {e}")
