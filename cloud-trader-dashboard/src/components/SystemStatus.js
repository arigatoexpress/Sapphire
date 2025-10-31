import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const SystemStatus = ({ status }) => {
    const getStatusColor = (status) => {
        switch (status.toLowerCase()) {
            case 'healthy':
            case 'online':
                return 'bg-green-100 text-green-800';
            case 'unhealthy':
            case 'offline':
                return 'bg-red-100 text-red-800';
            case 'unreachable':
                return 'bg-gray-100 text-gray-800';
            default:
                return 'bg-yellow-100 text-yellow-800';
        }
    };
    const getStatusIcon = (status) => {
        switch (status.toLowerCase()) {
            case 'healthy':
            case 'online':
                return '🟢';
            case 'unhealthy':
            case 'offline':
                return '🔴';
            case 'unreachable':
                return '⚫';
            default:
                return '🟡';
        }
    };
    const services = status?.services || {};
    const models = status?.models || {};
    return (_jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: [_jsxs("div", { className: "flex items-center justify-between mb-6", children: [_jsx("h2", { className: "text-xl font-semibold text-slate-900", children: "System Status" }), _jsxs("div", { className: "flex items-center space-x-2 text-sm text-slate-500", children: [_jsxs("span", { children: ["Last updated: ", status?.timestamp ? new Date(status.timestamp).toLocaleTimeString() : 'Never'] }), _jsx("div", { className: `w-2 h-2 rounded-full ${status?.redis_connected ? 'bg-green-500' : 'bg-red-500'}` })] })] }), _jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-8", children: [_jsxs("div", { children: [_jsxs("h3", { className: "text-lg font-medium text-slate-900 mb-4 flex items-center", children: [_jsx("span", { className: "mr-2", children: "\uD83D\uDD27" }), "Core Services"] }), _jsxs("div", { className: "space-y-3", children: [Object.entries(services).map(([service, status]) => (_jsxs("div", { className: "flex items-center justify-between p-3 bg-slate-50 rounded-lg", children: [_jsxs("div", { className: "flex items-center space-x-3", children: [_jsx("span", { className: "text-lg", children: getStatusIcon(status) }), _jsx("span", { className: "font-medium text-slate-900 capitalize", children: service.replace('_', ' ') })] }), _jsx("span", { className: `px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(status)}`, children: status })] }, service))), Object.keys(services).length === 0 && (_jsx("div", { className: "text-center py-4 text-slate-500", children: _jsx("p", { children: "No service data available" }) }))] })] }), _jsxs("div", { children: [_jsxs("h3", { className: "text-lg font-medium text-slate-900 mb-4 flex items-center", children: [_jsx("span", { className: "mr-2", children: "\uD83E\uDD16" }), "AI Models"] }), _jsxs("div", { className: "space-y-3", children: [Object.entries(models).map(([model, status]) => (_jsxs("div", { className: "flex items-center justify-between p-3 bg-slate-50 rounded-lg", children: [_jsxs("div", { className: "flex items-center space-x-3", children: [_jsx("span", { className: "text-lg", children: getStatusIcon(status) }), _jsx("span", { className: "font-medium text-slate-900", children: model })] }), _jsx("span", { className: `px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(status)}`, children: status })] }, model))), Object.keys(models).length === 0 && (_jsx("div", { className: "text-center py-4 text-slate-500", children: _jsx("p", { children: "No model data available" }) }))] })] })] }), _jsx("div", { className: "mt-6 pt-6 border-t border-slate-200", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { className: "flex items-center space-x-3", children: [_jsx("span", { className: "text-lg", children: status?.redis_connected ? '🟢' : '🔴' }), _jsxs("div", { children: [_jsx("span", { className: "font-medium text-slate-900", children: "Redis Connection" }), _jsx("p", { className: "text-sm text-slate-500", children: "Data streaming and caching" })] })] }), _jsx("span", { className: `px-3 py-1 rounded-full text-sm font-medium ${status?.redis_connected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`, children: status?.redis_connected ? 'Connected' : 'Disconnected' })] }) }), _jsxs("div", { className: "mt-6 grid grid-cols-1 md:grid-cols-3 gap-4", children: [_jsxs("div", { className: "bg-slate-50 rounded-lg p-4 text-center", children: [_jsxs("div", { className: "text-2xl font-bold text-slate-900", children: [Object.values(services).filter(s => s === 'healthy').length, "/", Object.keys(services).length] }), _jsx("div", { className: "text-sm text-slate-600", children: "Services Healthy" })] }), _jsxs("div", { className: "bg-slate-50 rounded-lg p-4 text-center", children: [_jsxs("div", { className: "text-2xl font-bold text-slate-900", children: [Object.values(models).filter(s => s === 'healthy').length, "/", Object.keys(models).length] }), _jsx("div", { className: "text-sm text-slate-600", children: "Models Healthy" })] }), _jsxs("div", { className: "bg-slate-50 rounded-lg p-4 text-center", children: [_jsx("div", { className: `text-2xl font-bold ${status?.redis_connected ? 'text-green-600' : 'text-red-600'}`, children: status?.redis_connected ? '✓' : '✗' }), _jsx("div", { className: "text-sm text-slate-600", children: "Data Pipeline" })] })] })] }));
};
export default SystemStatus;
