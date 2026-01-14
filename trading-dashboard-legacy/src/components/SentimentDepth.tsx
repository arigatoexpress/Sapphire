import { useState, useEffect } from 'react';
import { Users, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface SentimentDepthProps {
    symbol: string;
}

interface SentimentData {
    bullish_pct: number;
    bearish_pct: number;
    neutral_pct: number;
    vote_count: number;
    avg_confidence: number;
}

const SentimentDepth = ({ symbol }: SentimentDepthProps) => {
    const [data, setData] = useState<SentimentData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchSentiment = async () => {
            try {
                const response = await fetch(`/api/sentiment/${symbol}`);
                const result = await response.json();

                // Ensure default structure if API returns error or empty
                if (result.symbol) {
                    setData(result);
                } else {
                    // Fallback/Empty state
                    setData({
                        bullish_pct: 0,
                        bearish_pct: 0,
                        neutral_pct: 0,
                        vote_count: 0,
                        avg_confidence: 0
                    });
                }
            } catch (error) {
                console.error('Failed to fetch sentiment:', error);
            } finally {
                setLoading(false);
            }
        };

        fetchSentiment();
        // Poll every 10s for live feel
        const interval = setInterval(fetchSentiment, 10000);
        return () => clearInterval(interval);
    }, [symbol]);

    if (loading) return <div className="h-full flex items-center justify-center text-xs text-slate-500">Loading Sentiment...</div>;

    if (!data || data.vote_count === 0) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center p-4 text-center">
                <Users size={24} className="text-slate-600 mb-2" />
                <p className="text-xs text-slate-500">No votes yet for {symbol}</p>
                <div className="mt-2 text-[10px] text-slate-600 bg-white/5 px-2 py-1 rounded">
                    Be the first to predict!
                </div>
            </div>
        );
    }

    // Calculations for bar widths
    const bullW = Math.max(5, data.bullish_pct * 100);
    const bearW = Math.max(5, data.bearish_pct * 100);
    const neutralW = Math.max(5, data.neutral_pct * 100);

    return (
        <div className="flex flex-col h-full bg-[#0a0b10] p-4 overflow-hidden relative">
            {/* Header */}
            <div className="flex justify-between items-end mb-4 font-mono z-10">
                <div className="flex flex-col">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">CROWD CONSENSUS</span>
                    <span className={`text-xl font-bold ${data.bullish_pct > data.bearish_pct ? 'text-emerald-400' :
                            data.bearish_pct > data.bullish_pct ? 'text-rose-400' : 'text-slate-400'
                        }`}>
                        {data.bullish_pct > data.bearish_pct ? 'BULLISH' :
                            data.bearish_pct > data.bullish_pct ? 'BEARISH' : 'NEUTRAL'}
                    </span>
                </div>
                <div className="text-right">
                    <span className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">VOTES</span>
                    <span className="text-xl font-bold text-white block leading-none">{data.vote_count}</span>
                </div>
            </div>

            {/* Depth Bars (Vertical Stack or Horizontal?) -> Vertical mimics Order Book depth better visually */}
            <div className="flex-1 flex flex-col gap-3 justify-center relative z-10">

                {/* Bullish Bar */}
                <div className="w-full">
                    <div className="flex justify-between text-xs mb-1">
                        <span className="text-emerald-400 flex items-center gap-1"><TrendingUp size={12} /> {Math.round(data.bullish_pct * 100)}%</span>
                        <span className="text-emerald-500/50 text-[10px] font-mono">LONG BIAS</span>
                    </div>
                    <div className="h-3 w-full bg-slate-800/50 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)] transition-all duration-1000 ease-out"
                            style={{ width: `${bullW}%` }}
                        />
                    </div>
                </div>

                {/* Neutral Bar */}
                <div className="w-full">
                    <div className="flex justify-between text-xs mb-1">
                        <span className="text-amber-400 flex items-center gap-1"><Minus size={12} /> {Math.round(data.neutral_pct * 100)}%</span>
                        <span className="text-amber-500/50 text-[10px] font-mono">SIDEWAYS</span>
                    </div>
                    <div className="h-3 w-full bg-slate-800/50 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.3)] transition-all duration-1000 ease-out"
                            style={{ width: `${neutralW}%` }}
                        />
                    </div>
                </div>

                {/* Bearish Bar */}
                <div className="w-full">
                    <div className="flex justify-between text-xs mb-1">
                        <span className="text-rose-400 flex items-center gap-1"><TrendingDown size={12} /> {Math.round(data.bearish_pct * 100)}%</span>
                        <span className="text-rose-500/50 text-[10px] font-mono">SHORT BIAS</span>
                    </div>
                    <div className="h-3 w-full bg-slate-800/50 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.3)] transition-all duration-1000 ease-out"
                            style={{ width: `${bearW}%` }}
                        />
                    </div>
                </div>
            </div>

            {/* Avg Confidence Footer */}
            <div className="mt-4 pt-3 border-t border-white/5 flex justify-between items-center z-10">
                <span className="text-[10px] text-slate-500 uppercase">Avg. Confidence</span>
                <span className="text-sm font-mono text-blue-400 font-bold">
                    {Math.round(data.avg_confidence * 100)}%
                </span>
            </div>

            {/* Background Decor */}
            <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-blue-900/5 pointer-events-none" />
        </div>
    );
};

export default SentimentDepth;
