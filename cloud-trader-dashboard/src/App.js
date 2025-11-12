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
import HistoricalPerformance from './components/HistoricalPerformance';
import CrowdSentimentWidget from './components/CrowdSentimentWidget';
import useCrowdSentiment from './hooks/useCrowdSentiment';
import LandingPage from './components/LandingPage';
import useAuth from './hooks/useAuth';
import useCommunityComments from './hooks/useCommunityComments';
import useCommunityLeaderboard from './hooks/useCommunityLeaderboard';
import CommunityFeedback from './components/CommunityFeedback';
import CommunityLeaderboard from './components/CommunityLeaderboard';
import { recordCheckIn, isRealtimeCommunityEnabled } from './services/community';
import AnalyticsManager from './components/analytics/AnalyticsManager';
const ActivityLog = lazy(() => import('./components/ActivityLog'));
const ModelPerformance = lazy(() => import('./components/ModelPerformance'));
const ModelReasoning = lazy(() => import('./components/ModelReasoning'));
const LivePositions = lazy(() => import('./components/LivePositions'));
const SystemStatus = lazy(() => import('./components/SystemStatus'));
const PerformanceTrends = lazy(() => import('./components/PerformanceTrends'));
const MCPCouncil = lazy(() => import('./components/MCPCouncil'));
const formatCurrency = (value) => new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
}).format(value);
const formatMaskedPortfolioValue = (value) => {
    void value;
    return '%s';
};
const SectionSkeleton = ({ title, className }) => (_jsxs("div", { className: `rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-glass animate-pulse ${className ?? ''}`, children: [title && _jsx("div", { className: "mb-5 h-3 w-40 rounded-full bg-white/20" }), _jsxs("div", { className: "space-y-4", children: [_jsx("div", { className: "h-4 w-full rounded-full bg-white/10" }), _jsx("div", { className: "h-4 w-5/6 rounded-full bg-white/10" }), _jsx("div", { className: "h-4 w-4/6 rounded-full bg-white/10" })] })] }));
const DashboardSkeleton = () => (_jsxs("div", { className: "space-y-8", children: [_jsx(SectionSkeleton, { title: "Initializing trading system" }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-3", children: [_jsx(SectionSkeleton, { className: "h-40" }), _jsx(SectionSkeleton, { className: "h-40" }), _jsx(SectionSkeleton, { className: "h-40" })] }), _jsx(SectionSkeleton, { title: "Streaming live trade telemetry", className: "h-80" }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-2", children: [_jsx(SectionSkeleton, { className: "h-72" }), _jsx(SectionSkeleton, { className: "h-72" })] })] }));
const MaintenancePage = () => (_jsxs("div", { className: "min-h-screen bg-brand-midnight text-brand-ice relative overflow-hidden flex items-center justify-center p-6", children: [_jsx("div", { className: "pointer-events-none absolute inset-0 bg-sapphire-mesh opacity-60" }), _jsx("div", { className: "pointer-events-none absolute inset-0 bg-sapphire-strata opacity-50" }), _jsxs("div", { className: "relative max-w-3xl rounded-4xl border border-brand-border/70 bg-brand-abyss/80 p-10 text-center shadow-sapphire", children: [_jsx("div", { className: "mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-accent-blue/20 text-3xl", children: "\u23F3" }), _jsx("h1", { className: "text-3xl font-bold tracking-wide text-brand-ice", children: "Sapphire is calibrating for launch" }), _jsxs("p", { className: "mt-4 text-brand-ice/80 leading-relaxed", children: ["We're applying final production upgrades to the live trading stack and refreshing all community data. The dashboard will reopen by ", _jsx("span", { className: "text-brand-accent-blue font-semibold", children: "10:30\u202FPM Central Time" }), "with the full Sapphire experience."] }), _jsxs("div", { className: "mt-8 space-y-2 text-sm text-brand-ice/60", children: [_jsx("p", { children: "\u2022 Live traders remain on risk-managed standby during this upgrade window." }), _jsx("p", { children: "\u2022 Telegram alerts will resume automatically once trading restarts." }), _jsxs("p", { children: ["\u2022 Follow updates on Twitter/X: ", _jsx("span", { className: "text-brand-accent-blue", children: "@rari_sui" })] })] })] })] }));
// This is the new, self-contained Dashboard component.
// All hooks and data logic now live here, ensuring they are always called in the same order.
const Dashboard = ({ onBackToHome }) => {
    const { health, dashboardData, loading, error, logs, connectionStatus, mcpMessages, mcpStatus, refresh } = useTraderService();
    const [selectedAgentForHistory, setSelectedAgentForHistory] = React.useState(null);
    const { user, loading: authLoading, signInWithSocial, signOut: authSignOut, signInWithEmail, signUpWithEmail, enabled: authEnabled, error: authError, } = useAuth();
    const [communityComments, submitCommunityComment, commentsLoading] = useCommunityComments(user);
    const [leaderboardEntries, leaderboardLoading] = useCommunityLeaderboard(15);
    const [crowdSentiment, registerCrowdVote, resetCrowd, sentimentLoading] = useCrowdSentiment(user);
    const [activeTab, setActiveTab] = useState('overview');
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
    const [commentSubmitting, setCommentSubmitting] = useState(false);
    const realtimeCommunity = isRealtimeCommunityEnabled();
    React.useEffect(() => {
        if (user && realtimeCommunity) {
            recordCheckIn(user).catch((err) => {
                if (import.meta.env.DEV) {
                    console.warn('[community] failed to record daily check-in', err);
                }
            });
        }
    }, [user, realtimeCommunity]);
    // Keyboard shortcuts
    React.useEffect(() => {
        const handleKeyDown = (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'r') {
                event.preventDefault();
                refresh();
            }
            if (event.key === 'Escape') {
                onBackToHome();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [refresh, onBackToHome]);
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
        const cacheBackend = systemStatus?.cache?.backend ?? 'memory';
        const cacheConnected = systemStatus?.cache?.connected ?? false;
        const storageReady = systemStatus?.storage_ready ?? false;
        const pubsubConnected = systemStatus?.pubsub_connected ?? false;
        const featureStoreReady = systemStatus?.feature_store_ready ?? false;
        const bigqueryReady = systemStatus?.bigquery_ready ?? false;
        return {
            orchestratorStatus,
            traderStatus,
            cacheBackend,
            cacheConnected,
            storageReady,
            pubsubConnected,
            featureStoreReady,
            bigqueryReady,
            timestamp: systemStatus?.timestamp ?? null,
        };
    }, [systemStatus]);
    const traderStatus = systemStatus?.services?.cloud_trader ?? 'unknown';
    const communityInsights = useMemo(() => {
        const totalVotes = crowdSentiment.totalVotes;
        const bullishRatio = totalVotes ? Math.round((crowdSentiment.bullishVotes / totalVotes) * 100) : 0;
        const bearishRatio = totalVotes ? Math.round((crowdSentiment.bearishVotes / totalVotes) * 100) : 0;
        const totalComments = communityComments.length;
        const topContributor = leaderboardEntries.length ? leaderboardEntries[0] : undefined;
        const totalPoints = leaderboardEntries.reduce((acc, entry) => acc + (entry.points ?? 0), 0);
        return {
            totalVotes,
            bullishRatio,
            bearishRatio,
            totalComments,
            topContributor,
            totalPoints,
        };
    }, [crowdSentiment, communityComments, leaderboardEntries]);
    const topContributor = communityInsights.topContributor;
    const topContributorPoints = topContributor?.points ?? 0;
    const configuredAgents = derived.agents.length || 4;
    const cacheConnected = systemStatus?.cache?.connected ?? false;
    const cacheBackend = systemStatus?.cache?.backend ?? 'memory';
    const tabs = [
        { id: 'overview', label: 'Live Trading', icon: '🚀' },
        { id: 'positions', label: 'Positions', icon: '📈' },
        { id: 'performance', label: 'Performance', icon: '💰' },
        { id: 'community', label: 'Community', icon: '🌐' },
        { id: 'council', label: 'AI Council', icon: '🤖' },
        { id: 'activity', label: 'Activity Log', icon: '📋' },
        { id: 'system', label: 'System', icon: '⚙️' },
    ];
    const sidebarTabs = tabs.map((tab) => ({ id: tab.id, label: tab.label, icon: tab.icon }));
    const handleSocialSignIn = async (provider) => {
        if (!authEnabled) {
            toast.error('Community sign-in is currently disabled in this environment.');
            return;
        }
        try {
            await signInWithSocial(provider);
            toast.success('Signed in—welcome to the Sapphire Collective.');
        }
        catch (signInError) {
            const message = signInError instanceof Error ? signInError.message : 'Unable to sign in right now.';
            toast.error(message);
            throw signInError;
        }
    };
    const handleAuthenticate = () => {
        void handleSocialSignIn('google');
    };
    const handleEmailSignIn = async (email, password) => {
        try {
            await signInWithEmail(email, password);
            toast.success('Signed in—your voice is live.');
        }
        catch (err) {
            const message = err instanceof Error ? err.message : 'Unable to sign in right now.';
            toast.error(message);
            throw err;
        }
    };
    const handleEmailSignUp = async (email, password, displayName) => {
        try {
            await signUpWithEmail(email, password, displayName);
            toast.success('Account created. Welcome aboard!');
        }
        catch (err) {
            const message = err instanceof Error ? err.message : 'Unable to create account right now.';
            toast.error(message);
            throw err;
        }
    };
    const handleCrowdVote = (vote) => {
        if (!user) {
            toast.error('Authenticate to cast your signal.');
            return;
        }
        void (async () => {
            try {
                await registerCrowdVote(vote);
                toast.success('Signal received. Thanks for steering the desk!');
            }
            catch (voteError) {
                const message = voteError instanceof Error ? voteError.message : 'Failed to record vote';
                toast.error(message);
            }
        })();
    };
    const handleCommentSubmit = async (message) => {
        if (!user) {
            toast.error('Sign in to leave feedback for the agents.');
            return;
        }
        setCommentSubmitting(true);
        try {
            await submitCommunityComment(message);
            toast.success('Feedback sent to the council.');
        }
        catch (commentError) {
            const message = commentError instanceof Error ? commentError.message : 'Failed to send feedback';
            toast.error(message);
            throw commentError;
        }
        finally {
            setCommentSubmitting(false);
        }
    };
    const handleSignOut = async () => {
        try {
            await authSignOut();
            toast.success('Signed out. See you on the next session.');
        }
        catch (signOutError) {
            const message = signOutError instanceof Error ? signOutError.message : 'Failed to sign out';
            toast.error(message);
        }
    };
    return (_jsxs(_Fragment, { children: [_jsx(AnalyticsManager, {}), _jsxs("div", { className: "relative min-h-screen overflow-hidden bg-brand-midnight text-brand-ice", children: [_jsx("div", { className: "pointer-events-none absolute inset-0 bg-sapphire-strata" }), _jsx("div", { className: "pointer-events-none absolute inset-0 bg-sapphire-mesh opacity-80" }), _jsxs("div", { className: "relative flex min-h-screen", children: [_jsx(Sidebar, { tabs: sidebarTabs, activeTab: activeTab, onSelect: (id) => setActiveTab(id), mobileMenuOpen: mobileMenuOpen, setMobileMenuOpen: setMobileMenuOpen }), _jsxs("div", { className: "flex-1 flex flex-col", children: [_jsx(TopBar, { onRefresh: refresh, lastUpdated: dashboardData?.system_status?.timestamp, healthRunning: health?.running, mobileMenuOpen: mobileMenuOpen, setMobileMenuOpen: setMobileMenuOpen, onBackToHome: onBackToHome, connectionStatus: connectionStatus, error: error, autoRefreshEnabled: autoRefreshEnabled, onToggleAutoRefresh: () => setAutoRefreshEnabled(!autoRefreshEnabled) }), _jsx("main", { className: "flex-1 overflow-y-auto p-4 md:p-6 lg:p-8", children: _jsx("div", { className: "space-y-8", children: loading ? (_jsx(DashboardSkeleton, {})) : error ? (_jsx("div", { className: "flex items-center justify-center min-h-[400px]", children: _jsxs("div", { className: "text-center space-y-6 max-w-md mx-auto", children: [_jsxs("div", { className: "relative", children: [_jsx("div", { className: "w-16 h-16 mx-auto rounded-full bg-error/10 flex items-center justify-center", children: _jsx("svg", { className: "w-8 h-8 text-error", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" }) }) }), _jsx("div", { className: "absolute -top-2 -right-2 w-6 h-6 bg-error rounded-full flex items-center justify-center", children: _jsx("span", { className: "text-xs text-white font-bold", children: "!" }) })] }), _jsxs("div", { className: "space-y-2", children: [_jsx("h3", { className: "text-xl font-semibold text-brand-ice", children: "Connection Error" }), _jsx("p", { className: "text-brand-muted/80 text-sm leading-relaxed", children: "Unable to connect to the trading service. This might be a temporary network issue." }), _jsx("div", { className: "bg-error/10 border border-error/30 rounded-lg p-3 mt-4", children: _jsx("p", { className: "text-error/80 text-xs font-mono break-words", children: error }) })] }), _jsxs("div", { className: "flex gap-3 justify-center", children: [_jsxs("button", { onClick: refresh, className: "px-4 py-2 bg-accent-sapphire/80 hover:bg-accent-sapphire text-brand-midnight text-sm font-medium rounded-lg transition-colors duration-200 flex items-center gap-2", children: [_jsx("svg", { className: "w-4 h-4", fill: "none", stroke: "currentColor", viewBox: "0 0 24 24", children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: 2, d: "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" }) }), "Retry Connection"] }), _jsx("button", { onClick: () => window.location.reload(), className: "px-4 py-2 bg-brand-border/60 hover:bg-brand-border/80 text-brand-ice text-sm font-medium rounded-lg transition-colors duration-200", children: "Reload Page" })] }), _jsxs("div", { className: "text-xs text-brand-muted/70 space-y-1", children: [_jsx("p", { children: "\u2022 Check your internet connection" }), _jsx("p", { children: "\u2022 The trading service might be restarting" }), _jsx("p", { children: "\u2022 Try refreshing the page in a few moments" })] })] }) })) : (_jsxs(_Fragment, { children: [activeTab === 'overview' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "sapphire-section flex flex-col gap-6 rounded-4xl p-8 lg:flex-row lg:items-center", children: [_jsxs("div", { className: "flex-1 space-y-6", children: [_jsx("span", { className: "inline-flex items-center gap-2 rounded-full border border-accent-sapphire/40 bg-brand-abyss/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.32em] text-accent-sapphire", children: "Command Center" }), _jsxs("div", { className: "space-y-3", children: [_jsx("h2", { className: "text-3xl font-bold text-brand-ice", children: "Live trading telemetry at a glance" }), _jsx("p", { className: "max-w-2xl text-sm leading-relaxed text-brand-muted", children: "4 AI agents trading 154 symbols with intelligent risk management." })] }), _jsxs("div", { className: "grid gap-3 sm:grid-cols-2", children: [_jsxs("div", { className: "rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-5 shadow-sapphire-sm", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted/70", children: "Status" }), _jsx("p", { className: "mt-2 text-xl font-semibold text-brand-ice", children: "Live Trading" }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "$350 daily target, max profit optimization." })] }), _jsxs("div", { className: "rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-5 shadow-sapphire-sm", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted/70", children: "Risk Control" }), _jsx("p", { className: "mt-2 text-xl font-semibold text-brand-ice", children: "Active" }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Liquidation protection, adaptive leverage." })] })] }), _jsxs("div", { className: "flex flex-wrap items-center gap-3 pt-2 text-xs text-brand-muted/70", children: [_jsxs("span", { className: "inline-flex items-center gap-2 rounded-full border border-brand-border/50 bg-brand-abyss/80 px-4 py-2 font-semibold uppercase tracking-[0.28em] text-brand-ice/80", children: [configuredAgents, " Agents Coordinated"] }), _jsxs("span", { className: "inline-flex items-center gap-2 rounded-full border border-brand-border/50 bg-brand-abyss/80 px-4 py-2 font-semibold uppercase tracking-[0.28em] text-brand-ice/80", children: ["Cache Backend: ", cacheBackend] })] })] }), _jsxs("div", { className: "relative w-full max-w-sm rounded-3xl border border-brand-border/60 bg-brand-abyss/80 p-6 shadow-sapphire overflow-hidden", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(79,209,255,0.22),_transparent_65%)]" }), _jsxs("div", { className: "relative space-y-4 text-sm text-brand-ice", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-brand-muted/80", children: "Quick View" }), _jsx("h3", { className: "text-lg font-semibold text-brand-ice", children: "What to watch" }), _jsxs("ul", { className: "space-y-2 text-xs text-brand-muted/75", children: [_jsx("li", { children: "\u2022 Fills & exposure update every refresh interval." }), _jsx("li", { children: "\u2022 System tab shows cache/storage/pubsub health without Redis." }), _jsx("li", { children: "\u2022 Community tab surfaces feedback that agents may reference." })] }), _jsx("div", { className: "rounded-2xl border border-brand-border/50 bg-brand-midnight/80 p-3 text-xs text-brand-muted", children: _jsx("p", { children: "Telemetry runs entirely on GCP: Pub/Sub for streaming, Cloud SQL + BigQuery for history, and in-memory caching for fast reads." }) })] })] })] }), _jsxs("section", { className: "sapphire-section rounded-4xl border border-brand-border/60 bg-brand-abyss/80 p-6 shadow-sapphire", children: [_jsxs("header", { className: "flex flex-col gap-3 text-brand-ice/80 md:flex-row md:items-center md:justify-between", children: [_jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-brand-ice/70", children: "Open-source intelligence core" }), _jsx("h3", { className: "text-2xl font-semibold text-brand-ice", children: "Multi-Agent AI Stack: FinGPT + Lag-LLaMA" })] }), _jsx("p", { className: "text-sm md:max-w-xl", children: "Sapphire queries multiple AI agents in parallel for AVAX and ARB symbols, synthesizing their perspectives for enhanced accuracy. Both agents collaborate simultaneously, with intelligent thesis selection based on confidence and risk scores. All signals stay within our secure Vertex/GCP boundary, with privacy-preserving inference and community-auditable reasoning." })] }), _jsxs("div", { className: "mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2", children: [_jsxs("article", { className: "relative overflow-hidden rounded-3xl border border-brand-border/60 bg-brand-abyss/70 p-5 shadow-sapphire-sm", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(79,70,229,0.24),_transparent_65%)]" }), _jsxs("div", { className: "relative space-y-3", children: [_jsx("div", { className: "inline-flex items-center gap-2 rounded-full bg-brand-accent-blue/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-brand-accent-blue", children: "\uD83E\uDDE0 FinGPT Alpha" }), _jsx("p", { className: "text-sm text-brand-ice/80", children: "Primary thesis generator for AVAX markets with parallel collaboration with Lag-Llama. Outputs structured reasoning, risk scoring, and confidence. Queries happen simultaneously with Lag-Llama for multi-perspective analysis. Hallucination guardrails and risk threshold enforcement ensure only high-quality theses reach execution." }), _jsxs("ul", { className: "space-y-2 text-xs text-brand-ice/70", children: [_jsx("li", { children: "\u2022 Parallel queries with Lag-Llama for AVAX symbols." }), _jsx("li", { children: "\u2022 Response caching (10s TTL) reduces redundant API calls by 50-70%." }), _jsx("li", { children: "\u2022 Retry logic with exponential backoff for reliability." }), _jsx("li", { children: "\u2022 Risk threshold enforcement (default 0.7) filters low-quality theses." }), _jsx("li", { children: "\u2022 Enhanced prompts with DeFi context and volatility regime detection." })] })] })] }), _jsxs("article", { className: "relative overflow-hidden rounded-3xl border border-brand-border/60 bg-brand-abyss/70 p-5 shadow-sapphire-sm", children: [_jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(34,197,94,0.22),_transparent_65%)]" }), _jsxs("div", { className: "relative space-y-3", children: [_jsx("div", { className: "inline-flex items-center gap-2 rounded-full bg-brand-accent-teal/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-brand-accent-teal", children: "\uD83E\uDD99 Lag-LLaMA Visionary" }), _jsx("p", { className: "text-sm text-brand-ice/80", children: "Primary time-series forecaster for ARB markets with parallel collaboration with FinGPT. Generates probabilistic forecasts with confidence bands and anomaly detection. Queries happen simultaneously with FinGPT for sentiment + time-series synthesis. CI span validation (over 20% rejected) keeps execution disciplined." }), _jsxs("ul", { className: "space-y-2 text-xs text-brand-ice/70", children: [_jsx("li", { children: "\u2022 Parallel queries with FinGPT for ARB symbols." }), _jsx("li", { children: "\u2022 Forecast validation rejects predictions over 50% away from current price." }), _jsx("li", { children: "\u2022 CI span validation (max 20%) prevents overconfident trades." }), _jsx("li", { children: "\u2022 Anomaly detection integration for regime shift identification." }), _jsx("li", { children: "\u2022 Time-series enrichment with on-chain volume data." })] })] })] })] })] }), _jsxs("div", { className: "grid grid-cols-1 gap-4 md:grid-cols-4", children: [_jsx(MetricCard, { label: "Portfolio Balance", value: formatMaskedPortfolioValue(derived.balance), accent: "emerald", footer: _jsx("span", { children: "Live account equity" }) }), _jsx(MetricCard, { label: "Live Agent P&L", value: formatCurrency(derived.totalAgentPnL), accent: "teal", footer: _jsx("span", { children: "Combined unrealized result" }) }), _jsx(MetricCard, { label: "Available Margin", value: formatCurrency(derived.availableBalance), accent: "slate", footer: _jsx("span", { children: "Deployable capital" }) }), _jsx(MetricCard, { label: "Active Positions", value: derived.positions.length, accent: "amber", footer: _jsx("span", { children: "Across all agents" }) })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-3", children: [_jsx(StatusCard, { health: health, loading: loading }), _jsxs("div", { className: "sapphire-panel p-6", children: [_jsxs("div", { className: "mb-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-brand-muted/80", children: "Trading Status" }), _jsx("h3", { className: "mt-2 text-lg font-semibold text-brand-ice", children: "System Health" })] }), _jsxs("div", { className: "space-y-3", children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("span", { className: "text-sm text-brand-muted", children: "Trader Service" }), _jsx("span", { className: `px-2 py-1 rounded-full text-xs font-medium ${traderStatus === 'running' ? 'bg-accent-emerald/30 text-accent-emerald' : 'bg-warning-amber/30 text-warning-amber'}`, children: traderStatus })] }), _jsxs("div", { className: "flex items-center justify-between", children: [_jsxs("span", { className: "text-sm text-brand-muted", children: ["Cache Backend (", cacheBackend, ")"] }), _jsx("span", { className: `px-2 py-1 rounded-full text-xs font-medium ${cacheConnected ? 'bg-accent-emerald/30 text-accent-emerald' : 'bg-error/20 text-error'}`, children: cacheConnected ? 'Online' : 'Offline' })] }), _jsxs("div", { className: "flex items-center justify-between", children: [_jsx("span", { className: "text-sm text-brand-muted", children: "Active Agents" }), _jsxs("span", { className: "px-2 py-1 rounded-full text-xs font-medium bg-accent-sapphire/20 text-accent-sapphire", children: [derived.activeAgents, "/", configuredAgents] })] })] })] })] }), _jsx("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-2", children: derived.agents.length > 0 ? (derived.agents.map((agent) => (_jsx(AgentCard, { agent: agent, onClick: () => {
                                                                        toast.success(`${agent.name} metrics refreshed`, {
                                                                            duration: 2000,
                                                                            style: {
                                                                                background: 'rgba(4, 16, 41, 0.95)',
                                                                                color: '#d9ecff',
                                                                                border: '1px solid rgba(79, 209, 255, 0.25)',
                                                                            },
                                                                        });
                                                                    }, onViewHistory: (agent) => setSelectedAgentForHistory(agent) }, agent.id)))) : (_jsxs("div", { className: "sapphire-panel p-8 text-center text-brand-muted", children: [_jsx("p", { className: "text-lg font-semibold text-brand-ice", children: "Awaiting live trades" }), _jsx("p", { className: "mt-2 text-sm text-brand-muted", children: "Start the traders to stream real positions and model performance here." })] })) }), _jsxs("div", { className: "sapphire-panel p-6", children: [_jsx("div", { className: "mb-4 flex items-center justify-between", children: _jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-brand-muted/80", children: "Portfolio Performance" }), _jsx("h3", { className: "mt-2 text-xl font-semibold text-brand-ice", children: "Balance & Price Trends" })] }) }), _jsx(PortfolioPerformance, { balanceSeries: performanceSeries.balance, priceSeries: performanceSeries.price })] })] })), activeTab === 'positions' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "sapphire-section border border-accent-emerald/25", children: [_jsx(AuroraField, { className: "-left-64 -top-64 h-[520px] w-[520px]", variant: "emerald", intensity: "bold" }), _jsx(AuroraField, { className: "right-[-10rem] bottom-[-12rem] h-[540px] w-[540px]", variant: "sapphire" }), _jsxs("div", { className: "relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]", children: [_jsxs("div", { className: "space-y-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-accent-emerald/80", children: "Exposure Lab" }), _jsx("h2", { className: "text-3xl font-bold text-brand-ice", children: "Agent Exposure Monitor" }), _jsx("p", { className: "text-sm leading-relaxed text-brand-muted", children: "Track how each Sapphire agent is expressing conviction in the market right now. Radar-driven allocation keeps leverage disciplined while highlighting the heaviest targets on deck." }), _jsxs("div", { className: "flex flex-wrap items-center gap-3", children: [_jsx("span", { className: `inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] ${positionInsights.netNotional > 0 ? 'bg-accent-emerald/20 text-accent-emerald' : positionInsights.netNotional < 0 ? 'bg-error/20 text-error' : 'bg-brand-border/40 text-brand-muted'}`, children: positionInsights.sentiment }), _jsxs("span", { className: "inline-flex items-center gap-2 rounded-full border border-brand-border/60 bg-brand-abyss/80 px-4 py-2 text-xs uppercase tracking-[0.28em] text-brand-muted", children: [derived.positions.length, " Active Positions"] })] })] }), _jsxs("div", { className: "grid gap-4 text-sm text-brand-ice sm:grid-cols-2", children: [_jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Net Notional" }), _jsx("p", { className: `mt-2 text-2xl font-semibold ${positionInsights.netNotional >= 0 ? 'text-accent-emerald' : 'text-error'}`, children: formatCurrency(positionInsights.netNotional) }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Long minus short exposure (USD)" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Gross Notional" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: formatCurrency(positionInsights.totalNotional) }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "All positions aggregated" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Long / Short" }), _jsxs("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: [positionInsights.longCount, " / ", positionInsights.shortCount] }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Directional conviction split" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Hold-Ready" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: positionInsights.holdCount }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Agents waiting for better fills" })] })] })] })] }), positionInsights.topSymbols.length > 0 && (_jsx("div", { className: "grid grid-cols-1 gap-4 md:grid-cols-3", children: positionInsights.topSymbols.map(({ symbol, notional }) => {
                                                                    const meta = resolveTokenMeta(symbol);
                                                                    return (_jsx("div", { className: "sapphire-panel p-5", children: _jsxs("div", { className: "relative flex items-start justify-between gap-4", children: [_jsx("div", { className: `flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br ${meta.gradient} text-sm font-bold text-white shadow-lg`, children: meta.short }), _jsxs("div", { className: "text-right", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.28em] text-brand-muted", children: "Focus Notional" }), _jsx("p", { className: "mt-2 text-lg font-semibold text-brand-ice", children: formatCurrency(notional) }), _jsx("p", { className: "text-xs text-brand-muted", children: meta.name })] })] }) }, symbol));
                                                                }) })), _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Live Positions", className: "h-72" }), children: _jsx(LivePositions, { positions: derived.positions }) })] })), activeTab === 'performance' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "sapphire-section border border-accent-emerald/25", children: [_jsx(AuroraField, { className: "-left-60 -top-60 h-[520px] w-[520px]", variant: "emerald", intensity: "bold" }), _jsx(AuroraField, { className: "right-[-12rem] bottom-[-8rem] h-[500px] w-[500px]", variant: "amber" }), _jsxs("div", { className: "relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]", children: [_jsxs("div", { className: "space-y-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-accent-emerald/80", children: "PnL Observatory" }), _jsx("h2", { className: "text-3xl font-bold text-brand-ice", children: "Momentum Performance Console" }), _jsx("p", { className: "text-sm leading-relaxed text-brand-muted", children: "Follow the rolling dialogue between balance trajectory, fills, and realised PnL. Strategies publish their thesis into the MCP log before every trade\u2014this console shows how conviction translates into performance." }), _jsxs("div", { className: "flex flex-wrap items-center gap-3", children: [_jsxs("span", { className: "sapphire-chip text-brand-midnight bg-gradient-to-r from-accent-sapphire/90 to-accent-emerald/80", children: [performanceInsights.totalTrades, " Trades Observed"] }), _jsx("span", { className: "sapphire-chip text-brand-midnight bg-gradient-to-r from-accent-emerald/90 to-accent-teal/80", children: performanceInsights.sentiment })] })] }), _jsxs("div", { className: "grid gap-4 text-sm text-brand-ice sm:grid-cols-2", children: [_jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Win Rate" }), _jsxs("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: [performanceInsights.winRate.toFixed(1), "%"] }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Across recent trade set" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Average Notional" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: formatCurrency(performanceInsights.averageNotional) }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Per executed trade" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Total Notional" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: formatCurrency(performanceInsights.totalNotional) }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Cumulative deployment" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Last Trade" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: performanceInsights.lastTrade
                                                                                                    ? new Date(performanceInsights.lastTrade).toLocaleString()
                                                                                                    : 'Awaiting Fill' }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Local environment time" })] })] })] })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]", children: [_jsxs("div", { className: "sapphire-panel p-6", children: [_jsx("div", { className: "flex items-center justify-between", children: _jsxs("div", { children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-brand-muted/80", children: "Balance Trajectory" }), _jsx("h3", { className: "mt-2 text-lg font-semibold text-brand-ice", children: "Capital vs Guiding Price" })] }) }), _jsx("div", { className: "mt-4", children: _jsx(PortfolioPerformance, { balanceSeries: performanceSeries.balance, priceSeries: performanceSeries.price }) })] }), _jsx("div", { className: "sapphire-panel p-6", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Trade Trends", className: "h-72" }), children: _jsx(PerformanceTrends, { trades: dashboardData?.recent_trades || [] }) }) })] }), _jsx("div", { className: "grid grid-cols-1 gap-6", children: _jsx("div", { className: "sapphire-panel p-6", children: _jsx(RiskMetrics, { portfolio: dashboardData?.portfolio }) }) }), _jsxs("div", { className: "grid grid-cols-1 gap-6 xl:grid-cols-2", children: [_jsx("div", { className: "sapphire-panel p-6", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Model Performance", className: "h-[28rem]" }), children: _jsx(ModelPerformance, { models: dashboardData?.model_performance ?? [] }) }) }), _jsx("div", { className: "sapphire-panel p-6", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Model Reasoning", className: "h-[28rem]" }), children: _jsx(ModelReasoning, { reasoning: dashboardData?.model_reasoning ?? [] }) }) })] })] })), activeTab === 'community' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "sapphire-section border border-accent-sapphire/35", children: [_jsx(AuroraField, { className: "-left-64 -top-48 h-[520px] w-[520px]", variant: "sapphire", intensity: "bold" }), _jsx(AuroraField, { className: "right-[-12rem] bottom-[-12rem] h-[560px] w-[560px]", variant: "emerald", intensity: "soft" }), _jsxs("div", { className: "relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]", children: [_jsxs("div", { className: "space-y-5", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-accent-sapphire/80", children: "Collective Intelligence" }), _jsx("h2", { className: "text-3xl font-bold text-brand-ice", children: "Sapphire Community Command" }), _jsxs("p", { className: "text-sm leading-relaxed text-brand-muted", children: ["Every vote, comment, and daily check-in fuels our agent swarm. Insights are privacy-preserving and routed through throttled signals so bots can reference the crowd without overfitting. Follow ", _jsx("a", { href: "https://twitter.com/rari_sui", target: "_blank", rel: "noreferrer", className: "text-accent-sapphire hover:underline", children: "@rari_sui" }), " for the behind-the-scenes build."] }), _jsxs("div", { className: "grid gap-4 sm:grid-cols-2", children: [_jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Total Votes" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: communityInsights.totalVotes }), _jsxs("p", { className: "mt-1 text-xs text-brand-muted", children: ["Bullish ", communityInsights.bullishRatio, "% \u00B7 Bearish ", communityInsights.bearishRatio, "%"] })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Community Feedback" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: communityInsights.totalComments }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Signal briefs captured for the agents" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Top Contributor" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: topContributor?.displayName ?? '—' }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: topContributor ? `${topContributorPoints.toLocaleString()} pts earned` : 'Join in to claim the leaderboard' })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Collective Points" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: communityInsights.totalPoints.toLocaleString() }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Accrued via check-ins, comments, and sentiment votes" })] })] })] }), _jsx("div", { children: _jsx(CommunityLeaderboard, { entries: leaderboardEntries, loading: leaderboardLoading }) })] })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]", children: [_jsx("div", { className: "sapphire-panel p-6", children: _jsx(CrowdSentimentWidget, { totalVotes: crowdSentiment.totalVotes, bullishVotes: crowdSentiment.bullishVotes, bearishVotes: crowdSentiment.bearishVotes, hasVoted: crowdSentiment.hasVoted, onVote: handleCrowdVote, onAuthenticate: handleAuthenticate, isAuthenticated: Boolean(user), onReset: realtimeCommunity ? undefined : resetCrowd, loading: sentimentLoading }) }), _jsxs("div", { className: "sapphire-panel p-6", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-brand-muted", children: "Community Pulse" }), _jsx("h3", { className: "mt-2 text-xl font-semibold text-brand-ice", children: "How the crowd influences the desk" }), _jsxs("p", { className: "mt-3 text-sm text-brand-muted", children: ["We credit daily check-ins with points, capture ticker-tagged insights (ex: ", _jsx("code", { children: "$SOL" }), "), and expose anonymized aggregates to the trading agents. Bots treat these signals as optional context\u2014never primary execution drivers\u2014so sparse data never overrides disciplined momentum strategies."] }), _jsxs("ul", { className: "mt-4 space-y-2 text-sm text-brand-muted/90", children: [_jsx("li", { children: "\u2022 Daily attendance unlocks micropayment rewards when x402 launches." }), _jsx("li", { children: "\u2022 Hidden-positions mode keeps PnL private while still surfacing agent intent." }), _jsx("li", { children: "\u2022 Privacy coin routing is on the roadmap so shielded communities can participate." })] })] })] }), _jsx(CommunityFeedback, { comments: communityComments, onSubmit: handleCommentSubmit, user: user, loading: authLoading || commentsLoading, onSignOut: handleSignOut, authEnabled: authEnabled, authError: authError, onSocialSignIn: handleSocialSignIn, onEmailSignIn: handleEmailSignIn, onEmailSignUp: handleEmailSignUp, commentSubmitting: commentSubmitting })] })), activeTab === 'council' && (_jsx("div", { className: "space-y-6", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "MCP Council", className: "h-[24rem]" }), children: _jsx(MCPCouncil, { messages: mcpMessages ?? [], status: mcpStatus ?? connectionStatus }) }) })), activeTab === 'activity' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "sapphire-section border border-warning-amber/35", children: [_jsx(AuroraField, { className: "-left-48 -top-52 h-[480px] w-[480px]", variant: "amber", intensity: "bold" }), _jsx(AuroraField, { className: "right-[-10rem] bottom-[-12rem] h-[500px] w-[500px]", variant: "sapphire" }), _jsxs("div", { className: "relative grid gap-8 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]", children: [_jsxs("div", { className: "space-y-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-warning-amber", children: "Mission Feed" }), _jsx("h2", { className: "text-3xl font-bold text-brand-ice", children: "Command & Control Stream" }), _jsx("p", { className: "text-sm leading-relaxed text-brand-muted", children: "Sapphire logs every orchestration event\u2014from MCP critiques to orchestrator overrides\u2014in an auditable lab journal. Filter for warnings, replay experiments, and trace causality without leaving the console." }), _jsxs("div", { className: "flex flex-wrap items-center gap-3", children: [_jsxs("span", { className: "sapphire-chip text-brand-midnight bg-gradient-to-r from-warning-amber/90 to-accent-aurora/80", children: [activitySummary.total, " Entries Tracked"] }), activitySummary.lastEntry && (_jsxs("span", { className: "sapphire-chip text-brand-midnight bg-gradient-to-r from-accent-aurora/90 to-warning-amber/80", children: ["Last update ", new Date(activitySummary.lastEntry.timestamp).toLocaleTimeString()] }))] })] }), _jsxs("div", { className: "grid gap-4 text-sm text-brand-ice sm:grid-cols-2", children: [_jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Success Signals" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: activitySummary.counts.success }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Orders landed smoothly" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Warnings" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-warning-amber", children: activitySummary.counts.warning }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Pre-emptive flags" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Errors" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-error", children: activitySummary.counts.error }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Needs immediate review" })] }), _jsxs("div", { className: "sapphire-panel p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Informational" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: activitySummary.counts.info }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Contextual telemetry" })] })] })] })] }), _jsx("div", { className: "sapphire-panel p-6", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "Activity Log", className: "h-[28rem]" }), children: _jsx(ActivityLog, { logs: logs }) }) }), _jsxs("div", { className: "grid grid-cols-1 gap-6 xl:grid-cols-2", children: [_jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "MCP Council", className: "h-[24rem]" }), children: _jsx(MCPCouncil, { messages: mcpMessages ?? [], status: mcpStatus ?? connectionStatus }) }), _jsxs("div", { className: "sapphire-panel p-6", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.3em] text-brand-muted", children: "Community Highlights" }), _jsx("h3", { className: "mt-2 text-lg font-semibold text-brand-ice", children: "See the collective in action" }), _jsx("p", { className: "mt-2 text-sm text-brand-muted", children: "Live sentiment, points, and feedback now live in the Community tab. Drop your vote and brief the agents with your sharpest takes." }), _jsx("button", { type: "button", onClick: () => setActiveTab('community'), className: "mt-4 inline-flex items-center gap-2 rounded-full bg-accent-sapphire/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-brand-midnight transition hover:bg-accent-sapphire", children: "Open Community Hub \u2192" })] })] })] })), activeTab === 'system' && (_jsxs("div", { className: "space-y-6", children: [_jsxs("section", { className: "sapphire-section border border-primary-500/25", children: [_jsx(AuroraField, { className: "-left-60 -top-60 h-[520px] w-[520px]", variant: "sapphire", intensity: "bold" }), _jsx(AuroraField, { className: "right-[-12rem] bottom-[-10rem] h-[520px] w-[520px]", variant: "emerald" }), _jsx("div", { className: "absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(96,165,250,0.18),_transparent_70%)]" }), _jsxs("div", { className: "relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]", children: [_jsxs("div", { className: "space-y-4", children: [_jsx("p", { className: "text-xs uppercase tracking-[0.35em] text-security-shield/70", children: "Reliability Core" }), _jsx("h2", { className: "text-3xl font-bold text-white", children: "Platform Resilience Console" }), _jsx("p", { className: "text-sm leading-relaxed text-brand-muted", children: "Snap the infrastructure healthline: orchestrator governance, trader loops, cache layer, and MCP connectivity. Everything routes through the load-balanced perimeter with security-first defaults." }), _jsxs("div", { className: "flex flex-wrap items-center gap-3", children: [_jsx("span", { className: "inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-brand-muted", children: connectionStatus === 'connected' ? 'Live MCP uplink' : 'MCP reconnecting' }), _jsxs("span", { className: `inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] ${cacheConnected ? 'bg-accent-emerald/20 text-accent-emerald' : 'bg-error/20 text-error'}`, children: ["Cache ", cacheConnected ? 'Synchronized' : 'Offline'] })] })] }), _jsxs("div", { className: "grid gap-4 text-sm text-brand-ice sm:grid-cols-2", children: [_jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Orchestrator" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: systemSummary.orchestratorStatus }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Risk governor status" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Cloud Trader" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: systemSummary.traderStatus }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Execution loop heartbeat" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "Last Update" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: systemSummary.timestamp ? new Date(systemSummary.timestamp).toLocaleString() : 'Awaiting telemetry' }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "System status timestamp" })] }), _jsxs("div", { className: "rounded-3xl border border-white/10 bg-black/20 p-5", children: [_jsx("p", { className: "text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted", children: "MCP Channel" }), _jsx("p", { className: "mt-2 text-2xl font-semibold text-brand-ice", children: connectionStatus === 'connected' ? 'Synchronized' : 'Recovering' }), _jsx("p", { className: "mt-1 text-xs text-brand-muted", children: "Mesh consensus transport" })] })] })] })] }), _jsxs("div", { className: "grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]", children: [_jsx("div", { className: "sapphire-panel p-6", children: _jsx(Suspense, { fallback: _jsx(SectionSkeleton, { title: "System Status", className: "h-[24rem]" }), children: _jsx(SystemStatus, { status: dashboardData?.system_status }) }) }), _jsx("div", { className: "sapphire-panel p-6", children: _jsx(StatusCard, { health: health ?? null, loading: loading }) })] })] }))] })) }) })] })] })] }), selectedAgentForHistory && (_jsx(HistoricalPerformance, { agent: selectedAgentForHistory, onClose: () => setSelectedAgentForHistory(null) }))] }));
};
const App = () => {
    const maintenanceMode = import.meta.env.VITE_MAINTENANCE_MODE === 'true';
    const [view, setView] = useState('landing');
    if (maintenanceMode) {
        return _jsx(MaintenancePage, {});
    }
    if (view === 'landing') {
        return (_jsxs(_Fragment, { children: [_jsx(LandingPage, { onEnterApp: () => setView('dashboard') }), _jsx(Toaster, { position: "top-right", toastOptions: {
                        duration: 4000,
                        style: {
                            background: 'rgba(15, 23, 42, 0.95)',
                            color: '#cbd5f5',
                            border: '1px solid rgba(59, 130, 246, 0.35)',
                        },
                    } })] }));
    }
    return _jsx(Dashboard, { onBackToHome: () => setView('landing') });
};
export default App;
