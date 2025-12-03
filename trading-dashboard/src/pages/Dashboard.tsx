import React, { useState, useEffect } from 'react';
import { BotPerformanceBoard } from '../components/BotPerformanceBoard';
import { LiveAgentChat } from '../components/LiveAgentChat';
import { TradeActivityFeed } from '../components/TradeActivityFeed';
import { OpenPositionsTable } from '../components/OpenPositionsTable';
import DiamondSparkle from '../components/DiamondSparkle';
import SapphireDust from '../components/SapphireDust';

interface DashboardProps {
  bots: any[];
  messages: any[];
  trades: any[];
  openPositions?: any[];
  totalValue: number;
  totalPnl: number;
  pnlPercent: number;
}

export const Dashboard: React.FC<DashboardProps> = ({
  bots,
  messages,
  trades,
  openPositions = [],
  totalValue,
  totalPnl,
  pnlPercent
}) => {
  const [showSparkle, setShowSparkle] = useState(false);

  useEffect(() => {
    // Show sparkle effect when P&L changes significantly
    if (Math.abs(totalPnl) > 10 && !showSparkle) {
      setShowSparkle(true);
      const timer = setTimeout(() => setShowSparkle(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [totalPnl, showSparkle]); // Added showSparkle to deps to prevent loop if state setter is stable

  // Memoize SapphireDust to prevent re-renders
  const AnimatedBackground = React.useMemo(() => <SapphireDust />, []);

  return (
    <div className="min-h-screen relative overflow-hidden">
      {/* Animated Background */}
      {AnimatedBackground}

      {/* Sparkle Effect for Big Wins */}
      {showSparkle && totalPnl > 0 && (
        <div className="fixed inset-0 pointer-events-none z-50">
          <DiamondSparkle />
        </div>
      )}

      <div className="relative z-10 space-y-8">
        {/* Ultra-Modern Hero Header - Quantum Glass */}
        <div className="relative group">
          {/* Multi-dimensional Background Effects */}
          <div className="absolute -inset-4 bg-gradient-to-br from-blue-600/15 via-purple-600/20 to-cyan-600/15 rounded-[2rem] blur-2xl opacity-60 group-hover:opacity-80 transition-opacity duration-1000"></div>
          <div className="absolute -inset-2 bg-gradient-to-r from-blue-500/10 via-purple-500/8 to-cyan-500/10 rounded-[1.5rem] blur-xl animate-pulse duration-4000"></div>
          <div className="absolute inset-0 bg-gradient-to-t from-slate-900/90 via-slate-900/70 to-transparent rounded-3xl"></div>

          {/* Animated geometric patterns */}
          <div className="absolute inset-0 opacity-5">
            <div className="absolute top-4 left-4 w-20 h-20 border border-blue-400/30 rounded-full animate-spin duration-10000"></div>
            <div className="absolute top-8 right-8 w-16 h-16 border border-purple-400/30 rounded-full animate-spin duration-8000" style={{ animationDirection: 'reverse' }}></div>
            <div className="absolute bottom-6 left-1/3 w-12 h-12 border border-cyan-400/30 rounded-full animate-spin duration-6000"></div>
          </div>

          <div className="relative backdrop-blur-2xl bg-gradient-to-br from-slate-900/95 via-slate-900/90 to-slate-800/95 rounded-3xl p-8 border border-slate-700/50 shadow-[0_0_100px_-20px_rgba(59,130,246,0.3)] overflow-hidden">
            {/* Animated background pattern */}
            <div className="absolute inset-0 opacity-5">
              <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-cyan-400 to-purple-400 transform rotate-12 scale-150"></div>
            </div>
            <div className="flex items-center justify-between">
              <div className="space-y-6">
                <div className="flex items-center gap-4">
                  <div className="relative group">
                    {/* Multi-layer icon effects */}
                    <div className="absolute -inset-2 bg-gradient-to-br from-blue-500/30 to-purple-500/30 rounded-2xl blur-lg opacity-0 group-hover:opacity-100 transition-all duration-500"></div>
                    <div className="relative w-16 h-16 bg-gradient-to-br from-blue-500/20 via-purple-500/15 to-cyan-500/20 rounded-2xl flex items-center justify-center shadow-2xl border border-slate-600/30 backdrop-blur-sm">
                      <span className="text-4xl filter drop-shadow-xl animate-pulse">💎</span>
                      {/* Inner glow */}
                      <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-blue-400/5 to-purple-400/5 animate-pulse duration-3000"></div>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <h1 className="text-5xl font-black bg-gradient-to-r from-white via-blue-100 via-purple-200 to-cyan-100 bg-clip-text text-transparent tracking-tight">
                      Sapphire Trade
                    </h1>
                    <p className="text-slate-300 text-xl font-medium tracking-wide">
                      Quantum-Powered Intelligence
                    </p>
                    {/* Animated accent line */}
                    <div className="h-1 w-24 bg-gradient-to-r from-blue-500 via-purple-500 to-cyan-500 rounded-full animate-pulse"></div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <div className="group relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-r from-emerald-500/10 to-green-500/10 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                    <div className="relative flex items-center gap-3 px-5 py-3 backdrop-blur-sm bg-slate-800/50 rounded-full border border-emerald-500/30 hover:border-emerald-400/50 transition-all duration-300 shadow-lg shadow-emerald-500/5">
                      <div className="relative">
                        <div className="w-3 h-3 bg-emerald-400 rounded-full animate-pulse shadow-lg shadow-emerald-400/50"></div>
                        <div className="absolute inset-0 w-3 h-3 bg-emerald-400 rounded-full animate-ping opacity-75"></div>
                      </div>
                      <span className="text-emerald-200 font-bold tracking-wide">{(bots || []).length} AI Agents Active</span>
                      <div className="w-2 h-2 bg-emerald-400/30 rounded-full animate-pulse"></div>
                    </div>
                  </div>

                  <div className="group relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-r from-blue-500/10 to-cyan-500/10 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                    <div className="relative flex items-center gap-3 px-5 py-3 backdrop-blur-sm bg-slate-800/50 rounded-full border border-blue-500/30 hover:border-blue-400/50 transition-all duration-300 shadow-lg shadow-blue-500/5">
                      <div className="relative">
                        <div className="w-3 h-3 bg-blue-400 rounded-full animate-pulse shadow-lg shadow-blue-400/50"></div>
                        <div className="absolute inset-0 w-3 h-3 bg-blue-400 rounded-full animate-ping opacity-75"></div>
                      </div>
                      <span className="text-blue-200 font-bold tracking-wide">Real Money Trading</span>
                      <div className="w-2 h-2 bg-blue-400/30 rounded-full animate-pulse"></div>
                    </div>
                  </div>

                  <div className="group relative overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                    <div className="relative flex items-center gap-3 px-5 py-3 backdrop-blur-sm bg-slate-800/50 rounded-full border border-purple-500/30 hover:border-purple-400/50 transition-all duration-300 shadow-lg shadow-purple-500/5">
                      <div className="relative">
                        <div className="w-3 h-3 bg-purple-400 rounded-full animate-pulse shadow-lg shadow-purple-400/50"></div>
                        <div className="absolute inset-0 w-3 h-3 bg-purple-400 rounded-full animate-ping opacity-75"></div>
                      </div>
                      <span className="text-purple-200 font-bold tracking-wide">Live Market Data</span>
                      <div className="w-2 h-2 bg-purple-400/30 rounded-full animate-pulse"></div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Ultra-Modern Portfolio Display */}
              <div className="text-right space-y-4">
                <div className="flex items-center justify-end gap-2">
                  <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></div>
                  <div className="text-sm text-slate-400 uppercase tracking-[0.2em] font-bold">Portfolio Value</div>
                </div>

                <div className="relative">
                  {/* Animated glow effect */}
                  <div className="absolute -inset-4 bg-gradient-to-r from-blue-500/10 via-purple-500/8 to-cyan-500/10 rounded-3xl blur-xl opacity-50 animate-pulse duration-3000"></div>
                  <div className="relative text-7xl font-black bg-gradient-to-r from-white via-blue-100 to-purple-200 bg-clip-text text-transparent animate-pulse tracking-tight">
                    ${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className={`inline-flex items-center gap-3 px-6 py-3 rounded-2xl backdrop-blur-sm transition-all duration-500 transform ${totalPnl >= 0
                    ? 'bg-gradient-to-r from-emerald-500/10 to-green-500/10 border border-emerald-500/30 shadow-lg shadow-emerald-500/10 scale-105'
                    : 'bg-gradient-to-r from-rose-500/10 to-red-500/10 border border-rose-500/30 shadow-lg shadow-rose-500/10 scale-95'
                    }`}>
                    <div className={`text-3xl ${totalPnl >= 0 ? 'animate-bounce' : 'animate-pulse'}`}>
                      {totalPnl >= 0 ? '🚀' : '📉'}
                    </div>
                    <div className="text-center">
                      <div className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-emerald-300' : 'text-rose-300'} tracking-wide`}>
                        {totalPnl >= 0 ? '+' : ''}${Math.abs(totalPnl).toFixed(2)}
                      </div>
                      <div className={`text-sm font-medium ${totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'} uppercase tracking-wide`}>
                        {totalPnl >= 0 ? 'Profit' : 'Loss'}
                      </div>
                    </div>
                  </div>

                  <div className={`text-xl font-semibold ${totalPnl >= 0 ? 'text-emerald-300' : 'text-rose-300'} tracking-wide`}>
                    ({pnlPercent >= 0 ? '+' : ''}{(pnlPercent ?? 0).toFixed(2)}%)
                  </div>
                </div>

                {/* Mini Performance Indicator */}
                <div className="flex items-center gap-2 mt-3">
                  <div className={`px-3 py-1 rounded-full text-xs font-medium transition-all duration-300 ${totalPnl >= 0
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                    : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                    }`}>
                    {totalPnl >= 0 ? '🚀 PROFITABLE' : '⚠️ LOSING'}
                  </div>
                </div>
              </div>
            </div>

            {/* Animated Progress Bar */}
            <div className="mt-8">
              <div className="flex justify-between text-sm text-slate-400 mb-2">
                <span>AI Confidence Level</span>
                <span>{Math.min(95, Math.max(0, 50 + (pnlPercent ?? 0) * 2)).toFixed(0)}%</span>
              </div>
              <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 via-purple-500 to-cyan-500 rounded-full transition-all duration-1000 ease-out"
                  style={{ width: `${Math.min(95, Math.max(0, 50 + (pnlPercent ?? 0) * 2))}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>

        {/* Ultra-Modern Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
          <div className="group relative overflow-hidden">
            <div className="absolute -inset-1 bg-gradient-to-r from-blue-500/20 via-purple-500/15 to-cyan-500/20 rounded-3xl blur-lg opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            <div className="relative bg-gradient-to-br from-slate-900/95 to-slate-800/95 backdrop-blur-xl rounded-3xl p-8 border border-blue-500/20 hover:border-blue-400/40 transition-all duration-500 shadow-2xl hover:shadow-blue-500/10 hover:scale-[1.02]">
              {/* Animated background pattern */}
              <div className="absolute inset-0 opacity-5">
                <div className="absolute top-4 right-4 w-16 h-16 border border-blue-400/20 rounded-full animate-spin duration-8000"></div>
              </div>

              <div className="flex items-center gap-6 relative z-10">
                <div className="relative">
                  <div className="w-16 h-16 bg-gradient-to-br from-blue-500/20 to-purple-500/20 rounded-2xl flex items-center justify-center shadow-xl border border-blue-400/30 backdrop-blur-sm group-hover:shadow-blue-500/20 transition-all duration-300">
                    <span className="text-3xl filter drop-shadow-lg">🤖</span>
                  </div>
                  {/* Pulsing indicator */}
                  <div className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 rounded-full animate-pulse shadow-lg shadow-blue-500/50"></div>
                </div>
                <div>
                  <div className="text-4xl font-black text-white mb-1">{(bots || []).length}</div>
                  <div className="text-slate-300 font-semibold tracking-wide">Active Agents</div>
                  <div className="h-1 w-12 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full mt-2 animate-pulse"></div>
                </div>
              </div>
            </div>
          </div>

          <div className="group relative overflow-hidden">
            <div className="absolute -inset-1 bg-gradient-to-r from-purple-500/20 via-pink-500/15 to-cyan-500/20 rounded-3xl blur-lg opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            <div className="relative bg-gradient-to-br from-slate-900/95 to-slate-800/95 backdrop-blur-xl rounded-3xl p-8 border border-purple-500/20 hover:border-purple-400/40 transition-all duration-500 shadow-2xl hover:shadow-purple-500/10 hover:scale-[1.02]">
              {/* Animated background pattern */}
              <div className="absolute inset-0 opacity-5">
                <div className="absolute top-4 right-4 w-12 h-12 border border-purple-400/20 rounded-full animate-spin duration-6000"></div>
              </div>

              <div className="flex items-center gap-6 relative z-10">
                <div className="relative">
                  <div className="w-16 h-16 bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-2xl flex items-center justify-center shadow-xl border border-purple-400/30 backdrop-blur-sm group-hover:shadow-purple-500/20 transition-all duration-300">
                    <span className="text-3xl filter drop-shadow-lg">💰</span>
                  </div>
                  {/* Pulsing indicator */}
                  <div className="absolute -top-1 -right-1 w-4 h-4 bg-purple-500 rounded-full animate-pulse shadow-lg shadow-purple-500/50"></div>
                </div>
                <div>
                  <div className="text-4xl font-black text-white mb-1">${totalValue.toLocaleString('en-US', { maximumFractionDigits: 0 })}</div>
                  <div className="text-slate-300 font-semibold tracking-wide">Portfolio Value</div>
                  <div className="h-1 w-12 bg-gradient-to-r from-purple-500 to-pink-500 rounded-full mt-2 animate-pulse"></div>
                </div>
              </div>
            </div>
          </div>

          <div className={`group relative overflow-hidden ${totalPnl >= 0 ? 'border-emerald-500/30' : 'border-rose-500/30'}`}>
            <div className={`absolute -inset-1 rounded-3xl blur-lg opacity-0 group-hover:opacity-100 transition-opacity duration-500 ${totalPnl >= 0
                ? 'bg-gradient-to-r from-emerald-500/20 to-green-500/15'
                : 'bg-gradient-to-r from-rose-500/20 to-red-500/15'
              }`}></div>
            <div className={`relative bg-gradient-to-br from-slate-900/95 to-slate-800/95 backdrop-blur-xl rounded-3xl p-8 border hover:border-opacity-60 transition-all duration-500 shadow-2xl hover:scale-[1.02] ${totalPnl >= 0
                ? 'hover:shadow-emerald-500/10 border-emerald-500/20'
                : 'hover:shadow-rose-500/10 border-rose-500/20'
              }`}>
              {/* Animated background pattern */}
              <div className="absolute inset-0 opacity-5">
                <div className={`absolute top-4 right-4 w-12 h-12 border rounded-full animate-spin duration-5000 ${totalPnl >= 0 ? 'border-emerald-400/20' : 'border-rose-400/20'
                  }`}></div>
              </div>

              <div className="flex items-center gap-6 relative z-10">
                <div className="relative">
                  <div className={`w-16 h-16 rounded-2xl flex items-center justify-center shadow-xl border backdrop-blur-sm group-hover:shadow-lg transition-all duration-300 ${totalPnl >= 0
                      ? 'bg-gradient-to-br from-emerald-500/20 to-green-500/20 border-emerald-400/30 group-hover:shadow-emerald-500/20'
                      : 'bg-gradient-to-br from-rose-500/20 to-red-500/20 border-rose-400/30 group-hover:shadow-rose-500/20'
                    }`}>
                    <span className="text-3xl filter drop-shadow-lg">
                      {totalPnl >= 0 ? '📈' : '📉'}
                    </span>
                  </div>
                  {/* Pulsing indicator */}
                  <div className={`absolute -top-1 -right-1 w-4 h-4 rounded-full animate-pulse shadow-lg ${totalPnl >= 0 ? 'bg-emerald-500 shadow-emerald-500/50' : 'bg-rose-500 shadow-rose-500/50'
                    }`}></div>
                </div>
                <div>
                  <div className={`text-4xl font-black mb-1 ${totalPnl >= 0 ? 'text-emerald-300' : 'text-rose-300'
                    }`}>
                    {totalPnl >= 0 ? '+' : ''}${Math.abs(totalPnl).toFixed(2)}
                  </div>
                  <div className="text-slate-300 font-semibold tracking-wide">P&L Today</div>
                  <div className={`h-1 w-12 rounded-full mt-2 animate-pulse ${totalPnl >= 0 ? 'bg-gradient-to-r from-emerald-500 to-green-500' : 'bg-gradient-to-r from-rose-500 to-red-500'
                    }`}></div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-slate-900/90 rounded-2xl p-6 border border-cyan-500/30 relative overflow-hidden group hover:scale-[1.02] transition-transform duration-300 shadow-xl">
            <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
              <span className="text-6xl">⚡</span>
            </div>
            <div className="flex items-center gap-4 relative z-10">
              <div className="w-14 h-14 gradient-accent rounded-2xl flex items-center justify-center shadow-lg shadow-cyan-500/20">
                <span className="text-white text-2xl">⚡</span>
              </div>
              <div>
                <div className="text-3xl font-bold text-white">
                  ${(trades || []).reduce((acc, trade) => acc + (trade.value || 0), 0).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </div>
                <div className="text-sm text-slate-300 font-medium">Volume Traded</div>
              </div>
            </div>
          </div>
        </div>

        {/* Main Dashboard Grid with Enhanced Styling */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
          {/* Left Column: Performance & Trades */}
          <div className="xl:col-span-2 space-y-8">
            <div className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 backdrop-blur-xl rounded-2xl p-6 border border-slate-700/50 shadow-2xl">
              <BotPerformanceBoard
                bots={bots}
                totalValue={totalValue}
                dayChange={totalPnl}
                dayChangePercent={pnlPercent}
              />
            </div>

            {openPositions && openPositions.length > 0 && (
              <div className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 backdrop-blur-xl rounded-2xl border border-slate-700/50 shadow-2xl">
                <OpenPositionsTable positions={openPositions} />
              </div>
            )}

            <div className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 backdrop-blur-xl rounded-2xl p-6 border border-slate-700/50 shadow-2xl">
              <TradeActivityFeed trades={trades as any} />
            </div>
          </div>

          {/* Right Column: Agent Chat with Enhanced Styling */}
          <div className="xl:col-span-1">
            <div className="bg-gradient-to-br from-slate-900/80 to-slate-800/80 backdrop-blur-xl rounded-2xl p-6 border border-slate-700/50 shadow-2xl h-full">
              <LiveAgentChat messages={messages} />
            </div>
          </div>
        </div>

        {/* Enhanced System Status Footer */}
        <div className="bg-gradient-to-br from-slate-900/95 to-slate-800/95 backdrop-blur-xl rounded-2xl p-6 border border-slate-700/50 shadow-2xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-gradient-to-br from-emerald-500 to-green-600 rounded-lg flex items-center justify-center shadow-lg">
                  <span className="text-white text-sm">💎</span>
                </div>
                <div>
                  <div className="text-white font-semibold">Sapphire AI System</div>
                  <div className="text-slate-400 text-sm">Enterprise-Grade Trading Intelligence</div>
                </div>
              </div>

              <div className="hidden md:flex items-center gap-4 text-sm">
                <div className="flex items-center gap-2 px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-full">
                  <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></div>
                  <span className="text-emerald-400">6 AI Agents Online</span>
                </div>
                <div className="flex items-center gap-2 px-3 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full">
                  <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                  <span className="text-blue-400">Real Money Trading</span>
                </div>
                <div className="flex items-center gap-2 px-3 py-1 bg-purple-500/10 border border-purple-500/20 rounded-full">
                  <div className="w-2 h-2 bg-purple-500 rounded-full"></div>
                  <span className="text-purple-400">Live Data Streams</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className="text-right hidden md:block">
                <div className="text-slate-400 text-sm">System Status</div>
                <div className="text-emerald-400 font-semibold">All Systems Operational</div>
              </div>

              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-emerald-500 rounded-full animate-pulse shadow-lg shadow-emerald-500/50"></div>
                <span className="text-emerald-400 font-medium">Online</span>
              </div>
            </div>
          </div>

          {/* Performance Indicator */}
          <div className="mt-4 pt-4 border-t border-slate-700/50">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Overall AI Performance</span>
              <div className="flex items-center gap-2">
                <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-blue-500 rounded-full transition-all duration-1000"
                    style={{ width: `${Math.min(100, Math.max(0, 60 + pnlPercent))}%` }}
                  ></div>
                </div>
                <span className="text-slate-300 font-medium">
                  {Math.min(100, Math.max(0, 60 + pnlPercent)).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
