import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import ControlsPanel from './components/ControlsPanel';
import ActivityLog from './components/ActivityLog';
import StatusCard from './components/StatusCard';
import PortfolioCard from './components/PortfolioCard';
import PerformanceChart from './components/PerformanceChart';
import RiskMetrics from './components/RiskMetrics';
import ModelPerformance from './components/ModelPerformance';
import ModelReasoning from './components/ModelReasoning';
import LivePositions from './components/LivePositions';
import SystemStatus from './components/SystemStatus';
import TargetsAndAlerts from './components/TargetsAndAlerts';
import PerformanceTrends from './components/PerformanceTrends';
import NotificationCenter from './components/NotificationCenter';
import { useTraderService } from './hooks/useTraderService';
import { fetchDashboard } from './api/client';
const App = () => {
    const { health, loading, error, logs, startTrader, stopTrader, refresh } = useTraderService();
    const [isMobile, setIsMobile] = useState(false);
    const [activeTab, setActiveTab] = useState('overview');
    const [dashboardData, setDashboardData] = useState(null);
    const [dashboardLoading, setDashboardLoading] = useState(true);
    useEffect(() => {
        const checkMobile = () => {
            setIsMobile(window.innerWidth < 768);
        };
        checkMobile();
        window.addEventListener('resize', checkMobile);
        return () => window.removeEventListener('resize', checkMobile);
    }, []);
    // Fetch comprehensive dashboard data
    const fetchDashboardData = async () => {
        try {
            const data = await fetchDashboard();
            setDashboardData(data);
        }
        catch (err) {
            console.error('Failed to fetch dashboard data:', err);
        }
        finally {
            setDashboardLoading(false);
        }
    };
    useEffect(() => {
        fetchDashboardData();
        // Poll for updates every 5 seconds
        const interval = setInterval(fetchDashboardData, 5000);
        return () => clearInterval(interval);
    }, []);
    const tabs = [
        { id: 'overview', label: 'Overview', icon: '📊' },
        { id: 'models', label: 'AI Models', icon: '🤖' },
        { id: 'positions', label: 'Positions', icon: '📈' },
        { id: 'performance', label: 'Performance', icon: '💰' },
        { id: 'system', label: 'System', icon: '⚙️' },
    ];
    return (_jsxs("div", { className: "min-h-screen bg-gradient-to-br from-slate-50 to-slate-100", children: [_jsx("header", { className: "bg-white shadow-sm border-b border-slate-200", children: _jsx("div", { className: "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4", children: _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("div", { className: "flex items-center space-x-3", children: [_jsx("div", { className: "w-8 h-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg flex items-center justify-center", children: _jsx("span", { className: "text-white font-bold text-sm", children: "CT" }) }), _jsxs("div", { children: [_jsx("h1", { className: "text-xl font-bold text-slate-900", children: "Cloud Trader" }), _jsx("p", { className: "text-sm text-slate-500", children: "Autonomous Trading System" })] })] }), _jsxs("div", { className: "flex items-center space-x-4", children: [_jsxs("div", { className: "text-right", children: [_jsx("div", { className: "text-sm text-slate-600", children: "Total P&L" }), _jsxs("div", { className: `text-lg font-bold ${dashboardData?.portfolio?.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`, children: ["$", dashboardData?.portfolio?.total_pnl?.toFixed(2) || '0.00'] })] }), _jsxs("div", { className: "flex items-center space-x-2", children: [_jsx("div", { className: `w-2 h-2 rounded-full ${health?.running ? 'bg-green-500' : 'bg-red-500'}` }), _jsx("span", { className: "text-sm font-medium text-slate-600", children: health?.running ? 'Live' : 'Stopped' })] }), _jsx(NotificationCenter, { alerts: dashboardData?.targets?.alerts || [] }), _jsx("button", { onClick: fetchDashboardData, className: "bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors", children: "\uD83D\uDD04 Refresh" })] })] }) }) }), _jsxs("div", { className: "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6", children: [error && (_jsx("div", { className: "mb-6 bg-red-50 border border-red-200 rounded-lg p-4", children: _jsxs("div", { className: "flex items-center", children: [_jsx("div", { className: "flex-shrink-0", children: _jsx("svg", { className: "h-5 w-5 text-red-400", viewBox: "0 0 20 20", fill: "currentColor", children: _jsx("path", { fillRule: "evenodd", d: "M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z", clipRule: "evenodd" }) }) }), _jsxs("div", { className: "ml-3", children: [_jsx("h3", { className: "text-sm font-medium text-red-800", children: "Connection Error" }), _jsx("p", { className: "text-sm text-red-700 mt-1", children: error })] })] }) })), isMobile && (_jsx("div", { className: "mb-6", children: _jsx("div", { className: "flex space-x-1 bg-slate-100 p-1 rounded-lg", children: tabs.map((tab) => (_jsxs("button", { onClick: () => setActiveTab(tab.id), className: `flex-1 flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md transition-colors ${activeTab === tab.id
                                    ? 'bg-white text-slate-900 shadow-sm'
                                    : 'text-slate-600 hover:text-slate-900'}`, children: [_jsx("span", { className: "mr-1", children: tab.icon }), _jsx("span", { className: "hidden sm:inline", children: tab.label })] }, tab.id))) }) })), dashboardLoading ? (_jsxs("div", { className: "flex items-center justify-center py-12", children: [_jsx("div", { className: "animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" }), _jsx("span", { className: "ml-3 text-slate-600", children: "Loading dashboard data..." })] })) : (_jsxs("div", { className: "space-y-6", children: [activeTab === 'overview' && (_jsxs(_Fragment, { children: [_jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-6", children: [_jsx(StatusCard, { health: health, loading: loading }), _jsx(PortfolioCard, { portfolio: dashboardData?.portfolio })] }), _jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-6", children: [_jsx(PerformanceChart, { data: dashboardData?.recent_trades || [] }), _jsx(RiskMetrics, { positions: dashboardData?.positions || [] })] }), _jsx(TargetsAndAlerts, { targets: dashboardData?.targets }), _jsx(ActivityLog, { logs: logs })] })), activeTab === 'models' && (_jsxs("div", { className: "space-y-6", children: [_jsx(ModelPerformance, { models: dashboardData?.model_performance || [] }), _jsx(ModelReasoning, { reasoning: dashboardData?.model_reasoning || [] })] })), activeTab === 'positions' && (_jsx("div", { className: "space-y-6", children: _jsx(LivePositions, { positions: dashboardData?.positions || [] }) })), activeTab === 'performance' && (_jsxs("div", { className: "space-y-6", children: [_jsx(PerformanceTrends, { trades: dashboardData?.recent_trades || [] }), _jsx(PerformanceChart, { data: dashboardData?.recent_trades || [], detailed: true }), _jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-6", children: [_jsx(RiskMetrics, { positions: dashboardData?.positions || [] }), _jsx(TargetsAndAlerts, { targets: dashboardData?.targets })] })] })), activeTab === 'system' && (_jsxs("div", { className: "space-y-6", children: [_jsx(SystemStatus, { status: dashboardData?.system_status }), _jsx(ControlsPanel, { health: health, loading: loading, onStart: startTrader, onStop: stopTrader, onRefresh: refresh })] }))] }))] })] }));
};
export default App;
