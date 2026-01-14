import React from 'react';
import { useTradingData } from '../contexts/TradingContext';
import { Wifi, RefreshCw } from 'lucide-react';

export const ConnectionStatus: React.FC = () => {
    const { connected } = useTradingData();

    return (
        <div className="fixed top-4 right-4 z-50">
            <div className={`
        flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium
        backdrop-blur-xl border transition-all duration-300
        ${connected
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                }
      `}>
                {connected ? (
                    <>
                        <Wifi className="w-3.5 h-3.5" />
                        <span>Live</span>
                        <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                    </>
                ) : (
                    <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Polling</span>
                    </>
                )}
            </div>
        </div>
    );
};

export default ConnectionStatus;
