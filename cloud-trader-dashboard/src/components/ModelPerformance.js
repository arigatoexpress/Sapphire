import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const ModelPerformance = ({ models }) => {
    const getModelIcon = (modelName) => {
        const icons = {
            'DeepSeek-Coder-V2': '🧠',
            'Qwen2.5-Coder': '🧮',
            'FinGPT': '💰',
            'Phi-3': '🔬'
        };
        return icons[modelName] || '🤖';
    };
    const getConfidenceColor = (confidence) => {
        if (confidence >= 0.8)
            return 'text-emerald-300';
        if (confidence >= 0.6)
            return 'text-amber-200';
        return 'text-rose-300';
    };
    const getWinRateColor = (winRate) => {
        if (winRate >= 0.6)
            return 'text-emerald-300';
        if (winRate >= 0.4)
            return 'text-amber-200';
        return 'text-rose-300';
    };
    const getPerformanceBadge = (winRate, confidence) => {
        const score = (winRate * 0.7) + (confidence * 0.3);
        if (score >= 0.75)
            return { text: 'Elite', color: 'bg-emerald-500/20 text-emerald-200 border border-emerald-400/40' };
        if (score >= 0.6)
            return { text: 'Strong', color: 'bg-sky-500/20 text-sky-200 border border-sky-400/40' };
        if (score >= 0.45)
            return { text: 'Developing', color: 'bg-amber-500/20 text-amber-200 border border-amber-400/40' };
        return { text: 'Calibration Needed', color: 'bg-rose-500/20 text-rose-200 border border-rose-400/40' };
    };
    const getPnLColor = (pnl) => {
        return pnl >= 0 ? 'text-emerald-300' : 'text-rose-300';
    };
    return (_jsxs("section", { className: "relative overflow-hidden rounded-4xl border border-white/12 bg-surface-75/80 p-6 shadow-glass", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(45,212,191,0.18),_transparent_70%)]" }), _jsxs("div", { className: "relative flex items-center justify-between mb-6", children: [_jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-emerald-200/80", children: "Model mesh telemetry" }), _jsx("h2", { className: "text-2xl font-semibold text-white", children: "AI Model Performance" })] }), _jsxs("div", { className: "text-sm font-medium text-slate-200/80", children: [models.length, " active"] })] }), _jsx("div", { className: "relative grid grid-cols-1 md:grid-cols-2 gap-6", children: models.map((model) => {
                    const badge = getPerformanceBadge(model.win_rate, model.avg_confidence);
                    const compositeScore = (model.win_rate * 0.7 + model.avg_confidence * 0.3) * 100;
                    return (_jsxs("div", { className: "relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm transition-transform hover:-translate-y-0.5", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.16),_transparent_65%)]" }), _jsx("div", { className: "relative flex items-center justify-between mb-4", children: _jsxs("div", { className: "flex items-center gap-3", children: [_jsx("span", { className: "text-2xl drop-shadow", children: getModelIcon(model.model_name) }), _jsxs("div", { children: [_jsxs("div", { className: "flex items-center gap-2", children: [_jsx("h3", { className: "text-lg font-semibold text-white", children: model.model_name }), _jsx("span", { className: `inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[0.65rem] uppercase tracking-[0.2em] ${badge.color}`, children: badge.text })] }), _jsxs("p", { className: "text-xs text-slate-300/80", children: ["Last active ", model.last_decision ? new Date(model.last_decision).toLocaleTimeString() : '—'] })] })] }) }), _jsxs("div", { className: "grid grid-cols-2 gap-4", children: [_jsxs("div", { className: "space-y-3", children: [_jsxs("div", { children: [_jsx("div", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Decisions" }), _jsx("div", { className: "mt-1 text-xl font-semibold text-white", children: model.total_decisions })] }), _jsxs("div", { children: [_jsx("div", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Avg Confidence" }), _jsxs("div", { className: `mt-1 text-xl font-semibold ${getConfidenceColor(model.avg_confidence)}`, children: [(model.avg_confidence * 100).toFixed(1), "%"] })] }), _jsxs("div", { children: [_jsx("div", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Response Time" }), _jsx("div", { className: "mt-1 text-xl font-semibold text-slate-200", children: model.avg_response_time > 0 ? `${model.avg_response_time.toFixed(2)}s` : 'N/A' })] })] }), _jsxs("div", { className: "space-y-3", children: [_jsxs("div", { children: [_jsx("div", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Win Rate" }), _jsxs("div", { className: `mt-1 text-xl font-semibold ${getWinRateColor(model.win_rate)}`, children: [(model.win_rate * 100).toFixed(1), "%"] })] }), _jsxs("div", { children: [_jsx("div", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Total P&L" }), _jsxs("div", { className: `mt-1 text-xl font-semibold ${getPnLColor(model.total_pnl)}`, children: [model.total_pnl >= 0 ? '+' : '-', "$", Math.abs(model.total_pnl).toFixed(2)] })] }), _jsxs("div", { children: [_jsx("div", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Success Rate" }), _jsxs("div", { className: "mt-1 text-xl font-semibold text-slate-200", children: [model.total_decisions > 0 ? ((model.successful_trades / model.total_decisions) * 100).toFixed(1) : '0.0', "%"] })] })] })] }), _jsxs("div", { className: "relative mt-4 pt-4 border-t border-white/10", children: [_jsxs("div", { className: "flex items-center justify-between text-sm text-slate-300", children: [_jsx("span", { children: "Composite Fidelity" }), _jsxs("span", { className: "font-semibold text-white/90", children: [compositeScore.toFixed(1), "%"] })] }), _jsx("div", { className: "mt-3 h-2 w-full rounded-full bg-white/10", children: _jsx("div", { className: `h-2 rounded-full ${badge.text === 'Elite'
                                                ? 'bg-emerald-400'
                                                : badge.text === 'Strong'
                                                    ? 'bg-sky-400'
                                                    : badge.text === 'Developing'
                                                        ? 'bg-amber-400'
                                                        : 'bg-rose-400'}`, style: { width: `${Math.min(compositeScore, 100)}%` } }) })] })] }, model.model_name));
                }) }), models.length === 0 && (_jsxs("div", { className: "relative text-center py-10 text-slate-300", children: [_jsx("span", { className: "text-4xl mb-2 block", children: "\uD83E\uDD16" }), _jsx("p", { className: "text-sm", children: "Model telemetry will populate after the first live decisions." })] }))] }));
};
export default ModelPerformance;
