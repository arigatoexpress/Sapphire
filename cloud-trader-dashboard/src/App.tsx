import React, { Suspense, lazy, useState, useEffect, useMemo } from 'react';
import toast, { Toaster } from 'react-hot-toast';
import StatusCard from './components/StatusCard';
import PortfolioCard from './components/PortfolioCard';
import RiskMetrics from './components/RiskMetrics';
import Sidebar from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import MetricCard from './components/MetricCard';
import PortfolioPerformance from './components/charts/PortfolioPerformance';
import AuroraField from './components/visuals/AuroraField';
import { resolveTokenMeta } from './utils/tokenMeta';
import { useTraderService } from './hooks/useTraderService';
import { DashboardResponse, DashboardPosition } from './api/client';
import AgentCard from './components/AgentCard';
import CrowdSentimentWidget from './components/CrowdSentimentWidget';
import CommunityFeedback from './components/CommunityFeedback';
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

type RecentTrade = (DashboardResponse['recent_trades'] extends (infer T)[] ? T : never) & { pnl?: number };

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);

const formatNumber = (value: number) =>
  new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 0,
  }).format(value);

const formatMaskedPortfolioValue = (_value: number) => '%s';

const SectionSkeleton: React.FC<{ title?: string; className?: string }> = ({ title, className }) => (
  <div className={`rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-glass animate-pulse ${className ?? ''}`}>
    {title && <div className="mb-5 h-3 w-40 rounded-full bg-white/20" />}
    <div className="space-y-4">
      <div className="h-4 w-full rounded-full bg-white/10" />
      <div className="h-4 w-5/6 rounded-full bg-white/10" />
      <div className="h-4 w-4/6 rounded-full bg-white/10" />
    </div>
  </div>
);

const DashboardSkeleton: React.FC = () => (
  <div className="space-y-8">
    <SectionSkeleton title="Calibrating control nexus" />
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <SectionSkeleton className="h-40" />
      <SectionSkeleton className="h-40" />
      <SectionSkeleton className="h-40" />
    </div>
    <SectionSkeleton title="Streaming live trade telemetry" className="h-80" />
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <SectionSkeleton className="h-72" />
      <SectionSkeleton className="h-72" />
    </div>
  </div>
);

const CLOUD_RUN_REGION = 'us-central1';
const LOAD_BALANCER_IP = '34.117.165.111';
const TPU_FLEET_DESCRIPTION = 'LLM serving pods (DeepSeek, Qwen, Phi-3) TPU-ready via vLLM/llama.cpp stack';

const App: React.FC = () => {
  const { user, loading: authLoading, signIn, signOut, enabled: authEnabled, error: authError } = useAuth();
  const { health, dashboardData, loading, error, logs, connectionStatus, mcpMessages, mcpStatus, refresh } = useTraderService();
  const [crowdSentiment, castCrowdVote, resetCrowd] = useCrowdSentiment();
  const [communityComments, addCommunityComment] = useCommunityComments(user);
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'performance' | 'activity' | 'system'>('overview');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showLandingPage, setShowLandingPage] = useState(true);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);

  const handleEnterApp = () => {
    setShowLandingPage(false);
  };

  // Keyboard shortcuts
  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
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
        alerts: [] as string[],
        positions: [] as DashboardPosition[],
        agents: [] as DashboardResponse['agents'],
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

    const trades = dashboardData.recent_trades as RecentTrade[];
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
        topSymbols: [] as { symbol: string; notional: number }[],
      };
    }

    let longCount = 0;
    let shortCount = 0;
    let holdCount = 0;
    let totalNotional = 0;
    let netNotional = 0;
    const symbolMap = new Map<string, number>();

    derived.positions.forEach((pos) => {
      const side = String(pos.side ?? '').toUpperCase();
      const notional = Math.abs(Number(pos.notional) || 0);
      if (side === 'SELL' || side === 'SHORT') {
        shortCount += 1;
        netNotional -= notional;
      } else if (side === 'BUY' || side === 'LONG') {
        longCount += 1;
        netNotional += notional;
      } else {
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
    } else if (netNotional < 0) {
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
    const trades = (dashboardData?.recent_trades ?? []) as RecentTrade[];
    if (!trades.length) {
      return {
        totalTrades: 0,
        winRate: 0,
        totalNotional: 0,
        averageNotional: 0,
        sentiment: 'Awaiting execution',
        lastTrade: null as string | null,
      };
    }

    let wins = 0;
    let totalNotional = 0;
    let longCount = 0;
    let shortCount = 0;

    trades.forEach((trade) => {
      const pnl = Number(trade.pnl) || 0;
      if (pnl > 0) wins += 1;
      const notional = Math.abs(Number(trade.notional) || 0);
      totalNotional += notional;
      const side = String(trade.side ?? '').toUpperCase();
      if (side === 'BUY' || side === 'LONG') longCount += 1;
      if (side === 'SELL' || side === 'SHORT') shortCount += 1;
    });

    const winRate = trades.length ? (wins / trades.length) * 100 : 0;
    const averageNotional = trades.length ? totalNotional / trades.length : 0;
    let sentiment = 'Balanced flow';
    if (longCount > shortCount) sentiment = 'Long skew';
    if (shortCount > longCount) sentiment = 'Short skew';

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
        lastEntry: null as typeof logs[number] | null,
      };
    }

    const counts = logs.reduce(
      (acc, log) => ({ ...acc, [log.type]: (acc[log.type] ?? 0) + 1 }),
      { info: 0, success: 0, warning: 0, error: 0 }
    );

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
  ] as const;

  const sidebarTabs = tabs.map((tab) => ({ id: tab.id, label: tab.label, icon: tab.icon }));

  // Show landing page first
  if (showLandingPage) {
    return (
      <>
        <LandingPage onEnterApp={handleEnterApp} />
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: 'rgba(15, 23, 42, 0.95)',
              color: '#cbd5f5',
              border: '1px solid rgba(59, 130, 246, 0.35)',
            },
          }}
        />
      </>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white flex">
      <Sidebar
        tabs={sidebarTabs}
        activeTab={activeTab}
        onSelect={(id) => setActiveTab(id as typeof activeTab)}
        mobileMenuOpen={mobileMenuOpen}
        setMobileMenuOpen={setMobileMenuOpen}
      />
      <div className="flex-1 flex flex-col">
        <TopBar
          onRefresh={refresh}
          lastUpdated={dashboardData?.system_status?.timestamp}
          healthRunning={health?.running}
          mobileMenuOpen={mobileMenuOpen}
          setMobileMenuOpen={setMobileMenuOpen}
          onBackToHome={() => setShowLandingPage(true)}
          connectionStatus={connectionStatus}
          error={error}
          autoRefreshEnabled={autoRefreshEnabled}
          onToggleAutoRefresh={() => setAutoRefreshEnabled(!autoRefreshEnabled)}
        />
        <main className="flex-1 p-4 md:p-6 lg:p-8 overflow-y-auto">
          <div className="space-y-8">
            {loading ? (
              <DashboardSkeleton />
            ) : error ? (
              <div className="text-red-500">{error}</div>
            ) : (
              <>
                {activeTab === 'overview' && (
                  <div className="space-y-6">
                    {/* Key Metrics Dashboard */}
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                      <MetricCard
                        label="Portfolio Balance"
                        value={formatMaskedPortfolioValue(derived.balance)}
                        accent="emerald"
                        footer={<span>Live account equity</span>}
                      />
                      <MetricCard
                        label="Live Agent P&L"
                        value={formatCurrency(derived.totalAgentPnL)}
                        accent="teal"
                        footer={<span>Combined unrealized result</span>}
                      />
                      <MetricCard
                        label="Available Margin"
                        value={formatCurrency(derived.availableBalance)}
                        accent="slate"
                        footer={<span>Deployable capital</span>}
                      />
                      <MetricCard
                        label="Active Positions"
                        value={derived.positions.length}
                        accent="amber"
                        footer={<span>Across all agents</span>}
                      />
                    </div>

                    {/* System Status Overview */}
                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                      <StatusCard health={health} loading={loading} />
                      <div className="rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass">
                        <div className="mb-4">
                          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Trading Status</p>
                          <h3 className="mt-2 text-lg font-semibold text-white">System Health</h3>
                        </div>
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate-300">Trader Service</span>
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                              traderStatus === 'running' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300'
                            }`}>
                              {traderStatus}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate-300">Redis Connection</span>
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                              redisOnline ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'
                            }`}>
                              {redisOnline ? 'Online' : 'Offline'}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm text-slate-300">Active Agents</span>
                            <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-500/20 text-blue-300">
                              {derived.activeAgents}/{configuredAgents}
                            </span>
                          </div>
                        </div>
                      </div>
                      <TargetsAndAlerts targets={dashboardData?.targets} />
                    </div>

                    {/* Agent Performance Overview */}
                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                      {derived.agents.length > 0 ? (
                        derived.agents.map((agent) => (
                          <AgentCard
                            key={agent.id}
                            agent={agent}
                            onClick={() => {
                              toast.success(`${agent.name} metrics refreshed`, {
                                duration: 2000,
                                style: {
                                  background: 'rgba(15, 23, 42, 0.95)',
                                  color: '#cbd5f5',
                                  border: '1px solid rgba(59, 130, 246, 0.35)',
                                },
                              });
                            }}
                          />
                        ))
                      ) : (
                        <div className="rounded-2xl border border-surface-200/40 bg-surface-100/60 p-8 text-center text-slate-400 shadow-glass">
                          <p className="text-lg font-semibold text-white">Awaiting live trades</p>
                          <p className="mt-2 text-sm text-slate-400">
                            Start the traders to stream real positions and model performance here.
                          </p>
                        </div>
                      )}
                    </div>

                    {/* Portfolio Performance Chart */}
                    <div className="rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass">
                      <div className="mb-4 flex items-center justify-between">
                        <div>
                          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Portfolio Performance</p>
                          <h3 className="mt-2 text-xl font-semibold text-white">Balance & Price Trends</h3>
                        </div>
                      </div>
                      <PortfolioPerformance balanceSeries={performanceSeries.balance} priceSeries={performanceSeries.price} />
                    </div>
                  </div>
                )}

                {activeTab === 'positions' && (
                  <div className="space-y-6">
                    <section className="relative overflow-hidden rounded-4xl border border-accent-ai/30 bg-surface-75/70 p-8 shadow-glass-xl">
                      <AuroraField className="-left-64 -top-64 h-[520px] w-[520px]" variant="emerald" intensity="bold" />
                      <AuroraField className="right-[-10rem] bottom-[-12rem] h-[540px] w-[540px]" variant="sapphire" />
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(20,184,166,0.18),_transparent_70%)]" />
                      <div className="absolute -right-24 top-1/2 h-64 w-64 -translate-y-1/2 rounded-full bg-accent-ai/10 blur-3xl" />
                      <div className="relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
                        <div className="space-y-4">
                          <p className="text-xs uppercase tracking-[0.35em] text-accent-ai/70">Exposure Lab</p>
                          <h2 className="text-3xl font-bold text-white">Agent Exposure Monitor</h2>
                          <p className="text-sm leading-relaxed text-slate-300">
                            Track how each Sapphire agent is expressing conviction in the market right now. Radar-driven allocation keeps leverage disciplined while highlighting the heaviest targets on deck.
                          </p>
                          <div className="flex flex-wrap items-center gap-3">
                            <span className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] ${positionInsights.netNotional > 0 ? 'bg-emerald-400/20 text-emerald-200' : positionInsights.netNotional < 0 ? 'bg-rose-400/20 text-rose-200' : 'bg-slate-500/20 text-slate-200'}`}>
                              {positionInsights.sentiment}
                            </span>
                            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-slate-200">
                              {derived.positions.length} Active Positions
                            </span>
                          </div>
                        </div>
                        <div className="grid gap-4 text-sm text-slate-200 sm:grid-cols-2">
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Net Notional</p>
                            <p className={`mt-2 text-2xl font-semibold ${positionInsights.netNotional >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>{formatCurrency(positionInsights.netNotional)}</p>
                            <p className="mt-1 text-xs text-slate-400">Long minus short exposure (USD)</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Gross Notional</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{formatCurrency(positionInsights.totalNotional)}</p>
                            <p className="mt-1 text-xs text-slate-400">All positions aggregated</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Long / Short</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{positionInsights.longCount} / {positionInsights.shortCount}</p>
                            <p className="mt-1 text-xs text-slate-400">Directional conviction split</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Hold-Ready</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{positionInsights.holdCount}</p>
                            <p className="mt-1 text-xs text-slate-400">Agents waiting for better fills</p>
                          </div>
                        </div>
                      </div>
                    </section>

                    {positionInsights.topSymbols.length > 0 && (
                      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                        {positionInsights.topSymbols.map(({ symbol, notional }) => {
                          const meta = resolveTokenMeta(symbol);
                          return (
                            <div key={symbol} className="relative overflow-hidden rounded-3xl border border-white/10 bg-surface-75/70 p-5 shadow-glass">
                              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(148,163,255,0.18),_transparent_75%)]" />
                              <div className="relative flex items-start justify-between gap-4">
                                <div className={`flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br ${meta.gradient} text-sm font-bold text-white shadow-lg`}>{meta.short}</div>
                                <div className="text-right">
                                  <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Focus Notional</p>
                                  <p className="mt-2 text-lg font-semibold text-white">{formatCurrency(notional)}</p>
                                  <p className="text-xs text-slate-400">{meta.name}</p>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    <Suspense fallback={<SectionSkeleton title="Live Positions" className="h-72" />}>
                      <LivePositions positions={derived.positions} />
                    </Suspense>
                  </div>
                )}

                {activeTab === 'performance' && (
                  <div className="space-y-6">
                    <section className="relative overflow-hidden rounded-4xl border border-emerald-400/30 bg-surface-75/70 p-8 shadow-glass-xl">
                      <AuroraField className="-left-60 -top-60 h-[520px] w-[520px]" variant="emerald" intensity="bold" />
                      <AuroraField className="right-[-12rem] bottom-[-8rem] h-[500px] w-[500px]" variant="amber" />
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(16,185,129,0.18),_transparent_70%)]" />
                      <div className="relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
                        <div className="space-y-4">
                          <p className="text-xs uppercase tracking-[0.35em] text-emerald-200/80">PnL Observatory</p>
                          <h2 className="text-3xl font-bold text-white">Momentum Performance Console</h2>
                          <p className="text-sm leading-relaxed text-slate-300">
                            Follow the rolling dialogue between balance trajectory, fills, and realised PnL. Strategies publish their thesis into the MCP log before every trade—this console shows how conviction translates into performance.
                          </p>
                          <div className="flex flex-wrap items-center gap-3">
                            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-slate-200">
                              {performanceInsights.totalTrades} Trades Observed
                            </span>
                            <span className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] bg-emerald-400/20 text-emerald-200">
                              {performanceInsights.sentiment}
                            </span>
                          </div>
                        </div>
                        <div className="grid gap-4 text-sm text-slate-200 sm:grid-cols-2">
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Win Rate</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{performanceInsights.winRate.toFixed(1)}%</p>
                            <p className="mt-1 text-xs text-slate-400">Across recent trade set</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Average Notional</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{formatCurrency(performanceInsights.averageNotional)}</p>
                            <p className="mt-1 text-xs text-slate-400">Per executed trade</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Total Notional</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{formatCurrency(performanceInsights.totalNotional)}</p>
                            <p className="mt-1 text-xs text-slate-400">Cumulative deployment</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Last Trade</p>
                            <p className="mt-2 text-2xl font-semibold text-white">
                              {performanceInsights.lastTrade
                                ? new Date(performanceInsights.lastTrade).toLocaleString()
                                : 'Awaiting Fill'}
                            </p>
                            <p className="mt-1 text-xs text-slate-400">Local environment time</p>
                          </div>
                        </div>
                      </div>
                    </section>

                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
                      <div className="overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Balance Trajectory</p>
                            <h3 className="mt-2 text-lg font-semibold text-white">Capital vs Guiding Price</h3>
                          </div>
                        </div>
                        <div className="mt-4">
                          <PortfolioPerformance balanceSeries={performanceSeries.balance} priceSeries={performanceSeries.price} />
                        </div>
                      </div>
                      <div className="overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass">
                        <Suspense fallback={<SectionSkeleton title="Trade Trends" className="h-72" />}>
                          <PerformanceTrends trades={dashboardData?.recent_trades || []} />
                        </Suspense>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                      <div className="overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass">
                        <RiskMetrics portfolio={dashboardData?.portfolio} />
                      </div>
                      <div className="overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass">
                        <Suspense fallback={<SectionSkeleton title="Targets & Alerts" className="h-72" />}>
                          <TargetsAndAlerts targets={dashboardData?.targets} />
                        </Suspense>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                      <Suspense fallback={<SectionSkeleton title="Model Performance" className="h-[28rem]" />}>
                        <ModelPerformance models={dashboardData?.model_performance ?? []} />
                      </Suspense>
                      <Suspense fallback={<SectionSkeleton title="Model Reasoning" className="h-[28rem]" />}>
                        <ModelReasoning reasoning={dashboardData?.model_reasoning ?? []} />
                      </Suspense>
                    </div>
                  </div>
                )}

                {activeTab === 'activity' && (
                  <div className="space-y-6">
                    <section className="relative overflow-hidden rounded-4xl border border-amber-400/30 bg-surface-75/70 p-8 shadow-glass-xl">
                      <AuroraField className="-left-48 -top-52 h-[480px] w-[480px]" variant="amber" intensity="bold" />
                      <AuroraField className="right-[-10rem] bottom-[-12rem] h-[500px] w-[500px]" variant="sapphire" />
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(251,191,36,0.18),_transparent_70%)]" />
                      <div className="relative grid gap-8 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
                        <div className="space-y-4">
                          <p className="text-xs uppercase tracking-[0.35em] text-amber-200/80">Mission Feed</p>
                          <h2 className="text-3xl font-bold text-white">Command & Control Stream</h2>
                          <p className="text-sm leading-relaxed text-slate-300">
                            Sapphire logs every orchestration event—from MCP critiques to orchestrator overrides—in an auditable lab journal. Filter for warnings, replay experiments, and trace causality without leaving the console.
                          </p>
                          <div className="flex flex-wrap items-center gap-3">
                            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-slate-200">
                              {activitySummary.total} Entries Tracked
                            </span>
                            {activitySummary.lastEntry && (
                              <span className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] bg-amber-400/20 text-amber-100">
                                Last update {new Date(activitySummary.lastEntry.timestamp).toLocaleTimeString()}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="grid gap-4 text-sm text-slate-200 sm:grid-cols-2">
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Success Signals</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{activitySummary.counts.success}</p>
                            <p className="mt-1 text-xs text-slate-400">Orders landed smoothly</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Warnings</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{activitySummary.counts.warning}</p>
                            <p className="mt-1 text-xs text-slate-400">Pre-emptive flags</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Errors</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{activitySummary.counts.error}</p>
                            <p className="mt-1 text-xs text-slate-400">Needs immediate review</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Informational</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{activitySummary.counts.info}</p>
                            <p className="mt-1 text-xs text-slate-400">Contextual telemetry</p>
                          </div>
                        </div>
                      </div>
                    </section>

                    <div className="overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass">
                      <Suspense fallback={<SectionSkeleton title="Activity Log" className="h-[28rem]" />}>
                        <ActivityLog logs={logs} />
                      </Suspense>
                    </div>

                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                      <Suspense fallback={<SectionSkeleton title="MCP Council" className="h-[24rem]" />}>
                        <MCPCouncil messages={mcpMessages ?? []} status={mcpStatus ?? connectionStatus} />
                      </Suspense>
                      <div className="overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass">
                        <CrowdSentimentWidget
                          totalVotes={crowdSentiment.totalVotes}
                          bullishVotes={crowdSentiment.bullishVotes}
                          bearishVotes={crowdSentiment.bearishVotes}
                          onVote={castCrowdVote}
                          onReset={resetCrowd}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === 'system' && (
                  <div className="space-y-6">
                    <section className="relative overflow-hidden rounded-4xl border border-security-shield/40 bg-surface-75/70 p-8 shadow-glass-xl">
                      <AuroraField className="-left-60 -top-60 h-[520px] w-[520px]" variant="sapphire" intensity="bold" />
                      <AuroraField className="right-[-12rem] bottom-[-10rem] h-[520px] w-[520px]" variant="emerald" />
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(96,165,250,0.18),_transparent_70%)]" />
                      <div className="relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
                        <div className="space-y-4">
                          <p className="text-xs uppercase tracking-[0.35em] text-security-shield/70">Reliability Core</p>
                          <h2 className="text-3xl font-bold text-white">Platform Resilience Console</h2>
                          <p className="text-sm leading-relaxed text-slate-300">
                            Snap the infrastructure healthline: orchestrator governance, trader loops, Redis, and MCP connectivity. Everything routes through the load-balanced perimeter with security-first defaults.
                          </p>
                          <div className="flex flex-wrap items-center gap-3">
                            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-slate-200">
                              {connectionStatus === 'connected' ? 'Live MCP uplink' : 'MCP reconnecting'}
                            </span>
                            <span className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] ${systemSummary.redisConnected ? 'bg-emerald-400/20 text-emerald-200' : 'bg-rose-400/20 text-rose-200'}`}>
                              Redis {systemSummary.redisConnected ? 'Synchronized' : 'Offline'}
                            </span>
                          </div>
                        </div>
                        <div className="grid gap-4 text-sm text-slate-200 sm:grid-cols-2">
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Orchestrator</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{systemSummary.orchestratorStatus}</p>
                            <p className="mt-1 text-xs text-slate-400">Risk governor status</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Cloud Trader</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{systemSummary.traderStatus}</p>
                            <p className="mt-1 text-xs text-slate-400">Execution loop heartbeat</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Last Update</p>
                            <p className="mt-2 text-2xl font-semibold text-white">
                              {systemSummary.timestamp ? new Date(systemSummary.timestamp).toLocaleString() : 'Awaiting telemetry'}
                            </p>
                            <p className="mt-1 text-xs text-slate-400">System status timestamp</p>
                          </div>
                          <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">MCP Channel</p>
                            <p className="mt-2 text-2xl font-semibold text-white">{connectionStatus === 'connected' ? 'Synchronized' : 'Recovering'}</p>
                            <p className="mt-1 text-xs text-slate-400">Mesh consensus transport</p>
                          </div>
                        </div>
                      </div>
                    </section>

                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
                      <div className="overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass">
                        <Suspense fallback={<SectionSkeleton title="System Status" className="h-[24rem]" />}>
                          <SystemStatus status={dashboardData?.system_status} />
                        </Suspense>
                      </div>
                      <div className="overflow-hidden rounded-4xl border border-white/10 bg-surface-75/70 p-6 shadow-glass">
                        <StatusCard health={health ?? null} loading={loading} />
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
};

export default App;

