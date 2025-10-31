import React, { useState, useEffect } from 'react';

interface PerformanceData {
  timestamp: number;
  balance: number;
  pnl: number;
}

const PerformanceChart: React.FC = () => {
  const [performanceData, setPerformanceData] = useState<PerformanceData[]>([]);
  const [loading, setLoading] = useState(true);

  // Mock performance data - in real implementation, this would come from your backend
  useEffect(() => {
    const generateMockData = () => {
      const data: PerformanceData[] = [];
      const now = Date.now();
      let balance = 1000;

      for (let i = 23; i >= 0; i--) {
        const timestamp = now - (i * 60 * 60 * 1000); // Hourly data for last 24 hours
        const pnlChange = (Math.random() - 0.5) * 20; // Random P&L change
        balance += pnlChange;

        data.push({
          timestamp,
          balance: Math.max(950, balance), // Ensure balance doesn't go too low
          pnl: pnlChange,
        });
      }

      setPerformanceData(data);
      setLoading(false);
    };

    generateMockData();
  }, []);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USDT',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatTime = (timestamp: number) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-slate-200 rounded w-1/3 mb-4"></div>
          <div className="h-64 bg-slate-200 rounded"></div>
        </div>
      </div>
    );
  }

  const maxBalance = Math.max(...performanceData.map(d => d.balance));
  const minBalance = Math.min(...performanceData.map(d => d.balance));
  const range = maxBalance - minBalance;
  const chartHeight = 200;

  // Calculate points for the chart line
  const points = performanceData.map((data, index) => {
    const x = (index / (performanceData.length - 1)) * 100;
    const y = chartHeight - ((data.balance - minBalance) / range) * chartHeight;
    return `${x},${y}`;
  }).join(' ');

  const currentBalance = performanceData[performanceData.length - 1]?.balance || 0;
  const previousBalance = performanceData[performanceData.length - 2]?.balance || currentBalance;
  const changePercent = ((currentBalance - previousBalance) / previousBalance) * 100;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-slate-900">Performance</h3>
          <p className="text-sm text-slate-600">24-hour balance chart</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-slate-900">
            {formatCurrency(currentBalance)}
          </p>
          <p className={`text-sm font-medium ${changePercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="relative mb-4">
        <svg
          width="100%"
          height={chartHeight + 20}
          className="overflow-visible"
        >
          {/* Grid lines */}
          <defs>
            <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
              <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#f1f5f9" strokeWidth="1"/>
            </pattern>
          </defs>
          <rect width="100%" height={chartHeight} fill="url(#grid)" />

          {/* Chart line */}
          <polyline
            fill="none"
            stroke="#3b82f6"
            strokeWidth="2"
            points={points}
          />

          {/* Data points */}
          {performanceData.map((data, index) => {
            const x = (index / (performanceData.length - 1)) * 100;
            const y = chartHeight - ((data.balance - minBalance) / range) * chartHeight;

            return (
              <circle
                key={index}
                cx={`${x}%`}
                cy={y}
                r="3"
                fill="#3b82f6"
                className="hover:r-4 transition-all cursor-pointer"
              />
            );
          })}
        </svg>

        {/* Y-axis labels */}
        <div className="absolute left-0 top-0 h-full flex flex-col justify-between text-xs text-slate-500 -ml-12">
          <span>{formatCurrency(maxBalance)}</span>
          <span>{formatCurrency((maxBalance + minBalance) / 2)}</span>
          <span>{formatCurrency(minBalance)}</span>
        </div>
      </div>

      {/* Time labels */}
      <div className="flex justify-between text-xs text-slate-500">
        <span>{formatTime(performanceData[0]?.timestamp || 0)}</span>
        <span>{formatTime(performanceData[Math.floor(performanceData.length / 2)]?.timestamp || 0)}</span>
        <span>{formatTime(performanceData[performanceData.length - 1]?.timestamp || 0)}</span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mt-6 pt-4 border-t border-slate-200">
        <div className="text-center">
          <p className="text-sm text-slate-600">24h High</p>
          <p className="text-lg font-semibold text-slate-900">{formatCurrency(maxBalance)}</p>
        </div>
        <div className="text-center">
          <p className="text-sm text-slate-600">24h Low</p>
          <p className="text-lg font-semibold text-slate-900">{formatCurrency(minBalance)}</p>
        </div>
        <div className="text-center">
          <p className="text-sm text-slate-600">Change</p>
          <p className={`text-lg font-semibold ${changePercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)}%
          </p>
        </div>
      </div>
    </div>
  );
};

export default PerformanceChart;
