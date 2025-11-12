import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useMemo } from 'react';
import AgentChart from './charts/AgentChart';
import AgentRadar from './visuals/AgentRadar';
import { resolveTokenMeta } from '../utils/tokenMeta';
const modelPalette = {
    'fingpt-alpha': {
        label: 'FinGPT Alpha',
        subtitle: 'Open-source thesis engine \u2022 privacy-first \u2022 Parallel queries enabled',
        accent: 'from-brand-accent-blue/30 via-brand-accent-purple/20 to-brand-accent-green/30',
        icon: '🧠',
        multiAgent: true,
    },
    'lagllama-degen': {
        label: 'Lag-LLaMA Degenerate',
        subtitle: 'High-volatility forecasts with anomaly guardrails \u2022 Parallel queries enabled',
        accent: 'from-brand-accent-purple/30 via-brand-accent-teal/20 to-brand-accent-blue/30',
        icon: '🦙',
        multiAgent: true,
    },
};
const statusTone = {
    active: 'bg-brand-accent-green/80 text-brand-midnight',
    monitoring: 'bg-brand-accent-teal/80 text-brand-midnight',
    idle: 'bg-brand-border/70 text-brand-ice',
    error: 'bg-red-400/80 text-brand-midnight',
};
const AgentCard = ({ agent, onClick, onViewHistory }) => {
    const formatCurrency = (value) => new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(value);
    const formatPercent = (value) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
    const pnlColor = agent.total_pnl >= 0 ? 'text-brand-accent-green' : 'text-red-400';
    const activePositions = agent.positions?.length ?? 0;
    const lastTrade = agent.last_trade ? new Date(agent.last_trade) : null;
    const agentDescription = agent.description || 'Autonomous trading agent on live Sapphire mainnet, pairing quantitative edges with open-source AI.';
    const chartData = useMemo(() => {
        if (!agent.performance)
            return [];
        return agent.performance.map((point) => ({
            timestamp: point.timestamp,
            equity: point.equity,
        }));
    }, [agent.performance]);
    const sentiment = useMemo(() => {
        const netExposure = (agent.positions ?? []).reduce((acc, position) => {
            const notional = typeof position.notional === 'number' ? position.notional : 0;
            const side = (position.side || '').toUpperCase();
            if (side === 'SELL')
                return acc - Math.abs(notional);
            if (side === 'BUY')
                return acc + Math.abs(notional);
            return acc + notional;
        }, 0);
        if (netExposure > 0.0001) {
            return { label: 'Bullish bias', tone: 'bg-brand-accent-green/20 text-brand-accent-green', icon: '▲' };
        }
        if (netExposure < -0.0001) {
            return { label: 'Bearish bias', tone: 'bg-red-500/20 text-red-400', icon: '▼' };
        }
        return { label: 'Neutral stance', tone: 'bg-brand-border/40 text-brand-ice/70', icon: '◈' };
    }, [agent.positions]);
    const palette = modelPalette[agent.model ?? ''] ?? {
        label: agent.model ?? 'Autonomous Agent',
        subtitle: 'Hybrid quant + AI decision stack',
        accent: 'from-brand-accent-blue/30 via-brand-accent-teal/20 to-brand-accent-purple/30',
        icon: '✦',
    };
    return (_jsxs("div", { onClick: onClick, className: "sapphire-panel group relative overflow-hidden border border-brand-border/50 bg-brand-abyss/70 p-6 transition-all duration-200 hover:-translate-y-1 hover:border-brand-accent-blue/60 hover:shadow-sapphire-xl cursor-pointer", children: [_jsx("div", { className: `pointer-events-none absolute inset-0 bg-gradient-to-br ${palette.accent} opacity-20 transition-opacity duration-200 group-hover:opacity-40` }), _jsx("div", { className: "pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-200", style: { backgroundImage: 'radial-gradient(circle at top, rgba(56, 189, 248, 0.25), transparent 55%)' } }), _jsxs("div", { className: "relative space-y-6", children: [_jsxs("div", { className: "flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between", children: [_jsxs("div", { className: "flex items-start gap-4", children: [_jsx("div", { className: "flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-accent-blue/20 text-2xl shadow-sapphire", children: _jsx("span", { "aria-hidden": true, children: palette.icon }) }), _jsxs("div", { className: "space-y-2", children: [_jsxs("div", { className: "flex flex-wrap items-center gap-2", children: [_jsx("h3", { className: "text-xl font-semibold text-brand-ice drop-shadow-sm", children: agent.name }), _jsxs("span", { className: `sapphire-chip ${sentiment.tone}`, children: [_jsx("span", { className: "text-sm", "aria-hidden": true, children: sentiment.icon }), sentiment.label] })] }), _jsx("div", { className: "rounded-full border border-brand-border/60 bg-brand-abyss/70 px-3 py-1 text-xs text-brand-ice/80", children: palette.subtitle })] })] }), _jsxs("span", { className: `inline-flex min-w-[8rem] items-center justify-center gap-2 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] ${statusTone[agent.status] ?? statusTone.monitoring}`, children: [_jsx("span", { className: "h-2 w-2 rounded-full bg-current shadow-inner" }), agent.status] })] }), _jsx("div", { className: "rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-4 shadow-sapphire-sm", children: _jsxs("div", { className: "flex flex-wrap items-center gap-4 text-sm text-brand-ice/80", children: [_jsxs("div", { className: "flex items-center gap-2", children: [_jsx("span", { className: "text-2xl", "aria-hidden": true, children: palette.icon }), _jsxs("div", { children: [_jsx("p", { className: "text-brand-ice font-semibold tracking-[0.3em] uppercase", children: palette.label }), _jsx("p", { className: "text-xs text-brand-ice/60", children: "Open-source, privacy-preserving AI inference routed via Sapphire" })] })] }), _jsxs("div", { className: "flex flex-wrap items-center gap-3 text-xs text-brand-ice/60", children: [palette.multiAgent && (_jsxs(_Fragment, { children: [_jsxs("span", { className: "inline-flex items-center gap-1 rounded-full bg-brand-accent-green/20 px-2 py-1 text-brand-accent-green", children: [_jsx("span", { children: "\u26A1" }), _jsx("span", { children: "Parallel Multi-Agent" })] }), _jsx("span", { className: "text-brand-border", children: "\u2022" })] })), _jsx("span", { children: "Community-safe reasoning logs" }), _jsx("span", { className: "text-brand-border", children: "\u2022" }), _jsx("span", { children: "Edge-weighted with real-market data" }), palette.multiAgent && (_jsxs(_Fragment, { children: [_jsx("span", { className: "text-brand-border", children: "\u2022" }), _jsx("span", { children: "Risk threshold enforced" })] }))] })] }) }), _jsxs("div", { className: "flex flex-col gap-6 lg:flex-row lg:items-center", children: [_jsx("div", { className: "flex-1 min-w-[220px]", children: _jsx(AgentRadar, { agent: agent }) }), _jsxs("div", { className: "flex flex-1 flex-col gap-4", children: [_jsx("p", { className: "text-sm text-brand-ice/70 leading-relaxed", children: agentDescription }), _jsx("div", { className: "flex flex-wrap gap-2", children: (agent.symbols ?? []).map((symbol) => {
                                            const meta = resolveTokenMeta(symbol);
                                            return (_jsxs("span", { className: `inline-flex items-center gap-2 rounded-full border border-brand-border/60 bg-gradient-to-r ${meta.gradient} px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-brand-ice shadow-sapphire-sm`, children: [_jsx("span", { className: "rounded-full bg-black/30 px-2 py-0.5 text-[0.65rem]", children: meta.short }), meta.name] }, symbol));
                                        }) })] })] }), _jsxs("div", { className: "flex flex-wrap gap-2", children: [_jsx("span", { className: `inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium ${agent.risk_tolerance === 'extreme' ? 'bg-red-400/20 text-red-300' :
                                    agent.risk_tolerance === 'high' ? 'bg-orange-400/20 text-orange-300' :
                                        agent.risk_tolerance === 'medium' ? 'bg-yellow-400/20 text-yellow-300' :
                                            'bg-green-400/20 text-green-300'}`, children: agent.risk_tolerance?.toUpperCase() || 'MED' }), _jsxs("span", { className: "inline-flex items-center gap-1 rounded-full bg-purple-400/20 px-2 py-1 text-xs font-medium text-purple-300", children: [agent.max_leverage_limit || 3, "x"] }), _jsxs("span", { className: "inline-flex items-center gap-1 rounded-full bg-blue-400/20 px-2 py-1 text-xs font-medium text-blue-300", children: [agent.total_trades, " trades"] })] }), _jsxs("div", { className: "grid grid-cols-1 gap-4 sm:grid-cols-2", children: [_jsxs("div", { className: "rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-4 shadow-sapphire-sm", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.32em] text-brand-ice/50", children: "Cumulative P/L" }), _jsx("p", { className: `mt-1 text-2xl font-semibold ${pnlColor}`, children: formatCurrency(agent.total_pnl) })] }), _jsxs("div", { className: "rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-4 shadow-sapphire-sm", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.32em] text-brand-ice/50", children: "Win Rate" }), _jsx("p", { className: "mt-1 text-2xl font-semibold text-brand-ice", children: Number.isFinite(agent.win_rate) ? `${agent.win_rate.toFixed(1)}%` : '--' })] })] }), onViewHistory && (_jsx("button", { onClick: (e) => {
                            e.stopPropagation();
                            onViewHistory(agent);
                        }, className: "w-full px-4 py-2 text-sm font-medium text-brand-ice bg-brand-accent-blue/20 hover:bg-brand-accent-blue/30 rounded-lg transition-colors border border-brand-accent-blue/30", children: "View Historical Performance \u2192" })), _jsxs("div", { className: "space-y-3", children: [_jsxs("div", { className: "flex items-center justify-between text-xs uppercase tracking-[0.3em] text-brand-ice/50", children: [_jsx("span", { children: "Active Positions" }), _jsx("span", { className: "text-brand-ice", children: activePositions })] }), activePositions > 0 ? (_jsxs("div", { className: "space-y-2", children: [agent.positions.slice(0, 2).map((position, index) => {
                                        const meta = resolveTokenMeta(position.symbol);
                                        return (_jsxs("div", { className: "flex items-center justify-between rounded-xl border border-brand-border/50 bg-brand-abyss/60 p-3 text-xs text-brand-ice", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("div", { className: `flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br ${meta.gradient} text-[0.65rem] font-bold text-brand-ice shadow-sapphire-sm`, children: meta.short }), _jsxs("div", { children: [_jsx("span", { className: "text-sm font-semibold text-brand-ice", children: position.symbol }), _jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.2em] text-brand-ice/50", children: meta.name })] })] }), _jsxs("div", { className: "flex items-center gap-3 text-xs", children: [_jsx("span", { className: `font-medium ${Number(position.pnl) >= 0 ? 'text-brand-accent-green' : 'text-red-400'}`, children: formatPercent(position.pnl_percent ?? 0) }), position.size !== undefined && _jsx("span", { className: "text-brand-ice/60", children: position.size?.toFixed(2) })] })] }, index));
                                    }), activePositions > 2 && _jsxs("p", { className: "text-xs text-brand-ice/60", children: ["+", activePositions - 2, " additional exposures"] })] })) : (_jsx("p", { className: "text-xs text-brand-ice/60", children: "No active positions \\u2013 monitoring order book for optimal entries." }))] }), chartData && chartData.length > 0 && (_jsxs("div", { className: "space-y-2", children: [_jsxs("div", { className: "flex items-center justify-between text-xs uppercase tracking-[0.3em] text-brand-ice/50", children: [_jsx("span", { children: "Equity Curve" }), _jsx("span", { className: "text-brand-ice/60", children: "48h" })] }), _jsx("div", { className: "h-28 rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-2 shadow-sapphire-sm", children: _jsx(AgentChart, { data: chartData, height: 112 }) })] })), _jsxs("div", { className: "flex flex-wrap items-center justify-between gap-2 text-xs text-brand-ice/60", children: [_jsxs("span", { children: ["Last trade: ", lastTrade ? lastTrade.toLocaleTimeString() : '—'] }), _jsxs("span", { children: [agent.total_trades, " trades executed"] })] })] })] }));
};
export default AgentCard;
