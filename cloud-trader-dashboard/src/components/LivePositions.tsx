import React, { useState } from 'react';

interface Position {
  symbol: string;
  side: string;
  size: number;
  entry_price: number;
  current_price: number;
  pnl: number;
  pnl_percent: number;
  leverage: number;
  model_used: string;
  timestamp: string;
}

interface LivePositionsProps {
  positions: Position[];
}

const LivePositions: React.FC<LivePositionsProps> = ({ positions }) => {
  const [sortBy, setSortBy] = useState<'pnl' | 'symbol' | 'size'>('pnl');
  const [filterModel, setFilterModel] = useState<string>('all');
  const getModelIcon = (modelName: string) => {
    const icons: { [key: string]: string } = {
      'DeepSeek-Coder-V2': '🧠',
      'Qwen2.5-Coder': '🧮',
      'FinGPT': '💰',
      'Phi-3': '🔬'
    };
    return icons[modelName] || '🤖';
  };

  const getPositionColor = (side: string) => {
    return side.toLowerCase() === 'long' ? 'text-green-600' : 'text-red-600';
  };

  const getPnLColor = (pnl: number) => {
    return pnl >= 0 ? 'text-green-600' : 'text-red-600';
  };

  const getPnLBgColor = (pnl: number) => {
    return pnl >= 0 ? 'bg-green-50' : 'bg-red-50';
  };

  // Filter and sort positions
  const filteredPositions = positions.filter(pos =>
    filterModel === 'all' || pos.model_used === filterModel
  );

  const sortedPositions = [...filteredPositions].sort((a, b) => {
    switch (sortBy) {
      case 'pnl':
        return b.pnl - a.pnl;
      case 'symbol':
        return a.symbol.localeCompare(b.symbol);
      case 'size':
        return b.size - a.size;
      default:
        return 0;
    }
  });

  const totalPnL = positions.reduce((sum, pos) => sum + pos.pnl, 0);
  const totalExposure = positions.reduce((sum, pos) => sum + (pos.size * pos.entry_price), 0);

  const uniqueModels = Array.from(new Set(positions.map(p => p.model_used)));

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600">Total Positions</p>
              <p className="text-2xl font-bold text-slate-900">{positions.length}</p>
            </div>
            <span className="text-2xl">📊</span>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600">Total P&L</p>
              <p className={`text-2xl font-bold ${getPnLColor(totalPnL)}`}>
                ${totalPnL.toFixed(2)}
              </p>
            </div>
            <span className={`text-2xl ${totalPnL >= 0 ? 'filter hue-rotate-120' : ''}`}>💰</span>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-600">Total Exposure</p>
              <p className="text-2xl font-bold text-slate-900">${totalExposure.toFixed(2)}</p>
            </div>
            <span className="text-2xl">📈</span>
          </div>
        </div>
      </div>

      {/* Filters and Controls */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-4">
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
          <div className="flex items-center space-x-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Sort by:</label>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'pnl' | 'symbol' | 'size')}
                className="px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="pnl">P&L</option>
                <option value="symbol">Symbol</option>
                <option value="size">Size</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Filter Model:</label>
              <select
                value={filterModel}
                onChange={(e) => setFilterModel(e.target.value)}
                className="px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="all">All Models</option>
                {uniqueModels.map(model => (
                  <option key={model} value={model}>{model}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="text-sm text-slate-600">
            Showing {sortedPositions.length} of {positions.length} positions
          </div>
        </div>
      </div>

      {/* Positions Table */}
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="text-xl font-semibold text-slate-900">Live Positions</h2>
        </div>

        {sortedPositions.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            <span className="text-4xl mb-2 block">📊</span>
            <p>No active positions</p>
            <p className="text-sm">Positions will appear here when trades are executed</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Symbol & Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Side
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Size
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Entry Price
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Current Price
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    P&L
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Leverage
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                    Last Update
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-slate-200">
                {sortedPositions.map((position, index) => (
                  <tr key={index} className={`${getPnLBgColor(position.pnl)} hover:bg-slate-50`}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <span className="text-lg mr-2">{getModelIcon(position.model_used)}</span>
                        <div>
                          <div className="text-sm font-medium text-slate-900">{position.symbol}</div>
                          <div className="text-xs text-slate-500">{position.model_used}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getPositionColor(position.side)} bg-current bg-opacity-10`}>
                        {position.side.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900">
                      {position.size.toFixed(4)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900">
                      ${position.entry_price.toFixed(2)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900">
                      ${position.current_price.toFixed(2)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className={`text-sm font-medium ${getPnLColor(position.pnl)}`}>
                        ${position.pnl.toFixed(2)}
                      </div>
                      <div className={`text-xs ${getPnLColor(position.pnl_percent)}`}>
                        ({position.pnl_percent >= 0 ? '+' : ''}{position.pnl_percent.toFixed(2)}%)
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-900">
                      {position.leverage}x
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                      {new Date(position.timestamp).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default LivePositions;
