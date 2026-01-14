import React from 'react';
import { Box, Tooltip, Typography } from '@mui/material';

interface Trade {
  bot_id: string;
  bot_name: string;
  bot_emoji: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  price: number;
  quantity: number;
  pnl?: number;
  timestamp: number;
}

interface BotTradeMarkersProps {
  trades: Trade[];
  chartWidth: number;
  chartHeight: number;
  priceRange: { min: number; max: number };
  timeRange: { start: number; end: number };
}

const BOT_COLORS: Record<string, string> = {
  'trend-momentum-agent': '#2196F3',
  'strategy-optimization-agent': '#4CAF50',
  'financial-sentiment-agent': '#FF9800',
  'market-prediction-agent': '#9C27B0',
  'volume-microstructure-agent': '#F44336',
  'vpin-hft': '#00BCD4',
};

export const BotTradeMarkers: React.FC<BotTradeMarkersProps> = ({
  trades,
  chartWidth,
  chartHeight,
  priceRange,
  timeRange,
}) => {
  const calculatePosition = (trade: Trade) => {
    // Calculate X position based on time
    const timePercent = (trade.timestamp - timeRange.start) / (timeRange.end - timeRange.start);
    const x = timePercent * chartWidth;

    // Calculate Y position based on price
    const pricePercent = (trade.price - priceRange.min) / (priceRange.max - priceRange.min);
    const y = chartHeight - (pricePercent * chartHeight);

    return { x, y };
  };

  return (
    <svg
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: chartWidth,
        height: chartHeight,
        pointerEvents: 'none',
      }}
    >
      {trades.map((trade, index) => {
        const { x, y } = calculatePosition(trade);
        const botColor = BOT_COLORS[trade.bot_id] || '#ffffff';
        const isBuy = trade.side === 'BUY';

        return (
          <g key={`${trade.bot_id}-${index}`} style={{ pointerEvents: 'all' }}>
            {/* Trade Marker */}
            {isBuy ? (
              // Buy = Triangle pointing up
              <polygon
                points={`${x},${y} ${x-8},${y+12} ${x+8},${y+12}`}
                fill={botColor}
                stroke="#fff"
                strokeWidth="1"
                opacity="0.9"
              />
            ) : (
              // Sell = Triangle pointing down
              <polygon
                points={`${x},${y} ${x-8},${y-12} ${x+8},${y-12}`}
                fill={botColor}
                stroke="#fff"
                strokeWidth="1"
                opacity="0.9"
              />
            )}

            {/* Bot Emoji */}
            <text
              x={x}
              y={isBuy ? y + 22 : y - 14}
              textAnchor="middle"
              fontSize="12"
              fontWeight="bold"
            >
              {trade.bot_emoji}
            </text>

            {/* Hover tooltip data */}
            <title>
              {`${trade.bot_emoji} ${trade.bot_name}\n` +
               `${trade.side} ${trade.symbol}\n` +
               `Price: $${trade.price.toFixed(2)}\n` +
               `Size: ${trade.quantity}\n` +
               `Time: ${new Date(trade.timestamp * 1000).toLocaleString()}\n` +
               (trade.pnl !== undefined ? `P&L: $${trade.pnl.toFixed(2)}` : '')}
            </title>
          </g>
        );
      })}
    </svg>
  );
};

export default BotTradeMarkers;
