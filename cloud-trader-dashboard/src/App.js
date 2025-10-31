import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import ControlsPanel from './components/ControlsPanel';
import ActivityLog from './components/ActivityLog';
import StatusCard from './components/StatusCard';
import PortfolioCard from './components/PortfolioCard';
import PerformanceChart from './components/PerformanceChart';
import RiskMetrics from './components/RiskMetrics';
import { useTraderService } from './hooks/useTraderService';
const App = () => {
    const { health, loading, error, logs, startTrader, stopTrader, refresh } = useTraderService();
    const [isMobile, setIsMobile] = useState(false);
    const [activeTab, setActiveTab] = useState('overview');
    useEffect(() => {
        const checkMobile = () => {
            setIsMobile(window.innerWidth < 768);
        };
        checkMobile();
        window.addEventListener('resize', checkMobile);
        return () => window.removeEventListener('resize', checkMobile);
    }, []);
    const tabs = [
        { id: 'overview', label: 'Overview', icon: '📊' },
        { id: 'portfolio', label: 'Portfolio', icon: '💼' },
        { id: 'performance', label: 'Performance', icon: '📈' },
        { id: 'logs', label: 'Activity', icon: '📝' },
    ];
    return (_jsxs("div", { className: "min-h-screen bg-gradient-to-br from-slate-50 to-slate-100", children: [_jsx("header", { className: "bg-white shadow-sm border-b border-slate-200", children: _jsx("div", { className: "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { className: "flex items-center space-x-3", children: [_jsx("div", { className: "w-8 h-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg flex items-center justify-center", children: _jsx("span", { className: "text-white font-bold text-sm", children: "CT" }) }), _jsxs("div", { children: [_jsx("h1", { className: "text-xl font-bold text-slate-900", children: "Cloud Trader" }), _jsx("p", { className: "text-sm text-slate-500", children: "Autonomous Trading System" })] })] }), _jsxs("div", { className: "flex items-center space-x-2", children: [_jsx("div", { className: `w-2 h-2 rounded-full ${health?.running ? 'bg-green-500' : 'bg-red-500'}` }), _jsx("span", { className: "text-sm font-medium text-slate-600", children: health?.running ? 'Live' : 'Stopped' })] })] }) }) }), _jsxs("div", { className: "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6", children: [error && (_jsx("div", { className: "mb-6 bg-red-50 border border-red-200 rounded-lg p-4", children: _jsxs("div", { className: "flex items-center", children: [_jsx("div", { className: "flex-shrink-0", children: _jsx("svg", { className: "h-5 w-5 text-red-400", viewBox: "0 0 20 20", fill: "currentColor", children: _jsx("path", { fillRule: "evenodd", d: "M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z", clipRule: "evenodd" }) }) }), _jsxs("div", { className: "ml-3", children: [_jsx("h3", { className: "text-sm font-medium text-red-800", children: "Connection Error" }), _jsx("p", { className: "text-sm text-red-700 mt-1", children: error })] })] }) })), isMobile && (_jsx("div", { className: "mb-6", children: _jsx("div", { className: "flex space-x-1 bg-slate-100 p-1 rounded-lg", children: tabs.map((tab) => (_jsxs("button", { onClick: () => setActiveTab(tab.id), className: `flex-1 flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md transition-colors ${activeTab === tab.id
                                    ? 'bg-white text-slate-900 shadow-sm'
                                    : 'text-slate-600 hover:text-slate-900'}`, children: [_jsx("span", { className: "mr-1", children: tab.icon }), _jsx("span", { className: "hidden sm:inline", children: tab.label })] }, tab.id))) }) })), _jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-3 gap-6", children: [_jsxs("div", { className: `${isMobile ? 'col-span-1' : 'lg:col-span-2'} space-y-6`, children: [(activeTab === 'overview' || !isMobile) && (_jsxs(_Fragment, { children: [_jsxs("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-6", children: [_jsx(StatusCard, { health: health, loading: loading }), _jsx(ControlsPanel, { health: health, loading: loading, onStart: startTrader, onStop: stopTrader, onRefresh: refresh })] }), !isMobile && (_jsxs(_Fragment, { children: [_jsx(PortfolioCard, {}), _jsx(PerformanceChart, {})] }))] })), activeTab === 'portfolio' && isMobile && _jsx(PortfolioCard, {}), activeTab === 'performance' && isMobile && _jsx(PerformanceChart, {}), activeTab === 'logs' && _jsx(ActivityLog, { logs: logs })] }), !isMobile && (_jsxs("div", { className: "space-y-6", children: [_jsx(RiskMetrics, {}), _jsxs("div", { className: "bg-white rounded-lg shadow-sm border border-slate-200 p-6", children: [_jsx("h3", { className: "text-lg font-semibold text-slate-900 mb-4", children: "Quick Actions" }), _jsxs("div", { className: "space-y-3", children: [_jsxs("button", { onClick: refresh, disabled: loading, className: "w-full flex items-center justify-center px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors disabled:opacity-50", children: [_jsx("svg", { className: "w-4 h-4 mr-2", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" }) }), "Refresh Data"] }), _jsxs("button", { onClick: () => window.location.reload(), className: "w-full flex items-center justify-center px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors", children: [_jsx("svg", { className: "w-4 h-4 mr-2", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" }) }), "Reload Dashboard"] })] })] })] }))] })] })] }));
};
export default App;
