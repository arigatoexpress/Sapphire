import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useMemo } from 'react';
import toast, { Toaster } from 'react-hot-toast';
import ControlsPanel from './components/ControlsPanel';
import ActivityLog from './components/ActivityLog';
import StatusCard from './components/StatusCard';
import PortfolioCard from './components/PortfolioCard';
import RiskMetrics from './components/RiskMetrics';
import ModelPerformance from './components/ModelPerformance';
import ModelReasoning from './components/ModelReasoning';
import LivePositions from './components/LivePositions';
import SystemStatus from './components/SystemStatus';
import TargetsAndAlerts from './components/TargetsAndAlerts';
import PerformanceTrends from './components/PerformanceTrends';
import NotificationCenter from './components/NotificationCenter';
import Sidebar from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import MetricCard from './components/MetricCard';
import PortfolioPerformance from './components/charts/PortfolioPerformance';
import { useTraderService } from './hooks/useTraderService';
import { fetchDashboard } from './api/client';
const formatCurrency = (value) => new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
}).format(value);
const App = () => {
    const { health, loading, error, logs, startTrader, stopTrader, refresh } = useTraderService();
    const [activeTab, setActiveTab] = useState('overview');
    const [dashboardData, setDashboardData] = useState(null);
    const [dashboardLoading, setDashboardLoading] = useState(true);
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const fetchDashboardData = async () => {
        try {
            const data = await fetchDashboard();
            setDashboardData(data);
            toast.success('Dashboard data updated', {
                duration: 2000,
                style: {
                    background: 'rgba(15, 23, 42, 0.95)',
                    color: '#cbd5f5',
                    border: '1px solid rgba(34, 211, 238, 0.3)',
                },
            });
        }
        catch (err) {
            console.error('Failed to fetch dashboard data:', err);
            toast.error('Failed to update dashboard data', {
                duration: 4000,
                style: {
                    background: 'rgba(239, 68, 68, 0.95)',
                    color: '#fee2e2',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                },
            });
        }
        finally {
            setDashboardLoading(false);
        }
    };
    useEffect(() => {
        fetchDashboardData();
        const interval = setInterval(fetchDashboardData, 5000);
        return () => clearInterval(interval);
    }, []);
    const derived = useMemo(() => {
        if (!dashboardData) {
            return {
                balance: 0,
                exposure: 0,
                alerts: [],
                positions: [],
            };
        }
        const balance = dashboardData.portfolio?.balance ?? 0;
        const exposure = dashboardData.portfolio?.total_exposure ?? 0;
        const alerts = dashboardData.targets?.alerts ?? [];
        const positions = dashboardData.positions ?? [];
        return { balance, exposure, alerts, positions };
    }, [dashboardData]);
    const performanceSeries = useMemo(() => {
        if (!dashboardData?.recent_trades?.length) {
            return { balance: [], price: [] };
        }
        const trades = dashboardData.recent_trades;
        let runningBalance = derived.balance || 1000;
        const balanceSeries = trades.map((trade, index) => {
            const timestamp = trade.timestamp ?? new Date(Date.now() - (trades.length - index) * 60_000).toISOString();
            const signedNotional = (trade.quantity ?? 0) * (trade.price ?? 0) * (trade.side === 'SELL' ? -1 : 1);
            runningBalance = Math.max(runningBalance + signedNotional * 0.001, 0);
            return {
                timestamp,
                balance: runningBalance,
            };
        });
        const priceSeries = trades.map((trade, index) => ({
            timestamp: trade.timestamp ?? new Date(Date.now() - (trades.length - index) * 60_000).toISOString(),
            price: trade.price ?? 0,
        }));
        return { balance: balanceSeries, price: priceSeries };
    }, [dashboardData, derived.balance]);
    const tabs = [
        { id: 'overview', label: 'Overview', icon: '📊' },
        { id: 'models', label: 'AI Models', icon: '🤖' },
        { id: 'positions', label: 'Positions', icon: '📈' },
        { id: 'performance', label: 'Performance', icon: '💰' },
        { id: 'system', label: 'System', icon: '⚙️' },
    ];
    const sidebarTabs = tabs.map((tab) => ({ id: tab.id, label: tab.label, icon: tab.icon }));
    return (_jsxs("div", { className: "min-h-screen bg-surface-50 text-slate-200", children: [_jsx(Toaster, { position: "top-right", toastOptions: {
                    style: {
                        background: 'rgba(15, 23, 42, 0.95)',
                        color: '#cbd5f5',
                        border: '1px solid rgba(148, 163, 184, 0.3)',
                        backdropFilter: 'blur(10px)',
                    },
                } }), _jsxs("div", { className: "flex min-h-screen bg-gradient-to-br from-surface-100 via-surface-50 to-surface-50", children: [_jsx(Sidebar, { tabs: sidebarTabs, activeTab: activeTab, onSelect: (id) => setActiveTab(id), mobileMenuOpen: mobileMenuOpen, setMobileMenuOpen: setMobileMenuOpen }), _jsxs("div", { className: "flex flex-1 flex-col", children: [_jsx(TopBar, { onRefresh: fetchDashboardData, lastUpdated: dashboardData?.system_status?.timestamp, healthRunning: health?.running, mobileMenuOpen: mobileMenuOpen, setMobileMenuOpen: setMobileMenuOpen }), _jsxs("main", { className: "flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-10", children: [_jsx("div", { className: "flex justify-end", children: _jsx(NotificationCenter, { alerts: derived.alerts }) }), error && (_jsxs("div", { className: "mb-6 rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-100", children: [_jsx("p", { className: "font-semibold", children: "Connection Error" }), _jsx("p", { className: "mt-1 text-red-200/80", children: error })] })), dashboardLoading ? (_jsxs("div", { className: "space-y-8", children: [_jsx("div", { className: "grid grid-cols-1 gap-4 md:grid-cols-3", children: [1, 2, 3].map((i) => (_jsx("div", { className: "relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass", children: _jsxs("div", { className: "animate-pulse", children: [_jsx("div", { className: "h-3 bg-slate-600/40 rounded mb-2" }), _jsx("div", { className: "h-8 bg-slate-600/40 rounded mb-4" }), _jsx("div", { className: "h-3 bg-slate-600/40 rounded w-2/3" })] }) }, i))) }), _jsxs("div", { className: "grid grid-cols-1 gap-6 xl:grid-cols-3", children: [_jsx("div", { className: "xl:col-span-2 relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass", children: _jsxs("div", { className: "animate-pulse", children: [_jsx("div", { className: "h-4 bg-slate-600/40 rounded mb-2 w-1/3" }), _jsx("div", { className: "h-6 bg-slate-600/40 rounded mb-4 w-1/2" }), _jsx("div", { className: "h-64 bg-slate-600/40 rounded" })] }) }), _jsx("div", { className: "relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass", children: _jsxs("div", { className: "animate-pulse", children: [_jsx("div", { className: "h-4 bg-slate-600/40 rounded mb-2" }), _jsx("div", { className: "space-y-3", children: [1, 2, 3].map((i) => (_jsx("div", { className: "h-3 bg-slate-600/40 rounded" }, i))) })] }) })] }), _jsx("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-2", children: [1, 2].map((i) => (_jsx("div", { className: "relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass", children: _jsxs("div", { className: "animate-pulse", children: [_jsx("div", { className: "h-4 bg-slate-600/40 rounded mb-2 w-1/3" }), _jsx("div", { className: "h-6 bg-slate-600/40 rounded mb-4 w-1/2" }), _jsx("div", { className: "space-y-3", children: [1, 2, 3, 4].map((j) => (_jsx("div", { className: "h-3 bg-slate-600/40 rounded" }, j))) })] }) }, i))) })] })) : (_jsxs("div", { className: "space-y-8", children: [activeTab === 'overview' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("div", { className: "grid grid-cols-1 gap-4 md:grid-cols-3", children: [_jsx(MetricCard, { label: "Account Balance", value: formatCurrency(derived.balance), accent: "emerald", footer: _jsxs("span", { children: ["Exposure coverage ratio ", (derived.exposure / (derived.balance || 1) * 100).toFixed(1), "%"] }) }), _jsx(MetricCard, { label: "Gross Exposure", value: formatCurrency(derived.exposure), accent: "teal", footer: _jsxs("span", { children: [derived.positions.length, " instruments allocated"] }) }), _jsx(MetricCard, { label: "AI Alerts", value: derived.alerts.length, accent: "amber", footer: _jsx("span", { children: "Powered by orchestrator health checks" }) })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 xl:grid-cols-3", children: [_jsxs("div", { className: "xl:col-span-2 rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass", children: [_jsx("div", { className: "mb-4 flex items-center justify-between", children: _jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Performance Lens" }), _jsx("h3", { className: "mt-2 text-xl font-semibold text-white", children: "Portfolio & Benchmark" })] }) }), _jsx(PortfolioPerformance, { balanceSeries: performanceSeries.balance, priceSeries: performanceSeries.price })] }), _jsx(TargetsAndAlerts, { targets: dashboardData?.targets })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-2", children: [_jsx(StatusCard, { health: health, loading: loading }), _jsx(PortfolioCard, { portfolio: dashboardData?.portfolio })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-2", children: [_jsx(RiskMetrics, { portfolio: dashboardData?.portfolio }), _jsx(ActivityLog, { logs: logs })] })] })), activeTab === 'models' && (_jsxs("div", { className: "space-y-6", children: [_jsx(ModelPerformance, { models: dashboardData?.model_performance || [] }), _jsx(ModelReasoning, { reasoning: dashboardData?.model_reasoning || [] })] })), activeTab === 'positions' && (_jsx("div", { className: "space-y-6", children: _jsx(LivePositions, { positions: derived.positions }) })), activeTab === 'performance' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass", children: [_jsx("h3", { className: "text-lg font-semibold text-white", children: "Balance Trajectory" }), _jsx("p", { className: "mt-1 text-sm text-slate-400", children: "Overlay of account balance vs indicative price ladder." }), _jsx("div", { className: "mt-4", children: _jsx(PortfolioPerformance, { balanceSeries: performanceSeries.balance, priceSeries: performanceSeries.price }) })] }), _jsx(PerformanceTrends, { trades: dashboardData?.recent_trades || [] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-2", children: [_jsx(RiskMetrics, { portfolio: dashboardData?.portfolio }), _jsx(TargetsAndAlerts, { targets: dashboardData?.targets })] })] })), activeTab === 'system' && (_jsxs("div", { className: "space-y-6", children: [_jsx(SystemStatus, { status: dashboardData?.system_status }), _jsx(ControlsPanel, { health: health, loading: loading, onStart: startTrader, onStop: stopTrader, onRefresh: refresh })] }))] }))] })] })] })] }));
};
export default App;
