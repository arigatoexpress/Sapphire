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
import { DashboardResponse, DashboardPosition, DashboardAgent } from './api/client';
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

type RecentTrade = (DashboardResponse['recent_trades'] extends (infer T)[] ? T : never) & { pnl?: number };

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);

const formatMaskedPortfolioValue = (value: number) => {
  void value;
  return '%s';
};

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
    <SectionSkeleton title="Initializing trading system" />
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

const MaintenancePage: React.FC = () => (
  <div className="min-h-screen bg-brand-midnight text-brand-ice relative overflow-hidden flex items-center justify-center p-6">
    <div className="pointer-events-none absolute inset-0 bg-sapphire-mesh opacity-60" />
    <div className="pointer-events-none absolute inset-0 bg-sapphire-strata opacity-50" />
    <div className="relative max-w-3xl rounded-4xl border border-brand-border/70 bg-brand-abyss/80 p-10 text-center shadow-sapphire">
      <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-accent-blue/20 text-3xl">
        ⏳
      </div>
      <h1 className="text-3xl font-bold tracking-wide text-brand-ice">Sapphire is calibrating for launch</h1>
      <p className="mt-4 text-brand-ice/80 leading-relaxed">
        We&apos;re applying final production upgrades to the live trading stack and refreshing all community data.
        The dashboard will reopen by <span className="text-brand-accent-blue font-semibold">10:30 PM Central Time</span>
        with the full Sapphire experience.
      </p>
      <div className="mt-8 space-y-2 text-sm text-brand-ice/60">
        <p>• Live traders remain on risk-managed standby during this upgrade window.</p>
        <p>• Telegram alerts will resume automatically once trading restarts.</p>
        <p>• Follow updates on Twitter/X: <span className="text-brand-accent-blue">@rari_sui</span></p>
      </div>
    </div>
  </div>
);

// This is the new, self-contained Dashboard component.
// All hooks and data logic now live here, ensuring they are always called in the same order.
const Dashboard: React.FC<{ onBackToHome: () => void }> = ({ onBackToHome }) => {
  const { health, dashboardData, loading, error, logs, connectionStatus, mcpMessages, mcpStatus, refresh } = useTraderService();
  const [selectedAgentForHistory, setSelectedAgentForHistory] = React.useState<DashboardAgent | null>(null);
  const {
    user,
    loading: authLoading,
    signInWithSocial,
    signOut: authSignOut,
    signInWithEmail,
    signUpWithEmail,
    enabled: authEnabled,
    error: authError,
  } = useAuth();
  const [communityComments, submitCommunityComment, commentsLoading] = useCommunityComments(user);
  const [leaderboardEntries, leaderboardLoading] = useCommunityLeaderboard(15);
  const [crowdSentiment, registerCrowdVote, resetCrowd, sentimentLoading] = useCrowdSentiment(user);
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'performance' | 'community' | 'activity' | 'system' | 'council'>('overview');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [commentSubmitting, setCommentSubmitting] = useState(false);
  const realtimeCommunity = isRealtimeCommunityEnabled();

  React.useEffect(() => {
    if (user && realtimeCommunity) {
      recordCheckIn(user).catch((err: unknown) => {
        if (import.meta.env.DEV) {
          console.warn('[community] failed to record daily check-in', err);
        }
      });
    }
  }, [user, realtimeCommunity]);

  // Keyboard shortcuts
  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
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
  ] as const;

  const sidebarTabs = tabs.map((tab) => ({ id: tab.id, label: tab.label, icon: tab.icon }));

  const handleSocialSignIn = async (provider: 'google' | 'facebook' | 'apple') => {
    if (!authEnabled) {
      toast.error('Community sign-in is currently disabled in this environment.');
      return;
    }
    try {
      await signInWithSocial(provider);
      toast.success('Signed in—welcome to the Sapphire Collective.');
    } catch (signInError) {
      const message = signInError instanceof Error ? signInError.message : 'Unable to sign in right now.';
      toast.error(message);
      throw signInError;
    }
  };

  const handleAuthenticate = () => {
    void handleSocialSignIn('google');
  };

  const handleEmailSignIn = async (email: string, password: string) => {
    try {
      await signInWithEmail(email, password);
      toast.success('Signed in—your voice is live.');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to sign in right now.';
      toast.error(message);
      throw err;
    }
  };

  const handleEmailSignUp = async (email: string, password: string, displayName?: string) => {
    try {
      await signUpWithEmail(email, password, displayName);
      toast.success('Account created. Welcome aboard!');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to create account right now.';
      toast.error(message);
      throw err;
    }
  };

  const handleCrowdVote = (vote: 'bullish' | 'bearish') => {
    if (!user) {
      toast.error('Authenticate to cast your signal.');
      return;
    }
    void (async () => {
      try {
        await registerCrowdVote(vote);
        toast.success('Signal received. Thanks for steering the desk!');
      } catch (voteError) {
        const message = voteError instanceof Error ? voteError.message : 'Failed to record vote';
        toast.error(message);
      }
    })();
  };

  const handleCommentSubmit = async (message: string) => {
    if (!user) {
      toast.error('Sign in to leave feedback for the agents.');
      return;
    }
    setCommentSubmitting(true);
    try {
      await submitCommunityComment(message);
      toast.success('Feedback sent to the council.');
    } catch (commentError) {
      const message = commentError instanceof Error ? commentError.message : 'Failed to send feedback';
      toast.error(message);
      throw commentError;
    } finally {
      setCommentSubmitting(false);
    }
  };

  const handleSignOut = async () => {
    try {
      await authSignOut();
      toast.success('Signed out. See you on the next session.');
    } catch (signOutError) {
      const message = signOutError instanceof Error ? signOutError.message : 'Failed to sign out';
      toast.error(message);
    }
  };

  return (
    <>
      <AnalyticsManager />
      <div className="relative min-h-screen overflow-hidden bg-brand-midnight text-brand-ice">
        <div className="pointer-events-none absolute inset-0 bg-sapphire-strata" />
        <div className="pointer-events-none absolute inset-0 bg-sapphire-mesh opacity-80" />
        <div className="relative flex min-h-screen">
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
              onBackToHome={onBackToHome}
              connectionStatus={connectionStatus}
              error={error}
              autoRefreshEnabled={autoRefreshEnabled}
              onToggleAutoRefresh={() => setAutoRefreshEnabled(!autoRefreshEnabled)}
            />
            <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
              <div className="space-y-8">
                {loading ? (
                  <DashboardSkeleton />
                ) : error ? (
                  <div className="flex items-center justify-center min-h-[400px]">
                    <div className="text-center space-y-6 max-w-md mx-auto">
                      <div className="relative">
                        <div className="w-16 h-16 mx-auto rounded-full bg-error/10 flex items-center justify-center">
                          <svg className="w-8 h-8 text-error" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                          </svg>
                        </div>
                        <div className="absolute -top-2 -right-2 w-6 h-6 bg-error rounded-full flex items-center justify-center">
                          <span className="text-xs text-white font-bold">!</span>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <h3 className="text-xl font-semibold text-brand-ice">Connection Error</h3>
                        <p className="text-brand-muted/80 text-sm leading-relaxed">
                          Unable to connect to the trading service. This might be a temporary network issue.
                        </p>
                        <div className="bg-error/10 border border-error/30 rounded-lg p-3 mt-4">
                          <p className="text-error/80 text-xs font-mono break-words">{error}</p>
                        </div>
                      </div>

                      <div className="flex gap-3 justify-center">
                        <button
                          onClick={refresh}
                          className="px-4 py-2 bg-accent-sapphire/80 hover:bg-accent-sapphire text-brand-midnight text-sm font-medium rounded-lg transition-colors duration-200 flex items-center gap-2"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                          Retry Connection
                        </button>

                        <button
                          onClick={() => window.location.reload()}
                          className="px-4 py-2 bg-brand-border/60 hover:bg-brand-border/80 text-brand-ice text-sm font-medium rounded-lg transition-colors duration-200"
                        >
                          Reload Page
                        </button>
                      </div>

                      <div className="text-xs text-brand-muted/70 space-y-1">
                        <p>• Check your internet connection</p>
                        <p>• The trading service might be restarting</p>
                        <p>• Try refreshing the page in a few moments</p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    {activeTab === 'overview' && (
                      <div className="space-y-6">
                        <section className="sapphire-section flex flex-col gap-6 rounded-4xl p-8 lg:flex-row lg:items-center">
                          <div className="flex-1 space-y-6">
                            <span className="inline-flex items-center gap-2 rounded-full border border-accent-sapphire/40 bg-brand-abyss/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.32em] text-accent-sapphire">
                              Command Center
                            </span>
                            <div className="space-y-3">
                              <h2 className="text-3xl font-bold text-brand-ice">
                                Live trading telemetry at a glance
                              </h2>
                              <p className="max-w-2xl text-sm leading-relaxed text-brand-muted">
                                4 AI agents trading 154 symbols with intelligent risk management.
                              </p>
                            </div>
                            <div className="grid gap-3 sm:grid-cols-2">
                              <div className="rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-5 shadow-sapphire-sm">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted/70">Status</p>
                                <p className="mt-2 text-xl font-semibold text-brand-ice">Live Trading</p>
                                <p className="mt-1 text-xs text-brand-muted">$350 daily target, max profit optimization.</p>
                              </div>
                              <div className="rounded-2xl border border-brand-border/60 bg-brand-abyss/70 p-5 shadow-sapphire-sm">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted/70">Risk Control</p>
                                <p className="mt-2 text-xl font-semibold text-brand-ice">Active</p>
                                <p className="mt-1 text-xs text-brand-muted">Liquidation protection, adaptive leverage.</p>
                              </div>
                            </div>
                            <div className="flex flex-wrap items-center gap-3 pt-2 text-xs text-brand-muted/70">
                              <span className="inline-flex items-center gap-2 rounded-full border border-brand-border/50 bg-brand-abyss/80 px-4 py-2 font-semibold uppercase tracking-[0.28em] text-brand-ice/80">
                                {configuredAgents} Agents Coordinated
                              </span>
                              <span className="inline-flex items-center gap-2 rounded-full border border-brand-border/50 bg-brand-abyss/80 px-4 py-2 font-semibold uppercase tracking-[0.28em] text-brand-ice/80">
                                Cache Backend: {cacheBackend}
                              </span>
                            </div>
                          </div>
                          <div className="relative w-full max-w-sm rounded-3xl border border-brand-border/60 bg-brand-abyss/80 p-6 shadow-sapphire overflow-hidden">
                            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(79,209,255,0.22),_transparent_65%)]" />
                            <div className="relative space-y-4 text-sm text-brand-ice">
                              <p className="text-xs uppercase tracking-[0.35em] text-brand-muted/80">Quick View</p>
                              <h3 className="text-lg font-semibold text-brand-ice">What to watch</h3>
                              <ul className="space-y-2 text-xs text-brand-muted/75">
                                <li>• Fills & exposure update every refresh interval.</li>
                                <li>• System tab shows cache/storage/pubsub health without Redis.</li>
                                <li>• Community tab surfaces feedback that agents may reference.</li>
                              </ul>
                              <div className="rounded-2xl border border-brand-border/50 bg-brand-midnight/80 p-3 text-xs text-brand-muted">
                                <p>Telemetry runs entirely on GCP: Pub/Sub for streaming, Cloud SQL + BigQuery for history, and in-memory caching for fast reads.</p>
                              </div>
                            </div>
                          </div>
                        </section>

                        <section className="sapphire-section rounded-4xl border border-brand-border/60 bg-brand-abyss/80 p-6 shadow-sapphire">
                          <header className="flex flex-col gap-3 text-brand-ice/80 md:flex-row md:items-center md:justify-between">
                            <div>
                              <p className="text-xs uppercase tracking-[0.35em] text-brand-ice/70">Open-source intelligence core</p>
                              <h3 className="text-2xl font-semibold text-brand-ice">Multi-Agent AI Stack: FinGPT + Lag-LLaMA</h3>
                            </div>
                            <p className="text-sm md:max-w-xl">
                              Sapphire queries multiple AI agents in parallel for AVAX and ARB symbols, synthesizing their perspectives for enhanced accuracy. Both agents collaborate simultaneously, with intelligent thesis selection based on confidence and risk scores. All signals stay within our secure Vertex/GCP boundary, with privacy-preserving inference and community-auditable reasoning.
                            </p>
                          </header>
                          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
                            <article className="relative overflow-hidden rounded-3xl border border-brand-border/60 bg-brand-abyss/70 p-5 shadow-sapphire-sm">
                              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(79,70,229,0.24),_transparent_65%)]" />
                              <div className="relative space-y-3">
                                <div className="inline-flex items-center gap-2 rounded-full bg-brand-accent-blue/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-brand-accent-blue">
                                  🧠 FinGPT Alpha
                                </div>
                                <p className="text-sm text-brand-ice/80">
                                  Primary thesis generator for AVAX markets with parallel collaboration with Lag-Llama. Outputs structured reasoning, risk scoring, and confidence. Queries happen simultaneously with Lag-Llama for multi-perspective analysis. Hallucination guardrails and risk threshold enforcement ensure only high-quality theses reach execution.
                                </p>
                                <ul className="space-y-2 text-xs text-brand-ice/70">
                                  <li>• Parallel queries with Lag-Llama for AVAX symbols.</li>
                                  <li>• Response caching (10s TTL) reduces redundant API calls by 50-70%.</li>
                                  <li>• Retry logic with exponential backoff for reliability.</li>
                                  <li>• Risk threshold enforcement (default 0.7) filters low-quality theses.</li>
                                  <li>• Enhanced prompts with DeFi context and volatility regime detection.</li>
                                </ul>
                              </div>
                            </article>
                            <article className="relative overflow-hidden rounded-3xl border border-brand-border/60 bg-brand-abyss/70 p-5 shadow-sapphire-sm">
                              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(34,197,94,0.22),_transparent_65%)]" />
                              <div className="relative space-y-3">
                                <div className="inline-flex items-center gap-2 rounded-full bg-brand-accent-teal/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-brand-accent-teal">
                                  🦙 Lag-LLaMA Visionary
                                </div>
                                <p className="text-sm text-brand-ice/80">
                                  Primary time-series forecaster for ARB markets with parallel collaboration with FinGPT. Generates probabilistic forecasts with confidence bands and anomaly detection. Queries happen simultaneously with FinGPT for sentiment + time-series synthesis. CI span validation (over 20% rejected) keeps execution disciplined.
                                </p>
                                <ul className="space-y-2 text-xs text-brand-ice/70">
                                  <li>• Parallel queries with FinGPT for ARB symbols.</li>
                                  <li>• Forecast validation rejects predictions over 50% away from current price.</li>
                                  <li>• CI span validation (max 20%) prevents overconfident trades.</li>
                                  <li>• Anomaly detection integration for regime shift identification.</li>
                                  <li>• Time-series enrichment with on-chain volume data.</li>
                                </ul>
                              </div>
                            </article>
                          </div>
                        </section>

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
                          <div className="sapphire-panel p-6">
                            <div className="mb-4">
                              <p className="text-xs uppercase tracking-[0.3em] text-brand-muted/80">Trading Status</p>
                              <h3 className="mt-2 text-lg font-semibold text-brand-ice">System Health</h3>
                            </div>
                            <div className="space-y-3">
                              <div className="flex items-center justify-between">
                                <span className="text-sm text-brand-muted">Trader Service</span>
                                <span className={`px-2 py-1 rounded-full text-xs font-medium ${traderStatus === 'running' ? 'bg-accent-emerald/30 text-accent-emerald' : 'bg-warning-amber/30 text-warning-amber'
                                  }`}>
                                  {traderStatus}
                                </span>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-sm text-brand-muted">Cache Backend ({cacheBackend})</span>
                                <span className={`px-2 py-1 rounded-full text-xs font-medium ${cacheConnected ? 'bg-accent-emerald/30 text-accent-emerald' : 'bg-error/20 text-error'
                                  }`}>
                                  {cacheConnected ? 'Online' : 'Offline'}
                                </span>
                              </div>
                              <div className="flex items-center justify-between">
                                <span className="text-sm text-brand-muted">Active Agents</span>
                                <span className="px-2 py-1 rounded-full text-xs font-medium bg-accent-sapphire/20 text-accent-sapphire">
                                  {derived.activeAgents}/{configuredAgents}
                                </span>
                              </div>
                            </div>
                          </div>
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
                                      background: 'rgba(4, 16, 41, 0.95)',
                                      color: '#d9ecff',
                                      border: '1px solid rgba(79, 209, 255, 0.25)',
                                    },
                                  });
                                }}
                                onViewHistory={(agent) => setSelectedAgentForHistory(agent)}
                              />
                            ))
                          ) : (
                            <div className="sapphire-panel p-8 text-center text-brand-muted">
                              <p className="text-lg font-semibold text-brand-ice">Awaiting live trades</p>
                              <p className="mt-2 text-sm text-brand-muted">
                                Start the traders to stream real positions and model performance here.
                              </p>
                            </div>
                          )}
                        </div>

                        {/* Portfolio Performance Chart */}
                        <div className="sapphire-panel p-6">
                          <div className="mb-4 flex items-center justify-between">
                            <div>
                              <p className="text-xs uppercase tracking-[0.3em] text-brand-muted/80">Portfolio Performance</p>
                              <h3 className="mt-2 text-xl font-semibold text-brand-ice">Balance & Price Trends</h3>
                            </div>
                          </div>
                          <PortfolioPerformance balanceSeries={performanceSeries.balance} priceSeries={performanceSeries.price} />
                        </div>
                      </div>
                    )}

                    {activeTab === 'positions' && (
                      <div className="space-y-6">
                        <section className="sapphire-section border border-accent-emerald/25">
                          <AuroraField className="-left-64 -top-64 h-[520px] w-[520px]" variant="emerald" intensity="bold" />
                          <AuroraField className="right-[-10rem] bottom-[-12rem] h-[540px] w-[540px]" variant="sapphire" />
                          <div className="relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
                            <div className="space-y-4">
                              <p className="text-xs uppercase tracking-[0.35em] text-accent-emerald/80">Exposure Lab</p>
                              <h2 className="text-3xl font-bold text-brand-ice">Agent Exposure Monitor</h2>
                              <p className="text-sm leading-relaxed text-brand-muted">
                                Track how each Sapphire agent is expressing conviction in the market right now. Radar-driven allocation keeps leverage disciplined while highlighting the heaviest targets on deck.
                              </p>
                              <div className="flex flex-wrap items-center gap-3">
                                <span className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] ${positionInsights.netNotional > 0 ? 'bg-accent-emerald/20 text-accent-emerald' : positionInsights.netNotional < 0 ? 'bg-error/20 text-error' : 'bg-brand-border/40 text-brand-muted'}`}>
                                  {positionInsights.sentiment}
                                </span>
                                <span className="inline-flex items-center gap-2 rounded-full border border-brand-border/60 bg-brand-abyss/80 px-4 py-2 text-xs uppercase tracking-[0.28em] text-brand-muted">
                                  {derived.positions.length} Active Positions
                                </span>
                              </div>
                            </div>
                            <div className="grid gap-4 text-sm text-brand-ice sm:grid-cols-2">
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Net Notional</p>
                                <p className={`mt-2 text-2xl font-semibold ${positionInsights.netNotional >= 0 ? 'text-accent-emerald' : 'text-error'}`}>{formatCurrency(positionInsights.netNotional)}</p>
                                <p className="mt-1 text-xs text-brand-muted">Long minus short exposure (USD)</p>
                              </div>
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Gross Notional</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{formatCurrency(positionInsights.totalNotional)}</p>
                                <p className="mt-1 text-xs text-brand-muted">All positions aggregated</p>
                              </div>
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Long / Short</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{positionInsights.longCount} / {positionInsights.shortCount}</p>
                                <p className="mt-1 text-xs text-brand-muted">Directional conviction split</p>
                              </div>
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Hold-Ready</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{positionInsights.holdCount}</p>
                                <p className="mt-1 text-xs text-brand-muted">Agents waiting for better fills</p>
                              </div>
                            </div>
                          </div>
                        </section>

                        {positionInsights.topSymbols.length > 0 && (
                          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                            {positionInsights.topSymbols.map(({ symbol, notional }) => {
                              const meta = resolveTokenMeta(symbol);
                              return (
                                <div key={symbol} className="sapphire-panel p-5">
                                  <div className="relative flex items-start justify-between gap-4">
                                    <div className={`flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br ${meta.gradient} text-sm font-bold text-white shadow-lg`}>
                                      {meta.short}
                                    </div>
                                    <div className="text-right">
                                      <p className="text-xs uppercase tracking-[0.28em] text-brand-muted">Focus Notional</p>
                                      <p className="mt-2 text-lg font-semibold text-brand-ice">{formatCurrency(notional)}</p>
                                      <p className="text-xs text-brand-muted">{meta.name}</p>
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
                        <section className="sapphire-section border border-accent-emerald/25">
                          <AuroraField className="-left-60 -top-60 h-[520px] w-[520px]" variant="emerald" intensity="bold" />
                          <AuroraField className="right-[-12rem] bottom-[-8rem] h-[500px] w-[500px]" variant="amber" />
                          <div className="relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
                            <div className="space-y-4">
                              <p className="text-xs uppercase tracking-[0.35em] text-accent-emerald/80">PnL Observatory</p>
                              <h2 className="text-3xl font-bold text-brand-ice">Momentum Performance Console</h2>
                              <p className="text-sm leading-relaxed text-brand-muted">
                                Follow the rolling dialogue between balance trajectory, fills, and realised PnL. Strategies publish their thesis into the MCP log before every trade—this console shows how conviction translates into performance.
                              </p>
                              <div className="flex flex-wrap items-center gap-3">
                                <span className="sapphire-chip text-brand-midnight bg-gradient-to-r from-accent-sapphire/90 to-accent-emerald/80">
                                  {performanceInsights.totalTrades} Trades Observed
                                </span>
                                <span className="sapphire-chip text-brand-midnight bg-gradient-to-r from-accent-emerald/90 to-accent-teal/80">
                                  {performanceInsights.sentiment}
                                </span>
                              </div>
                            </div>
                            <div className="grid gap-4 text-sm text-brand-ice sm:grid-cols-2">
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Win Rate</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{performanceInsights.winRate.toFixed(1)}%</p>
                                <p className="mt-1 text-xs text-brand-muted">Across recent trade set</p>
                              </div>
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Average Notional</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{formatCurrency(performanceInsights.averageNotional)}</p>
                                <p className="mt-1 text-xs text-brand-muted">Per executed trade</p>
                              </div>
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Total Notional</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{formatCurrency(performanceInsights.totalNotional)}</p>
                                <p className="mt-1 text-xs text-brand-muted">Cumulative deployment</p>
                              </div>
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Last Trade</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">
                                  {performanceInsights.lastTrade
                                    ? new Date(performanceInsights.lastTrade).toLocaleString()
                                    : 'Awaiting Fill'}
                                </p>
                                <p className="mt-1 text-xs text-brand-muted">Local environment time</p>
                              </div>
                            </div>
                          </div>
                        </section>

                        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
                          <div className="sapphire-panel p-6">
                            <div className="flex items-center justify-between">
                              <div>
                                <p className="text-xs uppercase tracking-[0.3em] text-brand-muted/80">Balance Trajectory</p>
                                <h3 className="mt-2 text-lg font-semibold text-brand-ice">Capital vs Guiding Price</h3>
                              </div>
                            </div>
                            <div className="mt-4">
                              <PortfolioPerformance balanceSeries={performanceSeries.balance} priceSeries={performanceSeries.price} />
                            </div>
                          </div>
                          <div className="sapphire-panel p-6">
                            <Suspense fallback={<SectionSkeleton title="Trade Trends" className="h-72" />}>
                              <PerformanceTrends trades={dashboardData?.recent_trades || []} />
                            </Suspense>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 gap-6">
                          <div className="sapphire-panel p-6">
                            <RiskMetrics portfolio={dashboardData?.portfolio} />
                          </div>
                        </div>

                        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                          <div className="sapphire-panel p-6">
                            <Suspense fallback={<SectionSkeleton title="Model Performance" className="h-[28rem]" />}>
                              <ModelPerformance models={dashboardData?.model_performance ?? []} />
                            </Suspense>
                          </div>
                          <div className="sapphire-panel p-6">
                            <Suspense fallback={<SectionSkeleton title="Model Reasoning" className="h-[28rem]" />}>
                              <ModelReasoning reasoning={dashboardData?.model_reasoning ?? []} />
                            </Suspense>
                          </div>
                        </div>
                      </div>
                    )}

                    {activeTab === 'community' && (
                      <div className="space-y-6">
                        <section className="sapphire-section border border-accent-sapphire/35">
                          <AuroraField className="-left-64 -top-48 h-[520px] w-[520px]" variant="sapphire" intensity="bold" />
                          <AuroraField className="right-[-12rem] bottom-[-12rem] h-[560px] w-[560px]" variant="emerald" intensity="soft" />
                          <div className="relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
                            <div className="space-y-5">
                              <p className="text-xs uppercase tracking-[0.35em] text-accent-sapphire/80">Collective Intelligence</p>
                              <h2 className="text-3xl font-bold text-brand-ice">Sapphire Community Command</h2>
                              <p className="text-sm leading-relaxed text-brand-muted">
                                Every vote, comment, and daily check-in fuels our agent swarm. Insights are privacy-preserving and routed through throttled signals so bots can reference the crowd without overfitting. Follow <a href="https://twitter.com/rari_sui" target="_blank" rel="noreferrer" className="text-accent-sapphire hover:underline">@rari_sui</a> for the behind-the-scenes build.
                              </p>
                              <div className="grid gap-4 sm:grid-cols-2">
                                <div className="sapphire-panel p-5">
                                  <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Total Votes</p>
                                  <p className="mt-2 text-2xl font-semibold text-brand-ice">{communityInsights.totalVotes}</p>
                                  <p className="mt-1 text-xs text-brand-muted">Bullish {communityInsights.bullishRatio}% · Bearish {communityInsights.bearishRatio}%</p>
                                </div>
                                <div className="sapphire-panel p-5">
                                  <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Community Feedback</p>
                                  <p className="mt-2 text-2xl font-semibold text-brand-ice">{communityInsights.totalComments}</p>
                                  <p className="mt-1 text-xs text-brand-muted">Signal briefs captured for the agents</p>
                                </div>
                                <div className="sapphire-panel p-5">
                                  <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Top Contributor</p>
                                  <p className="mt-2 text-2xl font-semibold text-brand-ice">{topContributor?.displayName ?? '—'}</p>
                                  <p className="mt-1 text-xs text-brand-muted">{topContributor ? `${topContributorPoints.toLocaleString()} pts earned` : 'Join in to claim the leaderboard'}</p>
                                </div>
                                <div className="sapphire-panel p-5">
                                  <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Collective Points</p>
                                  <p className="mt-2 text-2xl font-semibold text-brand-ice">{communityInsights.totalPoints.toLocaleString()}</p>
                                  <p className="mt-1 text-xs text-brand-muted">Accrued via check-ins, comments, and sentiment votes</p>
                                </div>
                              </div>
                            </div>
                            <div>
                              <CommunityLeaderboard entries={leaderboardEntries} loading={leaderboardLoading} />
                            </div>
                          </div>
                        </section>

                        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                          <div className="sapphire-panel p-6">
                            <CrowdSentimentWidget
                              totalVotes={crowdSentiment.totalVotes}
                              bullishVotes={crowdSentiment.bullishVotes}
                              bearishVotes={crowdSentiment.bearishVotes}
                              hasVoted={crowdSentiment.hasVoted}
                              onVote={handleCrowdVote}
                              onAuthenticate={handleAuthenticate}
                              isAuthenticated={Boolean(user)}
                              onReset={realtimeCommunity ? undefined : resetCrowd}
                              loading={sentimentLoading}
                            />
                          </div>
                          <div className="sapphire-panel p-6">
                            <p className="text-xs uppercase tracking-[0.3em] text-brand-muted">Community Pulse</p>
                            <h3 className="mt-2 text-xl font-semibold text-brand-ice">How the crowd influences the desk</h3>
                            <p className="mt-3 text-sm text-brand-muted">
                              We credit daily check-ins with points, capture ticker-tagged insights (ex: <code>$SOL</code>), and expose anonymized aggregates to the trading agents. Bots treat these signals as optional context—never primary execution drivers—so sparse data never overrides disciplined momentum strategies.
                            </p>
                            <ul className="mt-4 space-y-2 text-sm text-brand-muted/90">
                              <li>• Daily attendance unlocks micropayment rewards when x402 launches.</li>
                              <li>• Hidden-positions mode keeps PnL private while still surfacing agent intent.</li>
                              <li>• Privacy coin routing is on the roadmap so shielded communities can participate.</li>
                            </ul>
                          </div>
                        </div>

                        <CommunityFeedback
                          comments={communityComments}
                          onSubmit={handleCommentSubmit}
                          user={user}
                          loading={authLoading || commentsLoading}
                          onSignOut={handleSignOut}
                          authEnabled={authEnabled}
                          authError={authError}
                          onSocialSignIn={handleSocialSignIn}
                          onEmailSignIn={handleEmailSignIn}
                          onEmailSignUp={handleEmailSignUp}
                          commentSubmitting={commentSubmitting}
                        />
                      </div>
                    )}

                    {activeTab === 'council' && (
                      <div className="space-y-6">
                        <Suspense fallback={<SectionSkeleton title="MCP Council" className="h-[24rem]" />}>
                          <MCPCouncil messages={mcpMessages ?? []} status={mcpStatus ?? connectionStatus} />
                        </Suspense>
                      </div>
                    )}

                    {activeTab === 'activity' && (
                      <div className="space-y-6">
                        <section className="sapphire-section border border-warning-amber/35">
                          <AuroraField className="-left-48 -top-52 h-[480px] w-[480px]" variant="amber" intensity="bold" />
                          <AuroraField className="right-[-10rem] bottom-[-12rem] h-[500px] w-[500px]" variant="sapphire" />
                          <div className="relative grid gap-8 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
                            <div className="space-y-4">
                              <p className="text-xs uppercase tracking-[0.35em] text-warning-amber">Mission Feed</p>
                              <h2 className="text-3xl font-bold text-brand-ice">Command & Control Stream</h2>
                              <p className="text-sm leading-relaxed text-brand-muted">
                                Sapphire logs every orchestration event—from MCP critiques to orchestrator overrides—in an auditable lab journal. Filter for warnings, replay experiments, and trace causality without leaving the console.
                              </p>
                              <div className="flex flex-wrap items-center gap-3">
                                <span className="sapphire-chip text-brand-midnight bg-gradient-to-r from-warning-amber/90 to-accent-aurora/80">
                                  {activitySummary.total} Entries Tracked
                                </span>
                                {activitySummary.lastEntry && (
                                  <span className="sapphire-chip text-brand-midnight bg-gradient-to-r from-accent-aurora/90 to-warning-amber/80">
                                    Last update {new Date(activitySummary.lastEntry.timestamp).toLocaleTimeString()}
                                  </span>
                                )}
                              </div>
                            </div>
                            <div className="grid gap-4 text-sm text-brand-ice sm:grid-cols-2">
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Success Signals</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{activitySummary.counts.success}</p>
                                <p className="mt-1 text-xs text-brand-muted">Orders landed smoothly</p>
                              </div>
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Warnings</p>
                                <p className="mt-2 text-2xl font-semibold text-warning-amber">{activitySummary.counts.warning}</p>
                                <p className="mt-1 text-xs text-brand-muted">Pre-emptive flags</p>
                              </div>
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Errors</p>
                                <p className="mt-2 text-2xl font-semibold text-error">{activitySummary.counts.error}</p>
                                <p className="mt-1 text-xs text-brand-muted">Needs immediate review</p>
                              </div>
                              <div className="sapphire-panel p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Informational</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{activitySummary.counts.info}</p>
                                <p className="mt-1 text-xs text-brand-muted">Contextual telemetry</p>
                              </div>
                            </div>
                          </div>
                        </section>

                        <div className="sapphire-panel p-6">
                          <Suspense fallback={<SectionSkeleton title="Activity Log" className="h-[28rem]" />}>
                            <ActivityLog logs={logs} />
                          </Suspense>
                        </div>

                        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                          <Suspense fallback={<SectionSkeleton title="MCP Council" className="h-[24rem]" />}>
                            <MCPCouncil messages={mcpMessages ?? []} status={mcpStatus ?? connectionStatus} />
                          </Suspense>
                          <div className="sapphire-panel p-6">
                            <p className="text-xs uppercase tracking-[0.3em] text-brand-muted">Community Highlights</p>
                            <h3 className="mt-2 text-lg font-semibold text-brand-ice">See the collective in action</h3>
                            <p className="mt-2 text-sm text-brand-muted">
                              Live sentiment, points, and feedback now live in the Community tab. Drop your vote and brief the agents with your sharpest takes.
                            </p>
                            <button
                              type="button"
                              onClick={() => setActiveTab('community')}
                              className="mt-4 inline-flex items-center gap-2 rounded-full bg-accent-sapphire/80 px-4 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-brand-midnight transition hover:bg-accent-sapphire"
                            >
                              Open Community Hub →
                            </button>
                          </div>
                        </div>
                      </div>
                    )}

                    {activeTab === 'system' && (
                      <div className="space-y-6">
                        <section className="sapphire-section border border-primary-500/25">
                          <AuroraField className="-left-60 -top-60 h-[520px] w-[520px]" variant="sapphire" intensity="bold" />
                          <AuroraField className="right-[-12rem] bottom-[-10rem] h-[520px] w-[520px]" variant="emerald" />
                          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(96,165,250,0.18),_transparent_70%)]" />
                          <div className="relative grid gap-10 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
                            <div className="space-y-4">
                              <p className="text-xs uppercase tracking-[0.35em] text-security-shield/70">Reliability Core</p>
                              <h2 className="text-3xl font-bold text-white">Platform Resilience Console</h2>
                              <p className="text-sm leading-relaxed text-brand-muted">
                                Snap the infrastructure healthline: orchestrator governance, trader loops, cache layer, and MCP connectivity. Everything routes through the load-balanced perimeter with security-first defaults.
                              </p>
                              <div className="flex flex-wrap items-center gap-3">
                                <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs uppercase tracking-[0.28em] text-brand-muted">
                                  {connectionStatus === 'connected' ? 'Live MCP uplink' : 'MCP reconnecting'}
                                </span>
                                <span className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] ${cacheConnected ? 'bg-accent-emerald/20 text-accent-emerald' : 'bg-error/20 text-error'}`}>
                                  Cache {cacheConnected ? 'Synchronized' : 'Offline'}
                                </span>
                              </div>
                            </div>
                            <div className="grid gap-4 text-sm text-brand-ice sm:grid-cols-2">
                              <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Orchestrator</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{systemSummary.orchestratorStatus}</p>
                                <p className="mt-1 text-xs text-brand-muted">Risk governor status</p>
                              </div>
                              <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Cloud Trader</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{systemSummary.traderStatus}</p>
                                <p className="mt-1 text-xs text-brand-muted">Execution loop heartbeat</p>
                              </div>
                              <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">Last Update</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">
                                  {systemSummary.timestamp ? new Date(systemSummary.timestamp).toLocaleString() : 'Awaiting telemetry'}
                                </p>
                                <p className="mt-1 text-xs text-brand-muted">System status timestamp</p>
                              </div>
                              <div className="rounded-3xl border border-white/10 bg-black/20 p-5">
                                <p className="text-[0.65rem] uppercase tracking-[0.28em] text-brand-muted">MCP Channel</p>
                                <p className="mt-2 text-2xl font-semibold text-brand-ice">{connectionStatus === 'connected' ? 'Synchronized' : 'Recovering'}</p>
                                <p className="mt-1 text-xs text-brand-muted">Mesh consensus transport</p>
                              </div>
                            </div>
                          </div>
                        </section>

                        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
                          <div className="sapphire-panel p-6">
                            <Suspense fallback={<SectionSkeleton title="System Status" className="h-[24rem]" />}>
                              <SystemStatus status={dashboardData?.system_status} />
                            </Suspense>
                          </div>
                          <div className="sapphire-panel p-6">
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
      </div>

      {/* Historical Performance Modal */}
      {selectedAgentForHistory && (
        <HistoricalPerformance
          agent={selectedAgentForHistory}
          onClose={() => setSelectedAgentForHistory(null)}
        />
      )}
    </>
  );
};

const App: React.FC = () => {
  const maintenanceMode = import.meta.env.VITE_MAINTENANCE_MODE === 'true';
  const [view, setView] = useState<'landing' | 'dashboard'>('landing');

  if (maintenanceMode) {
    return <MaintenancePage />;
  }

  if (view === 'landing') {
    return (
      <>
        <LandingPage onEnterApp={() => setView('dashboard')} />
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

  return <Dashboard onBackToHome={() => setView('landing')} />;
};

export default App;

