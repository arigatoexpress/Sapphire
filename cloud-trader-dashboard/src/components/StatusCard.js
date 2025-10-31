import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const StatusCard = ({ health, loading }) => {
    if (loading || !health) {
        return _jsx("div", { className: "bg-gray-200 p-4 rounded-md text-center", children: "Loading status..." });
    }
    const statusColor = health.running ? 'success' : 'error';
    return (_jsxs("div", { className: "bg-white border border-gray-200 rounded-md p-4 space-y-2", children: [_jsxs("div", { className: "flex items-center", children: [_jsx("h2", { className: "text-lg font-semibold", children: "Status:" }), _jsx("span", { className: `ml-2 text-${statusColor} font-bold`, children: health.running ? 'Running' : 'Stopped' }), health.paper_trading && (_jsx("span", { className: "ml-2 px-2 py-1 bg-warning text-white text-xs rounded-full", children: "Paper Trading" }))] }), health.last_error && _jsxs("div", { className: "text-error", children: ["Last Error: ", health.last_error] })] }));
};
export default StatusCard;
