
import React from 'react';

interface MetricTurbineProps {
    label: string;
    value: string | number;
    unit?: string;
    trend?: 'up' | 'down' | 'neutral';
    color?: 'success' | 'warning' | 'error' | 'blue' | 'purple';
    subtext?: string;
    progress?: number; // 0 to 100
}

const MetricTurbine: React.FC<MetricTurbineProps> = ({
    label,
    value,
    unit,
    trend,
    color = 'blue',
    subtext,
    progress
}) => {
    const getColorClass = (c: string) => {
        switch (c) {
            case 'success': return 'text-fd-success border-fd-success bg-fd-success';
            case 'warning': return 'text-fd-warning border-fd-warning bg-fd-warning';
            case 'error': return 'text-fd-error border-fd-error bg-fd-error';
            case 'purple': return 'text-fd-purple border-fd-purple bg-fd-purple';
            default: return 'text-fd-blue border-fd-blue bg-fd-blue';
        }
    };

    return (
        <div className="relative group bg-fd-card/50 border border-fd-border/50 p-4 h-full flex flex-col justify-between overflow-hidden">
            {/* Glow Effect */}
            <div className={`absolute top-0 right-0 w-24 h-24 bg-${color === 'blue' ? 'fd-blue' : `fd-${color}`}/5 blur-3xl rounded-full -mr-10 -mt-10 transition-opactiy group-hover:opacity-100 opacity-50`}></div>

            {/* Header */}
            <div className="flex justify-between items-start z-10">
                <span className="text-[10px] font-mono uppercase tracking-widest text-gray-500">{label}</span>
                {trend && (
                    <span className={`text-[10px] font-bold ${trend === 'up' ? 'text-fd-success' : trend === 'down' ? 'text-fd-error' : 'text-gray-400'}`}>
                        {trend === 'up' ? '▲' : trend === 'down' ? '▼' : '•'}
                    </span>
                )}
            </div>

            {/* Main Value */}
            <div className="flex items-baseline gap-1 my-2 z-10">
                <span className={`text-3xl font-mono font-bold tracking-tight text-white`}>
                    {value}
                </span>
                {unit && <span className="text-xs text-fd-muted font-mono">{unit}</span>}
            </div>

            {/* Progress / Subtext */}
            <div className="z-10 mt-auto">
                {progress !== undefined ? (
                    <div className="w-full bg-fd-border h-1 rounded-sm overflow-hidden flex">
                        <div
                            className={`h-full ${getColorClass(color).split(' ')[2]}`}
                            style={{ width: `${progress}%` }}
                        ></div>
                    </div>
                ) : (
                    <div className="text-[10px] text-fd-muted font-mono truncate">
                        {subtext || "---"}
                    </div>
                )}
            </div>

            {/* Corner Accent */}
            <div className={`absolute bottom-0 right-0 w-2 h-2 border-b border-r ${getColorClass(color).split(' ')[1]} opacity-50`}></div>
        </div>
    );
};

export default MetricTurbine;
