import React, { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// Real data type from context
export interface StreamItem {
    id: string;
    timestamp: string | number;
    type: 'trade' | 'signal' | 'funding' | 'error' | 'info';
    message: string;
    value?: number;
    symbol: string;
    agent?: string;
}

interface StreamWaterfallProps {
    items: StreamItem[];
}

const StreamWaterfall: React.FC<StreamWaterfallProps> = ({ items }) => {
    const containerRef = useRef<HTMLDivElement>(null);

    // Auto-scroll logic
    useEffect(() => {
        if (containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [items]);

    // Color mapping logic
    const getTypeColor = (type: string) => {
        switch (type) {
            case 'trade': return 'text-fd-success border-l-fd-success';
            case 'signal': return 'text-fd-purple border-l-fd-purple';
            case 'funding': return 'text-fd-blue border-l-fd-blue';
            case 'error': return 'text-fd-error border-l-fd-error';
            default: return 'text-gray-400 border-l-gray-600';
        }
    };

    const getTypeBg = (type: string) => {
        switch (type) {
            case 'trade': return 'bg-fd-success/10';
            case 'signal': return 'bg-fd-purple/5';
            case 'funding': return 'bg-fd-blue/5';
            case 'error': return 'bg-fd-error/10';
            default: return 'bg-transparent';
        }
    };

    const formatTimestamp = (ts: string | number) => {
        const d = new Date(ts);
        return d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' +
            d.getMilliseconds().toString().padStart(3, '0');
    };

    return (
        <div className="h-full flex flex-col bg-fd-card border border-fd-border rounded-sm relative overflow-hidden group">
            {/* Header */}
            <div className="px-3 py-2 border-b border-fd-border bg-fd-bg/50 backdrop-blur-sm flex justify-between items-center z-10">
                <h3 className="text-xs font-mono font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-fd-success rounded-sm animate-pulse"></span>
                    Live Stream
                </h3>
                <span className="text-[10px] text-fd-muted font-mono tracking-tighter uppercase whitespace-pre">
                    {items.length} EVENTS LOADED
                </span>
            </div>

            {/* The Waterfall */}
            <div
                ref={containerRef}
                className="flex-1 overflow-y-auto overflow-x-hidden p-2 space-y-0.5 scrollbar-thin scrollbar-thumb-fd-border scrollbar-track-transparent font-mono text-[11px]"
            >
                <AnimatePresence initial={false}>
                    {items.slice(-60).map((item) => (
                        <motion.div
                            key={item.id}
                            initial={{ opacity: 0, x: -5 }}
                            animate={{ opacity: 1, x: 0 }}
                            className={`
                            relative flex items-center gap-3 px-2 py-1 border-l-2 rounded-r-sm
                            ${getTypeColor(item.type)}
                            ${getTypeBg(item.type)}
                            hover:bg-opacity-20 transition-colors cursor-crosshair
                        `}
                        >
                            {/* Timestamp */}
                            <span className="text-gray-600 w-24 opacity-50 font-light tabular-nums">
                                {formatTimestamp(item.timestamp)}
                            </span>

                            {/* Agent Badge (Instead of Symbol if Symbol is missing) */}
                            <span className="px-1 py-0.5 bg-black/40 rounded text-[9px] min-w-[70px] text-center font-bold text-gray-300 uppercase truncate">
                                {item.symbol || item.agent || 'SYSTEM'}
                            </span>

                            {/* Main Message */}
                            <span className="flex-1 truncate tracking-tight font-medium">
                                {item.message}
                            </span>

                            {/* Value Badge (if any) */}
                            {item.value !== undefined && (
                                <span className="opacity-40 text-[10px] tabular-nums">
                                    {(item.value * 100).toFixed(2)}%
                                </span>
                            )}
                        </motion.div>
                    ))}
                </AnimatePresence>

                {/* Anchor for auto-scroll */}
                <div className="h-1"></div>
            </div>

            {/* CRT Scanline Overlay */}
            <div className="absolute inset-0 pointer-events-none bg-gradient-to-b from-transparent via-white/[0.01] to-transparent bg-[length:100%_4px] animate-pulse-slow opacity-20"></div>
        </div>
    );
};

export default StreamWaterfall;
