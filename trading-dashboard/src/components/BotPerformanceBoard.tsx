import React from 'react';
import { TrendingUp, TrendingDown, DollarSign, Activity, Brain } from 'lucide-react';
import { AreaChart, Area, ResponsiveContainer, XAxis, YAxis } from 'recharts';

interface BotMetrics {
  id: string;
  name: string;
  emoji: string;
  pnl: number;
  pnlPercent: number;
  allocation: number;
  activePositions: number;
  history: { time: string; value: number }[];
}

interface Props {
  bots: BotMetrics[];
  totalValue: number;
  dayChange: number;
  dayChangePercent: number;
}

export const BotPerformanceBoard: React.FC<Props> = ({
  bots,
  totalValue,
  dayChange,
  dayChangePercent
}) => {
  return (
    <div className="space-y-6">
      {/* Portfolio Overview Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2 bg-slate-900/50 border border-slate-800 rounded-2xl p-6 backdrop-blur-sm">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h2 className="text-slate-400 text-sm font-medium uppercase tracking-wider mb-1">Total Portfolio Value</h2>
              <div className="flex items-baseline gap-3">
                <span className="text-4xl font-bold text-white">
                  ${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </span>
                <div className={`flex items-center gap-1 px-2 py-1 rounded-lg text-sm font-semibold ${dayChange >= 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                }`}>
                  {dayChange >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                  {dayChangePercent >= 0 ? '+' : ''}{dayChangePercent.toFixed(2)}%
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <Badge icon={<Brain size={14} />} label="6 Active Agents" />
              <Badge icon={<Activity size={14} />} label="Live Trading" />
            </div>
          </div>

          <div className="h-[200px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={bots[0]?.history || []}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" hide />
                <YAxis hide domain={['auto', 'auto']} />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#3b82f6"
                  fillOpacity={1}
                  fill="url(#colorValue)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="space-y-4">
          <StatCard
            label="Total Profit/Loss"
            value={`$${dayChange.toFixed(2)}`}
            subValue="All Time"
            trend={dayChange >= 0 ? 'up' : 'down'}
          />
          <StatCard
            label="Active Positions"
            value={bots.reduce((acc, bot) => acc + bot.activePositions, 0).toString()}
            subValue="Across all agents"
            icon={<Activity size={20} className="text-purple-400" />}
          />
          <StatCard
            label="Capital Deployed"
            value={`$${bots.reduce((acc, bot) => acc + bot.allocation, 0).toFixed(0)}`}
            subValue="100% Utilization"
            icon={<DollarSign size={20} className="text-amber-400" />}
          />
        </div>
      </div>

      {/* Agent Leaderboard */}
      <div>
        <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <Brain size={20} className="text-blue-400" />
          Agent Performance Leaderboard
        </h3>
            <div className="text-xs text-slate-400 px-3 py-1 rounded-full bg-slate-800 border border-slate-700">
                🏆 Ranked by PnL
            </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {(!bots || bots.length === 0) ? (
            <div className="col-span-full text-center p-8 text-slate-500 bg-slate-900/30 rounded-xl border border-slate-800">
              Initializing agents...
            </div>
          ) : (
            [...bots].sort((a, b) => b.pnl - a.pnl).map((bot, index) => (
              <BotCard key={bot.id} bot={bot} rank={index + 1} />
            ))
          )}
        </div>
      </div>
    </div>
  );
};

const Badge = ({ icon, label }: any) => (
  <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 rounded-full border border-slate-700 text-xs font-medium text-slate-300">
    {icon}
    {label}
  </div>
);

const StatCard = ({ label, value, subValue, trend, icon }: any) => (
  <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 backdrop-blur-sm h-[calc(33.33%-0.66rem)] flex flex-col justify-center">
    <div className="flex justify-between items-start mb-1">
      <span className="text-slate-400 text-xs uppercase tracking-wider font-medium">{label}</span>
      {icon}
    </div>
    <div className="flex items-baseline gap-2">
      <span className={`text-2xl font-bold ${trend === 'up' ? 'text-emerald-400' :
        trend === 'down' ? 'text-rose-400' :
        'text-white'
      }`}>
        {value}
      </span>
    </div>
    <span className="text-slate-500 text-xs">{subValue}</span>
  </div>
);

const BotCard = ({ bot, rank }: { bot: BotMetrics; rank: number }) => {
    const isWinner = rank === 1;
    
    return (
      <div className={`bg-slate-900/50 border rounded-xl p-4 transition-all duration-300 group relative overflow-hidden ${
        isWinner 
            ? 'border-amber-500/50 shadow-lg shadow-amber-500/10 bg-gradient-to-b from-amber-500/5 to-slate-900/50' 
            : 'border-slate-800 hover:border-slate-700'
      }`}>
        {/* Rank Badge */}
        <div className="absolute top-0 left-0 z-10">
            <div className={`w-8 h-8 flex items-center justify-center rounded-br-xl font-bold text-sm shadow-md ${
            rank === 1 ? 'bg-amber-500 text-slate-900' :
            rank === 2 ? 'bg-slate-300 text-slate-900' :
            rank === 3 ? 'bg-orange-600 text-white' :
            'bg-slate-800 text-slate-500 border-b border-r border-slate-700'
            }`}>
            {rank === 1 ? '👑' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `#${rank}`}
            </div>
        </div>

        <div className="flex justify-between items-start mb-4 pl-6">
      <div className="flex items-center gap-3">
            <div className={`h-10 w-10 rounded-lg flex items-center justify-center text-xl border transition-colors ${
                isWinner ? 'bg-amber-500/10 border-amber-500/30' : 'bg-slate-800 border-slate-700 group-hover:border-slate-600'
            }`}>
          {bot.emoji}
        </div>
        <div>
              <h4 className={`font-semibold ${isWinner ? 'text-amber-200' : 'text-slate-200'}`}>
                {bot.name}
              </h4>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span>${bot.allocation} Alloc</span>
            <span>•</span>
            <span className={bot.activePositions > 0 ? 'text-emerald-400' : 'text-slate-500'}>
              {bot.activePositions} Active
            </span>
          </div>
        </div>
      </div>
      <div className={`text-right ${bot.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
        <div className="font-bold flex items-center justify-end gap-1">
          {bot.pnl >= 0 ? '+' : ''}{bot.pnlPercent.toFixed(2)}%
        </div>
        <div className="text-xs opacity-80">
          ${Math.abs(bot.pnl).toFixed(2)}
        </div>
      </div>
    </div>

    <div className="h-16 w-full opacity-50 group-hover:opacity-100 transition-opacity">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={bot.history}>
          <defs>
            <linearGradient id={`grad-${bot.id}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={bot.pnl >= 0 ? '#10b981' : '#f43f5e'} stopOpacity={0.2} />
                  <stop offset="100%" stopColor={bot.pnl >= 0 ? '#10b981' : '#f43f5e'} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={bot.pnl >= 0 ? '#10b981' : '#f43f5e'}
            strokeWidth={2}
            fill={`url(#grad-${bot.id})`}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  </div>
);
};
