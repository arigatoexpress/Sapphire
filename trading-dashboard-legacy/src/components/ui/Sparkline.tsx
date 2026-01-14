import { memo } from 'react';
import { AreaChart, Area, ResponsiveContainer } from 'recharts';

interface SparklineProps {
    data: number[];
    color?: string;
    height?: number;
    showGradient?: boolean;
}

/**
 * Sparkline - Compact area chart for showing trends.
 * Used in stat cards to visualize 24h history.
 */
export const Sparkline = memo<SparklineProps>(({
    data,
    color = '#06b6d4', // cyan-500
    height = 32,
    showGradient = true
}) => {
    // Convert raw numbers to chart data format
    const chartData = data.map((value, index) => ({
        value,
        index
    }));

    // Determine if trend is positive (last value > first value)
    const isPositive = data.length >= 2 && data[data.length - 1] >= data[0];
    const effectiveColor = color === 'auto'
        ? (isPositive ? '#10b981' : '#ef4444') // emerald-500 / red-500
        : color;

    if (data.length < 2) {
        return (
            <div style={{ height }} className="flex items-center justify-center text-slate-600 text-xs">
                No data
            </div>
        );
    }

    return (
        <ResponsiveContainer width="100%" height={height}>
            <AreaChart data={chartData} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
                <defs>
                    <linearGradient id={`sparkGradient-${effectiveColor.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={effectiveColor} stopOpacity={0.3} />
                        <stop offset="100%" stopColor={effectiveColor} stopOpacity={0} />
                    </linearGradient>
                </defs>
                <Area
                    type="monotone"
                    dataKey="value"
                    stroke={effectiveColor}
                    strokeWidth={1.5}
                    fill={showGradient ? `url(#sparkGradient-${effectiveColor.replace('#', '')})` : 'transparent'}
                    isAnimationActive={false}
                />
            </AreaChart>
        </ResponsiveContainer>
    );
});

Sparkline.displayName = 'Sparkline';
export default Sparkline;
