import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const ControlsPanel = ({ health, loading, onStart, onStop, onRefresh }) => {
    const isRunning = health?.running ?? false;
    const disabled = loading;
    return (_jsxs("div", { className: "flex justify-center gap-4 flex-wrap", children: [_jsx("button", { onClick: onStart, disabled: disabled || isRunning, className: "px-4 py-2 bg-success text-white rounded-md disabled:opacity-50", "aria-label": "Start Trader", children: "Start" }), _jsx("button", { onClick: onStop, disabled: disabled || !isRunning, className: "px-4 py-2 bg-error text-white rounded-md disabled:opacity-50", "aria-label": "Stop Trader", children: "Stop" }), _jsx("button", { onClick: onRefresh, disabled: loading, className: "px-4 py-2 bg-primary text-white rounded-md disabled:opacity-50", "aria-label": "Refresh Status", children: "Refresh" })] }));
};
export default ControlsPanel;
