import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo } from 'react';
const statusColorMap = {
    active: 'text-emerald-300',
    monitoring: 'text-sky-300',
    idle: 'text-slate-300',
    error: 'text-red-300',
};
const AgentRadar = ({ agent }) => {
    const activeSymbols = useMemo(() => new Set((agent.positions ?? []).map((p) => (p.symbol || '').toUpperCase())), [agent.positions]);
    // Show only active positions + up to 8 example symbols for visual variety
    const tokens = useMemo(() => {
        const allSymbols = agent.symbols ?? [];
        if (allSymbols.length === 0)
            return [];
        const activePositions = Array.from(activeSymbols);
        const availableSymbols = allSymbols.filter(s => !activeSymbols.has(s.toUpperCase()));
        // Prioritize active positions, then add some examples for visual effect
        const displaySymbols = [...activePositions, ...availableSymbols.slice(0, Math.max(0, 12 - activePositions.length))];
        return displaySymbols;
    }, [agent.symbols, activeSymbols]);
    const radarTargets = useMemo(() => {
        if (tokens.length === 0) {
            return [];
        }
        const radius = 42; // percentage of container
        return tokens.map((symbol, index) => {
            const angle = (index / tokens.length) * Math.PI * 2;
            const x = 50 + Math.cos(angle) * radius;
            const y = 50 + Math.sin(angle) * radius;
            const isActive = activeSymbols.has(symbol.toUpperCase());
            return {
                symbol,
                left: `${x}%`,
                top: `${y}%`,
                isActive,
            };
        });
    }, [tokens, activeSymbols]);
    const statusColor = statusColorMap[agent.status?.toLowerCase()] ?? 'text-cyan-300';
    return (_jsxs("div", { className: "relative flex flex-col items-center gap-3", children: [_jsxs("div", { className: "text-center", children: [_jsx("div", { className: "flex items-center justify-center gap-2", children: _jsx("span", { className: `inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.6rem] font-semibold uppercase tracking-[0.28em] ${agent.status === 'active' ? 'bg-emerald-400/20 text-emerald-200' :
                                agent.status === 'monitoring' ? 'bg-sky-400/20 text-sky-200' :
                                    'bg-slate-400/20 text-slate-200'}`, children: agent.status }) }), _jsx("p", { className: "text-[0.65rem] text-slate-400 mt-2", children: agent.symbols?.length ? `${agent.symbols.length} symbols available` : 'Monitoring' })] }), _jsxs("div", { className: "relative h-32 w-32 shrink-0", children: [_jsx("div", { className: "radar-grid" }), _jsx("div", { className: "radar-center-glow" }), _jsx("div", { className: "radar-beam" }), _jsxs("svg", { className: "absolute inset-0", viewBox: "0 0 200 200", role: "presentation", "aria-hidden": "true", children: [_jsx("circle", { cx: "100", cy: "100", r: "94", fill: "none", stroke: "rgba(148, 163, 184, 0.12)", strokeWidth: "0.8" }), _jsx("circle", { cx: "100", cy: "100", r: "70", fill: "none", stroke: "rgba(148, 163, 184, 0.15)", strokeWidth: "0.6" }), _jsx("circle", { cx: "100", cy: "100", r: "46", fill: "none", stroke: "rgba(148, 163, 184, 0.15)", strokeWidth: "0.6" }), _jsx("circle", { cx: "100", cy: "100", r: "22", fill: "none", stroke: "rgba(148, 163, 184, 0.2)", strokeWidth: "0.6" }), _jsx("line", { x1: "100", y1: "8", x2: "100", y2: "192", stroke: "rgba(148, 163, 184, 0.15)", strokeWidth: "0.6" }), _jsx("line", { x1: "8", y1: "100", x2: "192", y2: "100", stroke: "rgba(148, 163, 184, 0.15)", strokeWidth: "0.6" }), _jsx("line", { x1: "34", y1: "34", x2: "166", y2: "166", stroke: "rgba(148, 163, 184, 0.1)", strokeWidth: "0.5" }), _jsx("line", { x1: "166", y1: "34", x2: "34", y2: "166", stroke: "rgba(148, 163, 184, 0.1)", strokeWidth: "0.5" })] }), radarTargets.map((target) => (_jsx("div", { style: { left: target.left, top: target.top }, className: `radar-target absolute flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-cyan-400/40 bg-cyan-500/15 text-xs font-semibold tracking-wide text-cyan-100 backdrop-blur-sm ${target.isActive ? 'text-emerald-200 border-emerald-400/50 bg-emerald-500/20' : ''}` }, target.symbol)))] })] }));
};
export default AgentRadar;
