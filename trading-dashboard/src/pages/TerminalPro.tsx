import React, { useState, useEffect } from 'react';
import TradingViewChart from '../components/TradingViewChart';
import {
    TrendingUp,
    TrendingDown,
    Activity,
    Wifi,
    Brain,
    MessageSquare,
    Users
} from 'lucide-react';
import { useTradingData } from '../contexts/TradingContext';
import DailyVoteCard from '../components/DailyVoteCard';
import PointsWidget from '../components/PointsWidget';
import SentimentDepth from '../components/SentimentDepth';

const MarketStat: React.FC<{ label: string; value: string; trend?: 'up' | 'down'; subValue?: string }> = ({ label, value, trend, subValue }) => (
    <div className="flex flex-col">
        <span className="text-secondary-400 text-xs font-mono mb-1 uppercase tracking-wider">{label}</span>
        <div className="flex items-center gap-2">
            <span className="text-xl font-bold font-mono text-white">{value}</span>
            {trend && (
                <span className={`flex items-center text-xs px-1.5 py-0.5 rounded ${trend === 'up' ? 'text-emerald-400 bg-emerald-500/10' : 'text-rose-400 bg-rose-500/10'}`}>
                    {trend === 'up' ? <TrendingUp size={12} className="mr-1" /> : <TrendingDown size={12} className="mr-1" />}
                    {subValue}
                </span>
            )}
        </div>
    </div>
);

export const TerminalPro: React.FC = () => {
    const { connected, recent_activity, market_regime, open_positions } = useTradingData();
    const [selectedPair] = useState('ETH-USD');
    const [chartData, setChartData] = useState<any[]>([]);

    useEffect(() => {
        // Mock data generator for 150 candles
        const count = 150;
        const data = [];
        let time = Math.floor(Date.now() / 1000) - count * 60;
        let price = 2400; // ETH price
        for (let i = 0; i < count; i++) {
            const open = price;
            const close = price + (Math.random() - 0.5) * 10;
            const high = Math.max(open, close) + Math.random() * 5;
            const low = Math.min(open, close) - Math.random() * 5;
            const volume = Math.random() * 1000;
            data.push({ time, open, high, low, close, volume });
            time += 60;
            price = close;
        }
        setChartData(data);

        const interval = setInterval(() => {
            setChartData(prev => {
                if (prev.length === 0) return prev;
                const last = prev[prev.length - 1];
                const newTime = last.time + 60;
                const newPrice = last.close + (Math.random() - 0.5) * 5;
                const newCandle = {
                    time: newTime,
                    open: last.close,
                    high: Math.max(last.close, newPrice) + Math.random() * 2,
                    low: Math.min(last.close, newPrice) - Math.random() * 2,
                    close: newPrice,
                    volume: Math.random() * 50
                };
                return [...prev.slice(1), newCandle];
            });
        }, 3000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="flex flex-col gap-6 h-[calc(100vh-100px)]">

            {/* 🟦 TOP BAR: Stats & Points HUD */}
            <div className="flex justify-between items-start gap-6">
                {/* Market Stats */}
                <div className="flex-1 p-4 rounded-2xl bg-[#0a0b10] border border-white/10 grid grid-cols-4 gap-4">
                    <MarketStat label="Regime" value={market_regime?.current_regime || 'WAITING'} trend="up" subValue={(market_regime?.volatility_score ?? 0).toFixed(2)} />
                    <MarketStat label="24h High" value="$2,480.00" />
                    <MarketStat label="24h Vol" value="12.5M" />
                    <MarketStat label="Liquidity" value={(market_regime?.liquidity_score ?? 0).toFixed(2)} trend="up" subValue="Score" />
                </div>

                {/* Social HUD */}
                <div className="hidden lg:block">
                    <PointsWidget />
                </div>
            </div>

            {/* 🟥 MAIN GRID */}
            <div className="grid grid-cols-12 gap-6 flex-1 min-h-0">

                {/* 📊 LEFT: Crowd Sentiment Depth (Replacing Legacy Order Book) */}
                <div className="col-span-12 lg:col-span-3 flex flex-col gap-4 h-full min-h-0">

                    {/* Symbol Header */}
                    <div className="p-4 rounded-2xl bg-[#0a0b10] border border-white/10 flex items-center justify-between shrink-0">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-full bg-blue-600/20 flex items-center justify-center text-blue-400">
                                <Activity size={20} />
                            </div>
                            <div>
                                <h2 className="text-lg font-bold text-white">{selectedPair}</h2>
                                <span className="text-xs text-emerald-400 font-mono flex items-center">
                                    <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-500' : 'bg-red-500'} mr-1.5 animate-pulse`} />
                                    {connected ? 'MARKET OPEN' : 'DISCONNECTED'}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Real-Time Sentiment Gauge */}
                    <div className="flex-1 rounded-2xl bg-[#0a0b10] border border-white/10 flex flex-col overflow-hidden relative">
                        <div className="p-3 border-b border-white/5 flex justify-between items-center bg-[#0f1016]">
                            <span className="text-xs font-bold text-slate-400 flex items-center gap-2">
                                <Users size={12} className="text-blue-400" /> CROWD SENTIMENT
                            </span>
                            <span className="flex h-1.5 w-1.5 relative">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500"></span>
                            </span>
                        </div>
                        <SentimentDepth symbol={selectedPair} />
                    </div>
                </div>

                {/* 📈 CENTER: Chart & Prediction Deck */}
                <div className="col-span-12 lg:col-span-6 flex flex-col gap-4 h-full min-h-0">

                    {/* Main Chart Area */}
                    <div className="flex-1 rounded-2xl bg-[#0a0b10] border border-white/10 relative overflow-hidden group flex flex-col">
                        <div className="flex-1 w-full h-full">
                            <TradingViewChart data={chartData} height={500} symbol={selectedPair} />
                        </div>
                        <div className="absolute top-4 right-4 flex items-center gap-2 bg-black/40 backdrop-blur-md px-3 py-1 rounded-full border border-white/10 pointer-events-none">
                            <Wifi size={14} className={connected ? "text-emerald-500" : "text-rose-500"} />
                            <span className="text-xs text-slate-300">
                                {connected ? "Real-time" : "Connecting..."}
                            </span>
                        </div>
                        {/* Timeframe Toggles */}
                        <div className="absolute top-4 left-4 flex gap-1 bg-black/40 backdrop-blur-md p-1 rounded-lg border border-white/5">
                            {['1m', '5m', '15m', '1h', '4h', 'D'].map(tf => (
                                <button key={tf} className="px-3 py-1 rounded-md text-xs font-bold text-slate-400 hover:text-white hover:bg-white/10 transition-colors">
                                    {tf}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Social Prediction Deck (Replacing Quick Trade) */}
                    <div className="h-64 rounded-2xl overflow-hidden shrink-0">
                        <DailyVoteCard symbol={selectedPair} />
                    </div>
                </div>

                {/* 📋 RIGHT: Intelligence & Positions */}
                <div className="col-span-12 lg:col-span-3 flex flex-col gap-4 h-full min-h-0">

                    {/* Live Intelligence Feed */}
                    <div className="h-1/2 rounded-2xl bg-[#0a0b10] border border-white/10 flex flex-col overflow-hidden">
                        <div className="p-3 border-b border-white/5 flex justify-between items-center bg-[#0f1016]">
                            <span className="text-xs font-bold text-slate-400 flex items-center gap-2">
                                <Brain size={12} className="text-purple-500" /> LIVE INTELLIGENCE
                            </span>
                            <span className="flex h-2 w-2 relative">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-500"></span>
                            </span>
                        </div>
                        <div className="flex-1 overflow-y-auto">
                            {recent_activity.length === 0 ? (
                                <div className="p-4 text-center text-xs text-slate-500 py-10 flex flex-col items-center gap-2">
                                    <Brain size={24} className="text-slate-700 opacity-50" />
                                    <span>Waiting for agent consensus...</span>
                                </div>
                            ) : (
                                recent_activity.map((activity, idx) => (
                                    <div key={`${activity.symbol || 'UNK'}-${activity.timestamp || idx}-${idx}`} className="flex flex-col px-4 py-3 border-b border-white/5 hover:bg-white/5 gap-1">
                                        <div className="flex justify-between items-center">
                                            <div className="flex items-center gap-2">
                                                <span className="font-bold text-white text-xs">{activity.symbol || 'Unknown'}</span>
                                                <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${(activity.winning_signal || '').includes('BUY') ? 'bg-emerald-500/20 text-emerald-400' : (activity.winning_signal || '').includes('SELL') ? 'bg-rose-500/20 text-rose-400' : 'bg-slate-500/20 text-slate-400'}`}>
                                                    {activity.winning_signal || 'NEUTRAL'}
                                                </span>
                                            </div>
                                            <span className="text-xs text-slate-500 font-mono">{((activity.confidence || 0) * 100).toFixed(0)}% CONF</span>
                                        </div>
                                        <div className="flex items-start gap-1.5 mt-1">
                                            <MessageSquare size={10} className="text-slate-600 mt-0.5 shrink-0" />
                                            <p className="text-[10px] text-slate-400 leading-relaxed font-mono">
                                                {activity.reasoning ? activity.reasoning.replace('Logic:', '') : "Consensus Reached"}
                                            </p>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>

                    {/* Active Positions */}
                    <div className="h-1/2 rounded-2xl bg-[#0a0b10] border border-white/10 flex flex-col overflow-hidden">
                        <div className="p-3 border-b border-white/5 flex justify-between items-center bg-[#0f1016]">
                            <span className="text-xs font-bold text-slate-400 flex items-center gap-2">
                                <Activity size={12} /> YOUR POSITIONS
                            </span>
                        </div>
                        {open_positions.length === 0 ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-2">
                                <span className="p-3 rounded-full bg-white/5">
                                    <Users size={20} />
                                </span>
                                <span className="text-xs">No active positions</span>
                            </div>
                        ) : (
                            <div className="flex-1 overflow-y-auto">
                                {open_positions.map((pos, i) => (
                                    <div key={i} className="px-4 py-3 border-b border-white/5 hover:bg-white/5">
                                        <div className="flex justify-between mb-1">
                                            <span className="font-bold text-white">{pos.symbol}</span>
                                            <span className={`font-mono ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                {(pos.pnl ?? 0) >= 0 ? '+' : ''}{(pos.pnl ?? 0).toFixed(2)}
                                            </span>
                                        </div>
                                        <div className="flex justify-between text-xs text-slate-500">
                                            <span>{pos.size} @ {pos.entry_price}</span>
                                            <span>{pos.leverage}x</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
