import React, { useState } from 'react';

interface TradeRecord {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  timestamp: string;
  model_used: string;
  confidence: number;
  status: string;
  pnl?: number;
}

interface PerformanceTrendsProps {
  trades: TradeRecord[];
}

const PerformanceTrends: React.FC<PerformanceTrendsProps> = ({ trades }) => {
  const [selectedModels, setSelectedModels] = useState<string[]>(['all']);
  const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d'>('24h');

  // Get unique models
  const models = Array.from(new Set(trades.map(t => t.model_used)));

  // Filter trades by time range
  const now = new Date();
  const timeRanges = {
    '1h': 60 * 60 * 1000,
    '24h': 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000
  };

  const filteredTrades = trades.filter(trade => {
    const tradeTime = new Date(trade.timestamp);
    return (now.getTime() - tradeTime.getTime()) <= timeRanges[timeRange];
  });

  // Calculate cumulative P&L for each model
  const calculateModelPnL = (model: string) => {
    const modelTrades = filteredTrades.filter(t => t.model_used === model && t.pnl !== undefined);
    let cumulative = 0;
    return modelTrades.map(trade => {
      cumulative += trade.pnl!;
      return {
        time: new Date(trade.timestamp),
        pnl: cumulative,
        trade: trade
      };
    });
  };

  const getModelColor = (modelName: string) => {
    const colors = {
      'DeepSeek-Coder-V2': '#10B981', // green
      'Qwen2.5-Coder': '#3B82F6', // blue
      'FinGPT': '#F59E0B', // yellow
      'Phi-3': '#EF4444', // red
    };
    return colors[modelName as keyof typeof colors] || '#6B7280';
  };

  const toggleModel = (model: string) => {
    if (model === 'all') {
      setSelectedModels(['all']);
    } else {
      if (selectedModels.includes('all')) {
        setSelectedModels([model]);
      } else if (selectedModels.includes(model)) {
        const newSelected = selectedModels.filter(m => m !== model);
        setSelectedModels(newSelected.length === 0 ? ['all'] : newSelected);
      } else {
        setSelectedModels([...selectedModels.filter(m => m !== 'all'), model]);
      }
    }
  };

  const maxPnL = Math.max(...filteredTrades.map(t => Math.abs(t.pnl || 0)), 100);
  const chartHeight = 200;
  const chartWidth = 600;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-slate-900">Performance Trends</h2>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <label className="text-sm text-slate-600">Time:</label>
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as '1h' | '24h' | '7d')}
              className="px-2 py-1 border border-slate-300 rounded text-sm"
            >
              <option value="1h">1 Hour</option>
              <option value="24h">24 Hours</option>
              <option value="7d">7 Days</option>
            </select>
          </div>
        </div>
      </div>

      {/* Model Legend */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          onClick={() => toggleModel('all')}
          className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
            selectedModels.includes('all')
              ? 'bg-slate-900 text-white'
              : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
          }`}
        >
          All Models
        </button>
        {models.map(model => (
          <button
            key={model}
            onClick={() => toggleModel(model)}
            className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
              selectedModels.includes(model) || selectedModels.includes('all')
                ? 'text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
            style={{
              backgroundColor: selectedModels.includes(model) || selectedModels.includes('all')
                ? getModelColor(model)
                : undefined
            }}
          >
            {model}
          </button>
        ))}
      </div>

      {/* Chart Area */}
      <div className="relative bg-slate-50 rounded-lg p-4">
        <svg width={chartWidth} height={chartHeight} className="overflow-visible">
          {/* Grid lines */}
          <defs>
            <pattern id="grid" width="50" height="20" patternUnits="userSpaceOnUse">
              <path d="M 50 0 L 0 0 0 20" fill="none" stroke="#E2E8F0" strokeWidth="1"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />

          {/* Zero line */}
          <line
            x1="0"
            y1={chartHeight / 2}
            x2={chartWidth}
            y2={chartHeight / 2}
            stroke="#94A3B8"
            strokeWidth="1"
            strokeDasharray="2,2"
          />

          {/* Y-axis labels */}
          <text x="-10" y={chartHeight / 2 - 5} textAnchor="end" className="text-xs fill-slate-500">$0</text>
          <text x="-10" y="15" textAnchor="end" className="text-xs fill-green-600">+${maxPnL.toFixed(0)}</text>
          <text x="-10" y={chartHeight - 5} textAnchor="end" className="text-xs fill-red-600">-${maxPnL.toFixed(0)}</text>

          {/* Plot lines for each selected model */}
          {models.map(model => {
            if (!selectedModels.includes('all') && !selectedModels.includes(model)) return null;

            const pnlData = calculateModelPnL(model);
            if (pnlData.length === 0) return null;

            const points = pnlData.map((point, index) => {
              const x = (index / Math.max(pnlData.length - 1, 1)) * chartWidth;
              const y = chartHeight / 2 - (point.pnl / maxPnL) * (chartHeight / 2);
              return `${x},${y}`;
            }).join(' ');

            return (
              <g key={model}>
                {/* Line */}
                <polyline
                  points={points}
                  fill="none"
                  stroke={getModelColor(model)}
                  strokeWidth="2"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />

                {/* Data points */}
                {pnlData.map((point, index) => {
                  const x = (index / Math.max(pnlData.length - 1, 1)) * chartWidth;
                  const y = chartHeight / 2 - (point.pnl / maxPnL) * (chartHeight / 2);

                  return (
                    <circle
                      key={index}
                      cx={x}
                      cy={y}
                      r="3"
                      fill={getModelColor(model)}
                      className="hover:r-4 transition-all cursor-pointer"
                    />
                  );
                })}
              </g>
            );
          })}
        </svg>

        {filteredTrades.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center text-slate-500">
              <span className="text-4xl mb-2 block">📈</span>
              <p>No trading data available for the selected time range</p>
            </div>
          </div>
        )}
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-6">
        {models.map(model => {
          const modelTrades = filteredTrades.filter(t => t.model_used === model);
          const totalPnL = modelTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
          const winRate = modelTrades.length > 0
            ? modelTrades.filter(t => (t.pnl || 0) > 0).length / modelTrades.length
            : 0;

          return (
            <div key={model} className="bg-slate-50 rounded-lg p-3">
              <div className="flex items-center space-x-2 mb-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: getModelColor(model) }}
                ></div>
                <span className="text-sm font-medium text-slate-700 truncate">{model}</span>
              </div>
              <div className="space-y-1">
                <div className="text-xs text-slate-500">Trades: {modelTrades.length}</div>
                <div className={`text-sm font-medium ${totalPnL >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  P&L: ${totalPnL.toFixed(2)}
                </div>
                <div className="text-xs text-slate-500">
                  Win Rate: {(winRate * 100).toFixed(1)}%
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PerformanceTrends;
