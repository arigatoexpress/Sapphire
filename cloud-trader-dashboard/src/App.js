import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import React, { Suspense, lazy, useState, useMemo } from 'react';
import toast, { Toaster } from 'react-hot-toast';
import StatusCard from './components/StatusCard';
import RiskMetrics from './components/RiskMetrics';
import Sidebar from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import MetricCard from './components/MetricCard';
import PortfolioPerformance from './components/charts/PortfolioPerformance';
import AuroraField from './components/visuals/AuroraField';
import { resolveTokenMeta } from './utils/tokenMeta';
import { useTraderService } from './hooks/useTraderService';
import AgentCard from './components/AgentCard';
import CrowdSentimentWidget from './components/CrowdSentimentWidget';
import useCrowdSentiment from './hooks/useCrowdSentiment';
import useCommunityComments from './hooks/useCommunityComments';
import useAuth from './hooks/useAuth';
import LandingPage from './components/LandingPage';
const ActivityLog = lazy(() => import('./components/ActivityLog'));
const ModelPerformance = lazy(() => import('./components/ModelPerformance'));
const ModelReasoning = lazy(() => import('./components/ModelReasoning'));
const LivePositions = lazy(() => import('./components/LivePositions'));
const SystemStatus = lazy(() => import('./components/SystemStatus'));
const TargetsAndAlerts = lazy(() => import('./components/TargetsAndAlerts'));
const PerformanceTrends = lazy(() => import('./components/PerformanceTrends'));
const MCPCouncil = lazy(() => import('./components/MCPCouncil'));
const NotificationCenter = lazy(() => import('./components/NotificationCenter'));
const formatCurrency = (value) => new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
}).format(value);
const formatNumber = (value) => new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 0,
}).format(value);
const formatMaskedPortfolioValue = (_value) => '%s';
const SectionSkeleton = ({ title, className }) => (_jsxs("div", { className: `rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-glass animate-pulse ${className ?? ''}`, children: [title && _jsx("div", { className: "mb-5 h-3 w-40 rounded-full bg-white/20" }), _jsxs("div", { className: "space-y-4", children: [_jsx("div", { className: "h-4 w-full rounded-full bg-white/10" }), _jsx("div", { className: "h-4 w-5/6 rounded-full bg-white/10" }), _jsx("div", { className: "h-4 w-4/6 rounded-full bg-white/10" })] })] }));
const DashboardSkeleton = () => (_jsxs("div", { className: "space-y-8", children: [_jsx(SectionSkeleton, { title: "Calibrating control nexus" }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-3", children: [_jsx(SectionSkeleton, { className: "h-40" }), _jsx(SectionSkeleton, { className: "h-40" }), _jsx(SectionSkeleton, { className: "h-40" })] }), _jsx(SectionSkeleton, { title: "Streaming live trade telemetry", className: "h-80" }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-2", children: [_jsx(SectionSkeleton, { className: "h-72" }), _jsx(SectionSkeleton, { className: "h-72" })] })] }));
const CLOUD_RUN_REGION = 'us-central1';
const LOAD_BALANCER_IP = '34.117.165.111';
const TPU_FLEET_DESCRIPTION = 'LLM serving pods (DeepSeek, Qwen, Phi-3) TPU-ready via vLLM/llama.cpp stack';
const App = () => {
    const { user, loading: authLoading, signIn, signOut, enabled: authEnabled, error: authError } = useAuth();
    const { health, dashboardData, loading, error, logs, connectionStatus, mcpMessages, mcpStatus, refresh } = useTraderService();
    const [crowdSentiment, castCrowdVote, resetCrowd] = useCrowdSentiment();
    const [communityComments, addCommunityComment] = useCommunityComments(user);
    const [activeTab, setActiveTab] = useState('overview');
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [showLandingPage, setShowLandingPage] = useState(true);
    const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
    const handleEnterApp = () => {
        setShowLandingPage(false);
    };
    // Keyboard shortcuts
    React.useEffect(() => {
        const handleKeyDown = (event) => {
            // Ctrl+R or Cmd+R to refresh data
            if ((event.ctrlKey || event.metaKey) && event.key === 'r') {
                event.preventDefault();
                refresh();
            }
            // Escape to go back to landing page
            if (event.key === 'Escape' && !showLandingPage) {
                setShowLandingPage(true);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [refresh, showLandingPage]);
    const derived = useMemo(() => {
        if (!dashboardData) {
            return {
                balance: 0,
                exposure: 0,
                availableBalance: 0,
                alerts: [],
                positions: [],
                agents: [],
                totalAgentPnL: 0,
                activeAgents: 0,
            };
        }
        const balance = dashboardData.portfolio?.balance ?? 0;
        const exposure = dashboardData.portfolio?.total_exposure ?? 0;
        const alerts = dashboardData.targets?.alerts ?? [];
        const positions = dashboardData.positions ?? [];
        const agents = dashboardData.agents ?? [];
        const totalAgentPnL = agents.reduce((acc, agent) => acc + (agent.total_pnl ?? 0), 0);
        const activeAgents = agents.filter((agent) => agent.status === 'active').length;
        const availableBalance = dashboardData.portfolio?.available_balance ?? Math.max(balance - exposure, 0);
        return { balance, exposure, availableBalance, alerts, positions, agents, totalAgentPnL, activeAgents };
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
    const positionInsights = useMemo(() => {
        if (!derived.positions.length) {
            return {
                longCount: 0,
                shortCount: 0,
                holdCount: 0,
                totalNotional: 0,
                netNotional: 0,
                sentiment: 'No live exposure',
                topSymbols: [],
            };
        }
        let longCount = 0;
        let shortCount = 0;
        let holdCount = 0;
        let totalNotional = 0;
        let netNotional = 0;
        const symbolMap = new Map();
        derived.positions.forEach((pos) => {
            const side = String(pos.side ?? '').toUpperCase();
            const notional = Math.abs(Number(pos.notional) || 0);
            if (side === 'SELL' || side === 'SHORT') {
                shortCount += 1;
                netNotional -= notional;
            }
            else if (side === 'BUY' || side === 'LONG') {
                longCount += 1;
                netNotional += notional;
            }
            else {
                holdCount += 1;
            }
            totalNotional += notional;
            const symbol = String(pos.symbol ?? 'UNKNOWN').toUpperCase();
            symbolMap.set(symbol, (symbolMap.get(symbol) ?? 0) + notional);
        });
        const topSymbols = Array.from(symbolMap.entries())
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(([symbol, notional]) => ({ symbol, notional }));
        let sentiment = 'Market Neutral';
        if (netNotional > 0) {
            sentiment = 'Net Long Bias';
        }
        else if (netNotional < 0) {
            sentiment = 'Net Short Bias';
        }
        return {
            longCount,
            shortCount,
            holdCount,
            totalNotional,
            netNotional,
            sentiment,
            topSymbols,
        };
    }, [derived.positions]);
    const performanceInsights = useMemo(() => {
        const trades = (dashboardData?.recent_trades ?? []);
        if (!trades.length) {
            return {
                totalTrades: 0,
                winRate: 0,
                totalNotional: 0,
                averageNotional: 0,
                sentiment: 'Awaiting execution',
                lastTrade: null,
            };
        }
        let wins = 0;
        let totalNotional = 0;
        let longCount = 0;
        let shortCount = 0;
        trades.forEach((trade) => {
            const pnl = Number(trade.pnl) || 0;
            if (pnl > 0)
                wins += 1;
            const notional = Math.abs(Number(trade.notional) || 0);
            totalNotional += notional;
            const side = String(trade.side ?? '').toUpperCase();
            if (side === 'BUY' || side === 'LONG')
                longCount += 1;
            if (side === 'SELL' || side === 'SHORT')
                shortCount += 1;
        });
        const winRate = trades.length ? (wins / trades.length) * 100 : 0;
        const averageNotional = trades.length ? totalNotional / trades.length : 0;
        let sentiment = 'Balanced flow';
        if (longCount > shortCount)
            sentiment = 'Long skew';
        if (shortCount > longCount)
            sentiment = 'Short skew';
        return {
            totalTrades: trades.length,
            winRate,
            totalNotional,
            averageNotional,
            sentiment,
            lastTrade: trades[0]?.timestamp ?? null,
        };
    }, [dashboardData?.recent_trades]);
    const activitySummary = useMemo(() => {
        if (!logs.length) {
            return {
                total: 0,
                counts: { info: 0, success: 0, warning: 0, error: 0 },
                lastEntry: null,
            };
        }
        const counts = logs.reduce((acc, log) => ({ ...acc, [log.type]: (acc[log.type] ?? 0) + 1 }), { info: 0, success: 0, warning: 0, error: 0 });
        return {
            total: logs.length,
            counts,
            lastEntry: logs[0],
        };
    }, [logs]);
    const systemStatus = dashboardData?.system_status;
    const systemSummary = useMemo(() => {
        const orchestratorStatus = systemStatus?.services?.orchestrator ?? 'unknown';
        const traderStatus = systemStatus?.services?.cloud_trader ?? 'unknown';
        const redisConnected = systemStatus?.redis_connected ?? false;
        return {
            orchestratorStatus,
            traderStatus,
            redisConnected,
            timestamp: systemStatus?.timestamp ?? null,
        };
    }, [systemStatus]);
    const configuredAgents = derived.agents.length || 4;
    const recentTradeCount = dashboardData?.recent_trades?.length ?? 0;
    const orchestratorStatus = systemStatus?.services?.orchestrator ?? 'unknown';
    const traderStatus = systemStatus?.services?.cloud_trader ?? 'unknown';
    const redisOnline = systemStatus?.redis_connected ?? false;
    const latestLog = logs.length ? logs[0] : null;
    const lastHeartbeat = systemStatus?.timestamp
        ? new Date(systemStatus.timestamp).toLocaleTimeString()
        : '—';
    const infrastructureMetrics = [
        {
            label: 'Cloud Run Region',
            value: CLOUD_RUN_REGION,
            detail: 'wallet-orchestrator · cloud-trader',
        },
        {
            label: 'Load Balancer IP',
            value: LOAD_BALANCER_IP,
            detail: 'Whitelist for Aster API access',
        },
        {
            label: 'Redis Telemetry Bus',
            value: redisOnline ? 'Online' : 'Offline',
            tone: redisOnline ? 'text-emerald-300' : 'text-red-300',
            detail: 'Portfolio cache · decision streams',
        },
        {
            label: 'Last Heartbeat',
            value: lastHeartbeat,
            detail: 'system_status timestamp (UTC)',
        },
    ];
    const tradingMetrics = [
        {
            label: 'Agents Live',
            value: `${derived.activeAgents}/${configuredAgents}`,
            detail: 'DeepSeek Momentum · Qwen Adaptive · Strategist · Guardian',
        },
        {
            label: 'Recent Trades (24h)',
            value: formatNumber(recentTradeCount),
            detail: 'Orders reconciled through orchestrator',
        },
        {
            label: 'Total Agent P&L',
            value: formatCurrency(derived.totalAgentPnL),
            detail: 'Aggregated across all vibe traders',
        },
        {
            label: 'Trader Runtime',
            value: traderStatus,
            detail: 'Cloud Run service health state',
        },
    ];
    const modelOpsMetrics = [
        {
            label: 'TPU / GPU Fleet',
            value: 'Hybrid',
            detail: TPU_FLEET_DESCRIPTION,
        },
        {
            label: 'LLM Stack',
            value: 'DeepSeek · Qwen · Phi-3',
            detail: 'Multi-agent reasoning ensemble',
        },
        {
            label: 'Orchestrator',
            value: orchestratorStatus,
            detail: 'Risk engine + emergency stop',
        },
        {
            label: 'Latest Event',
            value: latestLog ? latestLog.message : 'Idle',
            detail: latestLog ? new Date(latestLog.timestamp).toLocaleString() : 'Awaiting telemetry',
        },
    ];
    const tabs = [
        { id: 'overview', label: 'Live Trading', icon: '🚀' },
        { id: 'positions', label: 'Positions', icon: '📈' },
        { id: 'performance', label: 'Performance', icon: '💰' },
        { id: 'activity', label: 'Activity Log', icon: '📋' },
        { id: 'system', label: 'System', icon: '⚙️' },
    ];
    const sidebarTabs = tabs.map((tab) => ({ id: tab.id, label: tab.label, icon: tab.icon }));
    // Show landing page first
    if (showLandingPage) {
        return (_jsxs(_Fragment, { children: [_jsx(LandingPage, { onEnterApp: handleEnterApp }), _jsx(Toaster, { position: "top-right", toastOptions: {
                        duration: 4000,
                        style: {
                            background: 'rgba(15, 23, 42, 0.95)',
                            color: '#cbd5f5',
                            border: '1px solid rgba(59, 130, 246, 0.35)',
                        },
                    } })] }));
    }
    return (_jsxs("div", { className: "min-h-screen bg-gray-900 text-white flex", children: [_jsx(Sidebar, { tabs: sidebarTabs, activeTab: activeTab, onSelect: (id) => setActiveTab(id), mobileMenuOpen: mobileMenuOpen, setMobileMenuOpen: setMobileMenuOpen }), _jsxs("div", { className: "flex-1 flex flex-col", children: [_jsx(TopBar, { onRefresh: refresh, lastUpdated: dashboardData?.system_status?.timestamp, healthRunning: health?.running, mobileMenuOpen: mobileMenuOpen, setMobileMenuOpen: setMobileMenuOpen, onBackToHome: () => setShowLandingPage(true), connectionStatus: connectionStatus, error: error, autoRefreshEnabled: autoRefreshEnabled, onToggleAutoRefresh: () => setAutoRefreshEnabled(!autoRefreshEnabled) }), _jsx("main", { className: "flex-1 p-4 md:p-6 lg:p-8 overflow-y-auto", children: _jsx("div", { className: "space-y-8", children: loading ? (_jsx(DashboardSkeleton, {})) : error ? (_jsx("div", { className: "text-red-500", children: error })) : (_jsxs(_Fragment, { children: [activeTab === 'overview' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("div", { className: "grid grid-cols-1 gap-4 md:grid-cols-4", children: [_jsx(MetricCard, { label: "Portfolio Balance", value: formatMaskedPortfolioValue(derived.balance), accent: "emerald", footer: _jsx("span", { children: "Live account equity" }) }), _jsx(MetricCard, { label: "Live Agent P&L", value: formatCurrency(derived.totalAgentPnL), accent: "teal", footer: _jsx("span", { children: "Combined unrealized result" }) }), _jsx(MetricCard, { label: "Available Margin", value: formatCurrency(derived.availableBalance), accent: "slate", footer: _jsx("span", { children: "Deployable capital" }) }), _jsx(MetricCard, { label: "Active Positions", value: derived.positions.length, accent: "amber", footer: _jsx("span", { children: "Across all agents" }) })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-3", children: [_jsx(StatusCard, { health: health, loading: loading }), _jsxs("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass", children: [_jsxs("div", { className: "mb-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Trading Status" }), _jsx("h3", { className: "mt-2 text-lg font-semibold text-white", children: "System Health" })] }), _jsxs("div", { className: "space-y-3", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("span", { className: "text-sm text-slate-300", children: "Trader Service" }), _jsx("span", { className: `px-2 py-1 rounded-full text-xs font-medium ${traderStatus === 'running' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300'}`, children: traderStatus })] }), _jsxs("div", { className: "flex items-center justify-between", children: [_jsx("span", { className: "text-sm text-slate-300", children: "Redis Connection" }), _jsx("span", { className: `px-2 py-1 rounded-full text-xs font-medium ${redisOnline ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'}`, children: redisOnline ? 'Online' : 'Offline' })] }), _jsxs("div", { className: "flex items-center justify-between", children: [_jsx("span", { className: "text-sm text-slate-300", children: "Active Agents" }), _jsxs("span", { className: "px-2 py-1 rounded-full text-xs font-medium bg-blue-500/20 text-blue-300", children: [derived.activeAgents, "/", configuredAgents] })] })] })] }), _jsx(TargetsAndAlerts, { targets: dashboardData?.targets })] }), _jsx("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-2", children: derived.agents.length > 0 ? (derived.agents.map((agent) => (_jsx(AgentCard, { agent: agent, onClick: () => {
                                                        toast.success(`${agent.name} metrics refreshed`, {
                                                            duration: 2000,
                                                            style: {
                                                                background: 'rgba(15, 23, 42, 0.95)',
                                                                color: '#cbd5f5',
                                                                border: '1px solid rgba(59, 130, 246, 0.35)',
                                                            },
                                                        });
                                                    } }, agent.id)))) : (_jsxs("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/60 p-8 text-center text-slate-400 shadow-glass", children: [_jsx("p", { className: "text-lg font-semibold text-white", children: "Awaiting live trades" }), _jsx("p", { className: "mt-2 text-sm text-slate-400", children: "Start the traders to stream real positions and model performance here." })] })) }), _jsxs("div", { className: "rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass", children: [_jsx("div", { className: "mb-4 flex items-center justify-between", children: _jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Portfolio Performance" }), _jsx("h3", { className: "mt-2 text-xl font-semibold text-white", children: "Balance & Price Trends" })] }) }), _jsx(PortfolioPerformance, { balanceSeries: performanceSeries.balance, priceSeries: performanceSeries.price })] })] })), activeTab === 'positions' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "relative overflow-hidden rounded-4xl border border-accent-ai/30 bg-surface-75/70 p-8 shadow-glass-xl", children: [_jsx(AuroraField, { className: "-left-64 -top-64 h-[520px] w-[520px]", variant: "emerald", intensity: "bold" }), _jsx(AuroraField, { className: "right-[-10rem] bottom-[-12rem] h-[540px] w-[540px]", variant: "sapphire" }), _jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(20,184,166,0.18),_transparent_70%)]" }), _jsx("div", { className: "absolute -right-24 top-1/2 h-64 w-64 -translate-y-1/2 rounded-full bg-accent-ai/10 blur-3xl" }), _jsxs("div", { className: "relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]", children: [_jsxs("div", { className: "space-y-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-accent-ai/70", children: "Exposure Lab" }), _jsx("h2", { className: "text-3xl font-bold text-white", children: "Agent Exposure Monitor" }), _jsx("p", { className: "text-sm leading-relaxed text-slate-300", children: "Track how each Sapphire agent is expressing conviction in the market right now. Radar-driven allocation keeps leverage disciplined while highlighting the heaviest targets on deck." }), _jsxs("div", { className: "flex flex-wrap items-center gap-3", children: [_jsx("span", { className: `inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] ${positionInsights.netNotional > 0 ? 'bg-emerald-400/20 text-emerald-200' : positionInsights.netNotional < 0 ? 'bg-rose-400/20 text-rose-200' : 'bg-slate-500/20 text-slate-200'}`, children: positionInsights.sentiment }), _jsxs("span", { className: "inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-slate-200", children: [derived.positions.length, " Active Positions"] })] })] }), _jsxs("div", { className: "grid gap-4 text-sm text-slate-200 sm:grid-cols-2", children: [_jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Net Notional" }), _jsx("p", { className: `mt-2 text-2xl font-semibold ${positionInsights.netNotional >= 0 ? 'text-emerald-300' : 'text-rose-300'}`, children: formatCurrency(positionInsights.netNotional) }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Long minus short exposure (USD)" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Gross Notional" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: formatCurrency(positionInsights.totalNotional) }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "All positions aggregated" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Long / Short" }), _jsxs("p", { className: "mt-2 text-2xl font-semibold text-white", children: [positionInsights.longCount, " / ", positionInsights.shortCount] }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Directional conviction split" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Hold-Ready" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: positionInsights.holdCount }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Agents waiting for better fills" })] })] })] })] }), positionInsights.topSymbols.length > 0 && (_jsx("div", { className: "grid grid-cols-1 gap-4 md:grid-cols-3", children: positionInsights.topSymbols.map(({ symbol, notional }) => {
                                                    const meta = resolveTokenMeta(symbol);
                                                    return (_jsxs("div", { className: "relative overflow-hidden rounded-3xl border border-white/10 bg-surface-75/70 p-5 shadow-glass", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(148,163,255,0.18),_transparent_75%)]" }), _jsxs("div", { className: "relative flex items-start justify-between gap-4", children: [_jsx("div", { className: `flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br ${meta.gradient} text-sm font-bold text-white shadow-lg`, children: meta.short }), _jsxs("div", { className: "text-right", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.28em] text-slate-400", children: "Focus Notional" }), _jsx("p", { className: "mt-2 text-lg font-semibold text-white", children: formatCurrency(notional) }), _jsx("p", { className: "text-xs text-slate-400", children: meta.name })] })] })] }, symbol));
                                                }) })), _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Live Positions", className: "h-72" }), children: _jsx(LivePositions, { positions: derived.positions }) })] })), activeTab === 'performance' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "relative overflow-hidden rounded-4xl border border-emerald-400/30 bg-surface-75/70 p-8 shadow-glass-xl", children: [_jsx(AuroraField, { className: "-left-60 -top-60 h-[520px] w-[520px]", variant: "emerald", intensity: "bold" }), _jsx(AuroraField, { className: "right-[-12rem] bottom-[-8rem] h-[500px] w-[500px]", variant: "amber" }), _jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(16,185,129,0.18),_transparent_70%)]" }), _jsxs("div", { className: "relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]", children: [_jsxs("div", { className: "space-y-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-emerald-200/80", children: "PnL Observatory" }), _jsx("h2", { className: "text-3xl font-bold text-white", children: "Momentum Performance Console" }), _jsx("p", { className: "text-sm leading-relaxed text-slate-300", children: "Follow the rolling dialogue between balance trajectory, fills, and realised PnL. Strategies publish their thesis into the MCP log before every trade\u2014this console shows how conviction translates into performance." }), _jsxs("div", { className: "flex flex-wrap items-center gap-3", children: [_jsxs("span", { className: "inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-slate-200", children: [performanceInsights.totalTrades, " Trades Observed"] }), _jsx("span", { className: "inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] bg-emerald-400/20 text-emerald-200", children: performanceInsights.sentiment })] })] }), _jsxs("div", { className: "grid gap-4 text-sm text-slate-200 sm:grid-cols-2", children: [_jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Win Rate" }), _jsxs("p", { className: "mt-2 text-2xl font-semibold text-white", children: [performanceInsights.winRate.toFixed(1), "%"] }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Across recent trade set" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Average Notional" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: formatCurrency(performanceInsights.averageNotional) }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Per executed trade" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Total Notional" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: formatCurrency(performanceInsights.totalNotional) }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Cumulative deployment" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Last Trade" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: performanceInsights.lastTrade
                                                                                    ? new Date(performanceInsights.lastTrade).toLocaleString()
                                                                                    : 'Awaiting Fill' }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Local environment time" })] })] })] })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]", children: [_jsxs("div", { className: "overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass", children: [_jsx("div", { className: "flex items-center justify-between", children: _jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-slate-400", children: "Balance Trajectory" }), _jsx("h3", { className: "mt-2 text-lg font-semibold text-white", children: "Capital vs Guiding Price" })] }) }), _jsx("div", { className: "mt-4", children: _jsx(PortfolioPerformance, { balanceSeries: performanceSeries.balance, priceSeries: performanceSeries.price }) })] }), _jsx("div", { className: "overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Trade Trends", className: "h-72" }), children: _jsx(PerformanceTrends, { trades: dashboardData?.recent_trades || [] }) }) })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-2", children: [_jsx("div", { className: "overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass", children: _jsx(RiskMetrics, { portfolio: dashboardData?.portfolio }) }), _jsx("div", { className: "overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Targets & Alerts", className: "h-72" }), children: _jsx(TargetsAndAlerts, { targets: dashboardData?.targets }) }) })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 xl:grid-cols-2", children: [_jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Model Performance", className: "h-[28rem]" }), children: _jsx(ModelPerformance, { models: dashboardData?.model_performance ?? [] }) }), _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Model Reasoning", className: "h-[28rem]" }), children: _jsx(ModelReasoning, { reasoning: dashboardData?.model_reasoning ?? [] }) })] })] })), activeTab === 'activity' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "relative overflow-hidden rounded-4xl border border-amber-400/30 bg-surface-75/70 p-8 shadow-glass-xl", children: [_jsx(AuroraField, { className: "-left-48 -top-52 h-[480px] w-[480px]", variant: "amber", intensity: "bold" }), _jsx(AuroraField, { className: "right-[-10rem] bottom-[-12rem] h-[500px] w-[500px]", variant: "sapphire" }), _jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(251,191,36,0.18),_transparent_70%)]" }), _jsxs("div", { className: "relative grid gap-8 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]", children: [_jsxs("div", { className: "space-y-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-amber-200/80", children: "Mission Feed" }), _jsx("h2", { className: "text-3xl font-bold text-white", children: "Command & Control Stream" }), _jsx("p", { className: "text-sm leading-relaxed text-slate-300", children: "Sapphire logs every orchestration event\u2014from MCP critiques to orchestrator overrides\u2014in an auditable lab journal. Filter for warnings, replay experiments, and trace causality without leaving the console." }), _jsxs("div", { className: "flex flex-wrap items-center gap-3", children: [_jsxs("span", { className: "inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-slate-200", children: [activitySummary.total, " Entries Tracked"] }), activitySummary.lastEntry && (_jsxs("span", { className: "inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] bg-amber-400/20 text-amber-100", children: ["Last update ", new Date(activitySummary.lastEntry.timestamp).toLocaleTimeString()] }))] })] }), _jsxs("div", { className: "grid gap-4 text-sm text-slate-200 sm:grid-cols-2", children: [_jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Success Signals" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: activitySummary.counts.success }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Orders landed smoothly" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Warnings" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: activitySummary.counts.warning }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Pre-emptive flags" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Errors" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: activitySummary.counts.error }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Needs immediate review" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Informational" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: activitySummary.counts.info }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Contextual telemetry" })] })] })] })] }), _jsx("div", { className: "overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Activity Log", className: "h-[28rem]" }), children: _jsx(ActivityLog, { logs: logs }) }) }), _jsxs("div", { className: "grid grid-cols-1 gap-6 xl:grid-cols-2", children: [_jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "MCP Council", className: "h-[24rem]" }), children: _jsx(MCPCouncil, { messages: mcpMessages ?? [], status: mcpStatus ?? connectionStatus }) }), _jsx("div", { className: "overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass", children: _jsx(CrowdSentimentWidget, { totalVotes: crowdSentiment.totalVotes, bullishVotes: crowdSentiment.bullishVotes, bearishVotes: crowdSentiment.bearishVotes, onVote: castCrowdVote, onReset: resetCrowd }) })] })] })), activeTab === 'system' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "relative overflow-hidden rounded-4xl border border-security-shield/40 bg-surface-75/70 p-8 shadow-glass-xl", children: [_jsx(AuroraField, { className: "-left-60 -top-60 h-[520px] w-[520px]", variant: "sapphire", intensity: "bold" }), _jsx(AuroraField, { className: "right-[-12rem] bottom-[-10rem] h-[520px] w-[520px]", variant: "emerald" }), _jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(96,165,250,0.18),_transparent_70%)]" }), _jsxs("div", { className: "relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]", children: [_jsxs("div", { className: "space-y-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-security-shield/70", children: "Reliability Core" }), _jsx("h2", { className: "text-3xl font-bold text-white", children: "Platform Resilience Console" }), _jsx("p", { className: "text-sm leading-relaxed text-slate-300", children: "Snap the infrastructure healthline: orchestrator governance, trader loops, Redis, and MCP connectivity. Everything routes through the load-balanced perimeter with security-first defaults." }), _jsxs("div", { className: "flex flex-wrap items-center gap-3", children: [_jsx("span", { className: "inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-slate-200", children: connectionStatus === 'connected' ? 'Live MCP uplink' : 'MCP reconnecting' }), _jsxs("span", { className: `inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] ${systemSummary.redisConnected ? 'bg-emerald-400/20 text-emerald-200' : 'bg-rose-400/20 text-rose-200'}`, children: ["Redis ", systemSummary.redisConnected ? 'Synchronized' : 'Offline'] })] })] }), _jsxs("div", { className: "grid gap-4 text-sm text-slate-200 sm:grid-cols-2", children: [_jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Orchestrator" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: systemSummary.orchestratorStatus }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Risk governor status" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Cloud Trader" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: systemSummary.traderStatus }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Execution loop heartbeat" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "Last Update" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: systemSummary.timestamp ? new Date(systemSummary.timestamp).toLocaleString() : 'Awaiting telemetry' }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "System status timestamp" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-slate-400", children: "MCP Channel" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-white", children: connectionStatus === 'connected' ? 'Synchronized' : 'Recovering' }), _jsx("p", { className: "mt-1 text-xs text-slate-400", children: "Mesh consensus transport" })] })] })] })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]", children: [_jsx("div", { className: "overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "System Status", className: "h-[24rem]" }), children: _jsx(SystemStatus, { status: dashboardData?.system_status }) }) }), _jsx("div", { className: "overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass", children: _jsx(StatusCard, { health: health ?? null, loading: loading }) })] })] }))] })) }) })] })] }));
};
export default App;
