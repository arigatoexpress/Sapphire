import React from 'react';

interface MetricCardProps {
    label: string;
    value: React.ReactNode;
    delta?: { value: number; label?: string } | null;
    icon?: string;
    accent?: 'emerald' | 'teal' | 'amber' | 'slate';
    footer?: React.ReactNode;
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, delta, icon, accent = 'teal', footer }) => {
    const deltaColor = delta && delta.value >= 0 ? 'text-emerald-400' : 'text-red-400';
    const accentMap: Record<'emerald' | 'teal' | 'amber' | 'slate', string> = {
        emerald: 'from-emerald-500/20 via-emerald-500/10 to-transparent border-emerald-400/20',
        teal: 'from-accent-teal/30 via-accent-teal/10 to-transparent border-accent-teal/20',
        amber: 'from-accent-amber/30 via-accent-amber/10 to-transparent border-accent-amber/20',
        slate: 'from-slate-500/20 via-slate-500/10 to-transparent border-slate-500/20',
    };

    return (
        <div className={`group relative overflow-hidden rounded-2xl border ${accentMap[accent]} bg-surface-100/60 p-6 shadow-glass transition-all duration-200 hover:shadow-glass-lg hover:scale-[1.02] hover:bg-surface-100/70`}>
            <div className="absolute inset-0 bg-gradient-to-br from-white/5 via-transparent to-transparent" />
            <div className="absolute inset-0 bg-gradient-to-br from-white/10 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
            <div className="relative flex items-start justify-between">
                <div className="transition-transform duration-200 group-hover:translate-y-[-1px]">
                    <p className="text-xs uppercase tracking-[0.35em] text-slate-400 transition-colors duration-200 group-hover:text-slate-300">{label}</p>
                    <div className="mt-2 text-3xl font-semibold text-white transition-transform duration-200 group-hover:scale-105">{value}</div>
                    {delta && (
                        <div className="mt-2 flex items-center gap-2 text-xs font-medium text-slate-300">
                            <span className={`${deltaColor} transition-all duration-200 group-hover:scale-110`}>
                                {delta.value >= 0 ? '+' : ''}
                                {delta.value.toFixed(2)}%
                            </span>
                            <span className="transition-colors duration-200 group-hover:text-slate-400">{delta.label ?? 'vs previous'}</span>
                        </div>
                    )}
                </div>
                {icon && <span className="text-3xl transition-transform duration-200 group-hover:scale-110 group-hover:rotate-3">{icon}</span>}
            </div>
            {footer && <div className="relative mt-4 text-xs text-slate-400 transition-colors duration-200 group-hover:text-slate-300">{footer}</div>}
        </div>
    );
};

export default MetricCard;

