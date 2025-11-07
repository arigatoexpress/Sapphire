import React, { useState, useEffect, useMemo } from 'react';
import { fetchAgentPerformance, fetchTradeHistory } from '../api/client';
import { DashboardAgent } from '../api/client';

interface HistoricalPerformanceProps {
  agent: DashboardAgent;
  onClose: () => void;
}

interface PerformanceData {
  timestamp: string;
  equity: number;
  total_trades: number;
  total_pnl: number;
  exposure: number;
  win_rate: number | null;
  active_positions: number;
}

const HistoricalPerformance: React.FC<HistoricalPerformanceProps> = ({ agent, onClose }) => {
  const [performanceData, setPerformanceData] = useState<PerformanceData[]>([]);
  const [tradeHistory, setTradeHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<'24h' | '7d' | '30d' | 'all'>('7d');
  const [activeTab, setActiveTab] = useState<'performance' | 'trades'>('performance');

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const endDate = new Date().toISOString();
        let startDate: string | undefined;
        
        if (timeRange === '24h') {
          startDate = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
        } else if (timeRange === '7d') {
          startDate = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
        } else if (timeRange === '30d') {
          startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
        }

        const [perfResult, tradesResult] = await Promise.all([
          fetchAgentPerformance(agent.id, startDate, endDate, 1000),
          fetchTradeHistory(agent.id, undefined, startDate, endDate, 500),
        ]);

        setPerformanceData(perfResult.performance || []);
        setTradeHistory(tradesResult.trades || []);
      } catch (err) {
        console.error('Failed to load historical data:', err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [agent.id, timeRange]);

  const chartData = useMemo(() => {
    if (!performanceData.length) return [];
    
    return performanceData.map(p => ({
      timestamp: new Date(p.timestamp).getTime(),
      equity: p.equity,
      pnl: p.total_pnl,
      winRate: p.win_rate || 0,
    })).sort((a, b) => a.timestamp - b.timestamp);
  }, [performanceData]);

  const maxEquity = Math.max(...chartData.map(d => d.equity), 1);
  const minEquity = Math.min(...chartData.map(d => d.equity), 0);
  const range = maxEquity - minEquity || 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="relative w-full max-w-6xl max-h-[90vh] bg-brand-abyss border border-brand-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-brand-border">
          <div>
            <h2 className="text-2xl font-bold text-brand-ice">{agent.name} - Historical Performance</h2>
            <p className="text-sm text-brand-muted mt-1">{agent.model}</p>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-brand-ice hover:text-red-400 transition-colors"
          >
            ✕ Close
          </button>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between p-4 border-b border-brand-border bg-brand-abyss/50">
          <div className="flex gap-2">
            {(['24h', '7d', '30d', 'all'] as const).map(range => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  timeRange === range
                    ? 'bg-brand-accent-blue text-white'
                    : 'bg-brand-border/30 text-brand-ice hover:bg-brand-border/50'
                }`}
              >
                {range === 'all' ? 'All Time' : range}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab('performance')}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                activeTab === 'performance'
                  ? 'bg-brand-accent-blue text-white'
                  : 'bg-brand-border/30 text-brand-ice hover:bg-brand-border/50'
              }`}
            >
              Performance
            </button>
            <button
              onClick={() => setActiveTab('trades')}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                activeTab === 'trades'
                  ? 'bg-brand-accent-blue text-white'
                  : 'bg-brand-border/30 text-brand-ice hover:bg-brand-border/50'
              }`}
            >
              Trades ({tradeHistory.length})
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-200px)]">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-brand-accent-blue"></div>
            </div>
          ) : activeTab === 'performance' ? (
            <div className="space-y-6">
              {/* Equity Chart */}
              <div className="bg-brand-abyss/70 rounded-xl p-6 border border-brand-border">
                <h3 className="text-lg font-semibold text-brand-ice mb-4">Equity Curve</h3>
                <div className="h-64 relative">
                  {chartData.length > 0 ? (
                    <svg className="w-full h-full" viewBox={`0 0 ${chartData.length * 2} 200`} preserveAspectRatio="none">
                      <polyline
                        fill="none"
                        stroke="rgb(56, 189, 248)"
                        strokeWidth="2"
                        points={chartData.map((d, i) => `${i * 2},${200 - ((d.equity - minEquity) / range) * 200}`).join(' ')}
                      />
                    </svg>
                  ) : (
                    <div className="flex items-center justify-center h-full text-brand-muted">
                      No performance data available
                    </div>
                  )}
                </div>
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-brand-abyss/70 rounded-xl p-4 border border-brand-border">
                  <div className="text-sm text-brand-muted">Total P&L</div>
                  <div className={`text-2xl font-bold mt-1 ${
                    performanceData[performanceData.length - 1]?.total_pnl >= 0
                      ? 'text-green-400'
                      : 'text-red-400'
                  }`}>
                    ${performanceData[performanceData.length - 1]?.total_pnl.toFixed(2) || '0.00'}
                  </div>
                </div>
                <div className="bg-brand-abyss/70 rounded-xl p-4 border border-brand-border">
                  <div className="text-sm text-brand-muted">Total Trades</div>
                  <div className="text-2xl font-bold mt-1 text-brand-ice">
                    {performanceData[performanceData.length - 1]?.total_trades || 0}
                  </div>
                </div>
                <div className="bg-brand-abyss/70 rounded-xl p-4 border border-brand-border">
                  <div className="text-sm text-brand-muted">Win Rate</div>
                  <div className="text-2xl font-bold mt-1 text-brand-ice">
                    {performanceData[performanceData.length - 1]?.win_rate?.toFixed(1) || '0.0'}%
                  </div>
                </div>
                <div className="bg-brand-abyss/70 rounded-xl p-4 border border-brand-border">
                  <div className="text-sm text-brand-muted">Current Equity</div>
                  <div className="text-2xl font-bold mt-1 text-brand-ice">
                    ${performanceData[performanceData.length - 1]?.equity.toFixed(2) || '0.00'}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {tradeHistory.length > 0 ? (
                tradeHistory.map((trade, idx) => (
                  <div
                    key={idx}
                    className="bg-brand-abyss/70 rounded-lg p-4 border border-brand-border hover:border-brand-accent-blue/50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                          trade.side === 'BUY'
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-red-500/20 text-red-400'
                        }`}>
                          {trade.side}
                        </span>
                        <span className="text-brand-ice font-medium">{trade.symbol}</span>
                        <span className="text-brand-muted text-sm">
                          {new Date(trade.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <div className="flex items-center gap-6 text-sm">
                        <div>
                          <span className="text-brand-muted">Price: </span>
                          <span className="text-brand-ice">${trade.price.toFixed(4)}</span>
                        </div>
                        <div>
                          <span className="text-brand-muted">Qty: </span>
                          <span className="text-brand-ice">{trade.quantity.toFixed(6)}</span>
                        </div>
                        <div>
                          <span className="text-brand-muted">Notional: </span>
                          <span className="text-brand-ice">${trade.notional.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-12 text-brand-muted">
                  No trades found for this period
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default HistoricalPerformance;

