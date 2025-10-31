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
            return 'text-green-600';
        if (confidence >= 0.6)
            return 'text-yellow-600';
        return 'text-red-600';
    };
    const getWinRateColor = (winRate) => {
        if (winRate >= 0.6)
            return 'text-green-600';
        if (winRate >= 0.4)
            return 'text-yellow-600';
        return 'text-red-600';
    };
    const getPerformanceBadge = (winRate, confidence) => {
        const score = (winRate * 0.7) + (confidence * 0.3);
        if (score >= 0.75)
            return { text: 'Excellent', color: 'bg-green-100 text-green-800' };
        if (score >= 0.6)
            return { text: 'Good', color: 'bg-blue-100 text-blue-800' };
        if (score >= 0.45)
            return { text: 'Fair', color: 'bg-yellow-100 text-yellow-800' };
        return { text: 'Needs Improvement', color: 'bg-red-100 text-red-800' };
    };
    const getPnLColor = (pnl) => {
        return pnl >= 0 ? 'text-green-600' : 'text-red-600';
    };
    return (_jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: [_jsxs("div", { className: "flex items-center justify-between mb-6", children: [_jsx("h2", { className: "text-xl font-semibold text-slate-900", children: "AI Model Performance" }), _jsxs("div", { className: "text-sm text-slate-500", children: [models.length, " models active"] })] }), _jsx("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-6", children: models.map((model) => (_jsxs("div", { className: "border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow", children: [_jsx("div", { className: "flex items-center justify-between mb-4", children: _jsxs("div", { className: "flex items-center space-x-3", children: [_jsx("span", { className: "text-2xl", children: getModelIcon(model.model_name) }), _jsxs("div", { children: [_jsxs("div", { className: "flex items-center space-x-2", children: [_jsx("h3", { className: "font-medium text-slate-900", children: model.model_name }), _jsx("span", { className: `px-2 py-1 rounded-full text-xs font-medium ${getPerformanceBadge(model.win_rate, model.avg_confidence).color}`, children: getPerformanceBadge(model.win_rate, model.avg_confidence).text })] }), _jsxs("p", { className: "text-sm text-slate-500", children: ["Last active: ", model.last_decision ? new Date(model.last_decision).toLocaleTimeString() : 'Never'] })] })] }) }), _jsxs("div", { className: "grid grid-cols-2 gap-4", children: [_jsxs("div", { className: "space-y-3", children: [_jsxs("div", { children: [_jsx("div", { className: "text-xs text-slate-500 uppercase tracking-wide", children: "Decisions" }), _jsx("div", { className: "text-lg font-semibold text-slate-900", children: model.total_decisions })] }), _jsxs("div", { children: [_jsx("div", { className: "text-xs text-slate-500 uppercase tracking-wide", children: "Avg Confidence" }), _jsxs("div", { className: `text-lg font-semibold ${getConfidenceColor(model.avg_confidence)}`, children: [(model.avg_confidence * 100).toFixed(1), "%"] })] }), _jsxs("div", { children: [_jsx("div", { className: "text-xs text-slate-500 uppercase tracking-wide", children: "Response Time" }), _jsx("div", { className: "text-lg font-semibold text-slate-900", children: model.avg_response_time > 0 ? `${model.avg_response_time.toFixed(2)}s` : 'N/A' })] })] }), _jsxs("div", { className: "space-y-3", children: [_jsxs("div", { children: [_jsx("div", { className: "text-xs text-slate-500 uppercase tracking-wide", children: "Win Rate" }), _jsxs("div", { className: `text-lg font-semibold ${getWinRateColor(model.win_rate)}`, children: [(model.win_rate * 100).toFixed(1), "%"] })] }), _jsxs("div", { children: [_jsx("div", { className: "text-xs text-slate-500 uppercase tracking-wide", children: "Total P&L" }), _jsxs("div", { className: `text-lg font-semibold ${getPnLColor(model.total_pnl)}`, children: ["$", model.total_pnl.toFixed(2)] })] }), _jsxs("div", { children: [_jsx("div", { className: "text-xs text-slate-500 uppercase tracking-wide", children: "Success Rate" }), _jsxs("div", { className: "text-lg font-semibold text-slate-900", children: [model.total_decisions > 0 ? ((model.successful_trades / model.total_decisions) * 100).toFixed(1) : '0.0', "%"] })] })] })] }), _jsx("div", { className: "mt-4 pt-4 border-t border-slate-100", children: _jsxs("div", { className: "space-y-2", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("span", { className: "text-sm text-slate-600", children: "Overall Score" }), _jsxs("span", { className: "text-sm font-medium text-slate-700", children: [((model.win_rate * 0.7 + model.avg_confidence * 0.3) * 100).toFixed(1), "%"] })] }), _jsx("div", { className: "w-full bg-slate-200 rounded-full h-2", children: _jsx("div", { className: `h-2 rounded-full ${getPerformanceBadge(model.win_rate, model.avg_confidence).text === 'Excellent' ? 'bg-green-500' :
                                                getPerformanceBadge(model.win_rate, model.avg_confidence).text === 'Good' ? 'bg-blue-500' :
                                                    getPerformanceBadge(model.win_rate, model.avg_confidence).text === 'Fair' ? 'bg-yellow-500' : 'bg-red-500'}`, style: { width: `${Math.min((model.win_rate * 0.7 + model.avg_confidence * 0.3) * 100, 100)}%` } }) })] }) })] }, model.model_name))) }), models.length === 0 && (_jsxs("div", { className: "text-center py-8 text-slate-500", children: [_jsx("span", { className: "text-4xl mb-2 block", children: "\uD83E\uDD16" }), _jsx("p", { children: "No model performance data available yet" }), _jsx("p", { className: "text-sm", children: "Models will appear here once they start making trading decisions" })] }))] }));
};
export default ModelPerformance;
