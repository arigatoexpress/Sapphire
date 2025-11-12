import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const ModelReasoning = ({ reasoning }) => {
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
            return 'bg-emerald-500/20 text-emerald-200 border border-emerald-400/40';
        if (confidence >= 0.6)
            return 'bg-amber-500/20 text-amber-200 border border-amber-400/40';
        return 'bg-rose-500/20 text-rose-200 border border-rose-400/40';
    };
    const getDecisionColor = (decision) => {
        switch (decision.toLowerCase()) {
            case 'buy':
                return 'bg-emerald-500/20 text-emerald-200 border border-emerald-400/40';
            case 'sell':
                return 'bg-rose-500/20 text-rose-200 border border-rose-400/40';
            case 'hold':
                return 'bg-slate-500/20 text-slate-200 border border-slate-400/40';
            default:
                return 'bg-sky-500/20 text-sky-200 border border-sky-400/40';
        }
    };
    return (_jsxs("section", { className: "relative overflow-hidden rounded-4xl border border-white/12 bg-surface-75/80 p-6 shadow-glass", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_bottom,_rgba(168,85,247,0.18),_transparent_70%)]" }), _jsxs("div", { className: "relative flex items-center justify-between mb-6", children: [_jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-purple-200/80", children: "Reasoning trace" }), _jsx("h2", { className: "text-2xl font-semibold text-white", children: "AI Model Reasoning" })] }), _jsxs("div", { className: "text-sm font-medium text-slate-200/80", children: [reasoning.length, " recent decisions"] })] }), _jsx("div", { className: "relative space-y-4 max-h-[28rem] overflow-y-auto pr-1", children: reasoning.map((entry, index) => (_jsxs("div", { className: "relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.14),_transparent_70%)]" }), _jsxs("div", { className: "relative flex items-start justify-between mb-3", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("span", { className: "text-xl drop-shadow", children: getModelIcon(entry.model_name) }), _jsxs("div", { children: [_jsxs("div", { className: "flex items-center gap-2", children: [_jsx("span", { className: "text-sm font-semibold text-white", children: entry.model_name }), _jsx("span", { className: `inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[0.65rem] uppercase tracking-[0.2em] ${getDecisionColor(entry.decision)}`, children: entry.decision.toUpperCase() })] }), _jsxs("p", { className: "text-xs text-slate-300/80", children: [entry.symbol, " \u2022 ", new Date(entry.timestamp).toLocaleString()] })] })] }), _jsxs("div", { className: `inline-flex items-center gap-1 rounded-full px-3 py-1 text-[0.65rem] font-medium uppercase tracking-[0.2em] ${getConfidenceColor(entry.confidence)}`, children: [(entry.confidence * 100).toFixed(1), "% Conf."] })] }), _jsxs("div", { className: "relative space-y-3 text-sm", children: [_jsxs("div", { children: [_jsx("span", { className: "text-xs uppercase tracking-[0.28em] text-slate-400", children: "Reasoning" }), _jsx("p", { className: "mt-2 text-slate-200 leading-relaxed", children: entry.reasoning })] }), entry.context && Object.keys(entry.context).length > 0 && (_jsxs("div", { className: "relative mt-3 pt-3 border-t border-white/10", children: [_jsx("span", { className: "text-xs uppercase tracking-[0.28em] text-slate-400", children: "Context" }), _jsx("div", { className: "mt-3 grid grid-cols-2 gap-2 text-xs text-slate-200", children: Object.entries(entry.context).slice(0, 4).map(([key, value]) => (_jsxs("div", { className: "rounded-lg border border-white/10 bg-white/5 px-2 py-1", children: [_jsxs("span", { className: "font-semibold text-slate-100", children: [key, ":"] }), _jsx("span", { className: "ml-1 text-slate-200/90", children: typeof value === 'number' ? value.toFixed(4) : String(value).slice(0, 24) })] }, key))) })] }))] })] }, index))) }), reasoning.length === 0 && (_jsxs("div", { className: "relative text-center py-12 text-slate-300", children: [_jsx("span", { className: "text-4xl mb-2 block", children: "\uD83D\uDCAD" }), _jsx("p", { className: "text-sm", children: "Reasoning transcripts will appear after the next model decision." })] }))] }));
};
export default ModelReasoning;
