import React from 'react';
import { Activity, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface MarketRegimeWidgetProps {
    regime: any;
}

export const MarketRegimeWidget: React.FC<MarketRegimeWidgetProps> = ({ regime }) => {
    if (!regime || !regime.regime) return null;

    const regimeStr = regime.regime || '';

    const getIcon = () => {
        if (regimeStr.includes('BULL')) return <TrendingUp className="w-5 h-5 text-emerald-400" />;
        if (regimeStr.includes('BEAR')) return <TrendingDown className="w-5 h-5 text-rose-400" />;
        return <Minus className="w-5 h-5 text-blue-400" />;
    };

    const getColor = () => {
        if (regimeStr.includes('BULL')) return 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10';
        if (regimeStr.includes('BEAR')) return 'text-rose-400 border-rose-500/30 bg-rose-500/10';
        return 'text-blue-400 border-blue-500/30 bg-blue-500/10';
    };

    return (
        <div className="glass-card p-4 rounded-2xl mb-6 border border-white/10">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-white/60" />
                    <span className="text-xs font-bold text-white/60 uppercase tracking-wider">Market Regime</span>
                </div>
                <div className="text-[10px] font-mono text-white/40">
                    CONF: {((regime?.confidence ?? 0) * 100).toFixed(0)}%
                </div>
            </div>

            <div className={`flex items-center gap-3 p-3 rounded-xl border ${getColor()}`}>
                {getIcon()}
                <div>
                    <div className="text-sm font-bold tracking-wide">{regime.regime.replace('_', ' ')}</div>
                    <div className="text-[10px] opacity-80">
                        Vol: {(regime.volatility_level * 100).toFixed(0)}% | Trend: {(regime.trend_strength * 100).toFixed(0)}%
                    </div>
                </div>
            </div>
        </div>
    );
};
