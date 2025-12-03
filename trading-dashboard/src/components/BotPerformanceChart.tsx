
import React, { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine
} from 'recharts';

interface BotPerformanceChartProps {
  bots: any[];
}

const COLORS = [
  '#3b82f6', // Blue (Aster)
  '#10b981', // Green (Hype)
  '#8b5cf6', // Purple
  '#f59e0b', // Amber
  '#ec4899', // Pink
  '#06b6d4', // Cyan
  '#ef4444', // Red
  '#6366f1', // Indigo
];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="glass-card p-3 border border-white/10 bg-slate-900/90 text-xs shadow-xl rounded-lg">
        <p className="font-mono font-bold mb-2 text-white">{label}</p>
        <div className="space-y-1">
          {payload.map((p: any, i: number) => (
            <div key={i} className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
                <span className="text-slate-300">{p.name}</span>
              </div>
              <span className={`font-mono font-bold ${p.value >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${Number(p.value).toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  return null;
};

export const BotPerformanceChart: React.FC<BotPerformanceChartProps> = ({ bots }) => {
  
  const data = useMemo(() => {
    if (!bots || bots.length === 0) return [];

    // 1. Collect all unique timestamps and map values
    const timeMap: Record<string, any> = {};
    
    bots.forEach(bot => {
      if (bot.history && Array.isArray(bot.history)) {
        bot.history.forEach((point: any) => {
          const time = point.time;
          if (!timeMap[time]) {
            timeMap[time] = { time };
          }
          timeMap[time][bot.name] = point.value;
        });
      }
    });

    // 2. Convert to array and sort
    let result = Object.values(timeMap);
    
    // Sort by time string (HH:MM)
    result.sort((a, b) => a.time.localeCompare(b.time));
    
    // 3. Fill gaps (optional, but good for line charts)
    // For now, recharts connects points automatically.
    
    return result;
  }, [bots]);

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-white/20 text-sm font-mono">
        Waiting for trade history data...
      </div>
    );
  }

  // Filter active bots for the legend/lines
  const activeBots = bots.filter(b => b.active && b.history?.length > 0);

  return (
    <div className="w-full h-full min-h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" vertical={false} />
          <XAxis 
            dataKey="time" 
            stroke="#94a3b8" 
            fontSize={10} 
            tickLine={false}
            axisLine={false}
            minTickGap={30}
          />
          <YAxis 
            stroke="#94a3b8" 
            fontSize={10} 
            tickLine={false} 
            axisLine={false}
            tickFormatter={(value) => `$${value}`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend 
            wrapperStyle={{ paddingTop: '10px' }} 
            iconType="circle" 
            iconSize={8}
            formatter={(value) => <span className="text-slate-400 text-xs ml-1">{value}</span>}
          />
          <ReferenceLine y={0} stroke="#ffffff20" strokeDasharray="3 3" />
          
          {activeBots.map((bot, index) => (
            <Line
              key={bot.id}
              type="monotone"
              dataKey={bot.name}
              stroke={bot.system === 'hyperliquid' ? '#10b981' : COLORS[index % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3, fill: bot.system === 'hyperliquid' ? '#10b981' : COLORS[index % COLORS.length], strokeWidth: 0 }}
              activeDot={{ r: 6, strokeWidth: 0 }}
              connectNulls
              animationDuration={1000}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

