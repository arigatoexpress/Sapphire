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
            return 'bg-green-100 text-green-800';
        if (confidence >= 0.6)
            return 'bg-yellow-100 text-yellow-800';
        return 'bg-red-100 text-red-800';
    };
    const getDecisionColor = (decision) => {
        switch (decision.toLowerCase()) {
            case 'buy':
                return 'bg-green-100 text-green-800';
            case 'sell':
                return 'bg-red-100 text-red-800';
            case 'hold':
                return 'bg-gray-100 text-gray-800';
            default:
                return 'bg-blue-100 text-blue-800';
        }
    };
    return (_jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: [_jsxs("div", { className: "flex items-center justify-between mb-6", children: [_jsx("h2", { className: "text-xl font-semibold text-slate-900", children: "AI Model Reasoning" }), _jsxs("div", { className: "text-sm text-slate-500", children: [reasoning.length, " recent decisions"] })] }), _jsx("div", { className: "space-y-4 max-h-96 overflow-y-auto", children: reasoning.map((entry, index) => (_jsxs("div", { className: "border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow", children: [_jsxs("div", { className: "flex items-start justify-between mb-3", children: [_jsxs("div", { className: "flex items-center space-x-3", children: [_jsx("span", { className: "text-xl", children: getModelIcon(entry.model_name) }), _jsxs("div", { children: [_jsxs("div", { className: "flex items-center space-x-2", children: [_jsx("span", { className: "font-medium text-slate-900", children: entry.model_name }), _jsx("span", { className: `px-2 py-1 rounded-full text-xs font-medium ${getDecisionColor(entry.decision)}`, children: entry.decision.toUpperCase() })] }), _jsxs("p", { className: "text-sm text-slate-500", children: [entry.symbol, " \u2022 ", new Date(entry.timestamp).toLocaleString()] })] })] }), _jsxs("div", { className: `px-3 py-1 rounded-full text-xs font-medium ${getConfidenceColor(entry.confidence)}`, children: [(entry.confidence * 100).toFixed(1), "% confidence"] })] }), _jsxs("div", { className: "space-y-2", children: [_jsxs("div", { children: [_jsx("span", { className: "text-sm font-medium text-slate-700", children: "Reasoning:" }), _jsx("p", { className: "text-sm text-slate-600 mt-1", children: entry.reasoning })] }), entry.context && Object.keys(entry.context).length > 0 && (_jsxs("div", { className: "mt-3 pt-3 border-t border-slate-100", children: [_jsx("span", { className: "text-sm font-medium text-slate-700", children: "Context:" }), _jsx("div", { className: "mt-2 grid grid-cols-2 gap-2 text-xs", children: Object.entries(entry.context).slice(0, 4).map(([key, value]) => (_jsxs("div", { className: "bg-slate-50 px-2 py-1 rounded", children: [_jsxs("span", { className: "font-medium text-slate-600", children: [key, ":"] }), _jsx("span", { className: "ml-1 text-slate-800", children: typeof value === 'number' ? value.toFixed(4) : String(value).slice(0, 20) })] }, key))) })] }))] })] }, index))) }), reasoning.length === 0 && (_jsxs("div", { className: "text-center py-12 text-slate-500", children: [_jsx("span", { className: "text-4xl mb-2 block", children: "\uD83D\uDCAD" }), _jsx("p", { children: "No reasoning data available yet" }), _jsx("p", { className: "text-sm", children: "Model reasoning will appear here as decisions are made" })] }))] }));
};
export default ModelReasoning;
