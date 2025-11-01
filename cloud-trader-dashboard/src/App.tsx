import React, { useState, useEffect, useMemo } from 'react';
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
import { fetchDashboard, DashboardResponse, DashboardPosition } from './api/client';

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);

const App: React.FC = () => {
  const { health, loading, error, logs, startTrader, stopTrader, refresh } = useTraderService();
  const [activeTab, setActiveTab] = useState<'overview' | 'models' | 'positions' | 'performance' | 'system'>('overview');
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
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
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
      toast.error('Failed to update dashboard data', {
        duration: 4000,
        style: {
          background: 'rgba(239, 68, 68, 0.95)',
          color: '#fee2e2',
          border: '1px solid rgba(239, 68, 68, 0.3)',
        },
      });
    } finally {
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
        alerts: [] as string[],
        positions: [] as DashboardPosition[],
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
  ] as const;

  const sidebarTabs = tabs.map((tab) => ({ id: tab.id, label: tab.label, icon: tab.icon }));

  return (
    <div className="min-h-screen bg-surface-50 text-slate-200">
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: 'rgba(15, 23, 42, 0.95)',
            color: '#cbd5f5',
            border: '1px solid rgba(148, 163, 184, 0.3)',
            backdropFilter: 'blur(10px)',
          },
        }}
      />
      <div className="flex min-h-screen bg-gradient-to-br from-surface-100 via-surface-50 to-surface-50">
        <Sidebar
          tabs={sidebarTabs}
          activeTab={activeTab}
          onSelect={(id) => setActiveTab(id as typeof activeTab)}
          mobileMenuOpen={mobileMenuOpen}
          setMobileMenuOpen={setMobileMenuOpen}
        />

        <div className="flex flex-1 flex-col">
          <TopBar
            onRefresh={fetchDashboardData}
            lastUpdated={dashboardData?.system_status?.timestamp}
            healthRunning={health?.running}
            mobileMenuOpen={mobileMenuOpen}
            setMobileMenuOpen={setMobileMenuOpen}
          />

          <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-10">
            <div className="flex justify-end">
              <NotificationCenter alerts={derived.alerts} />
            </div>

            {error && (
              <div className="mb-6 rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-100">
                <p className="font-semibold">Connection Error</p>
                <p className="mt-1 text-red-200/80">{error}</p>
              </div>
            )}

            {dashboardLoading ? (
              <div className="space-y-8">
                {/* Skeleton loading state */}
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass">
                      <div className="animate-pulse">
                        <div className="h-3 bg-slate-600/40 rounded mb-2"></div>
                        <div className="h-8 bg-slate-600/40 rounded mb-4"></div>
                        <div className="h-3 bg-slate-600/40 rounded w-2/3"></div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
                  <div className="xl:col-span-2 relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass">
                    <div className="animate-pulse">
                      <div className="h-4 bg-slate-600/40 rounded mb-2 w-1/3"></div>
                      <div className="h-6 bg-slate-600/40 rounded mb-4 w-1/2"></div>
                      <div className="h-64 bg-slate-600/40 rounded"></div>
                    </div>
                  </div>
                  <div className="relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass">
                    <div className="animate-pulse">
                      <div className="h-4 bg-slate-600/40 rounded mb-2"></div>
                      <div className="space-y-3">
                        {[1, 2, 3].map((i) => (
                          <div key={i} className="h-3 bg-slate-600/40 rounded"></div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  {[1, 2].map((i) => (
                    <div key={i} className="relative overflow-hidden rounded-2xl border border-surface-200/40 bg-surface-100/60 p-6 shadow-glass">
                      <div className="animate-pulse">
                        <div className="h-4 bg-slate-600/40 rounded mb-2 w-1/3"></div>
                        <div className="h-6 bg-slate-600/40 rounded mb-4 w-1/2"></div>
                        <div className="space-y-3">
                          {[1, 2, 3, 4].map((j) => (
                            <div key={j} className="h-3 bg-slate-600/40 rounded"></div>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-8">
                {activeTab === 'overview' && (
                  <div className="space-y-6">
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                      <MetricCard
                        label="Account Balance"
                        value={formatCurrency(derived.balance)}
                        accent="emerald"
                        footer={<span>Exposure coverage ratio {(derived.exposure / (derived.balance || 1) * 100).toFixed(1)}%</span>}
                      />
                      <MetricCard
                        label="Gross Exposure"
                        value={formatCurrency(derived.exposure)}
                        accent="teal"
                        footer={<span>{derived.positions.length} instruments allocated</span>}
                      />
                      <MetricCard
                        label="AI Alerts"
                        value={derived.alerts.length}
                        accent="amber"
                        footer={<span>Powered by orchestrator health checks</span>}
                      />
                    </div>

                    <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
                      <div className="xl:col-span-2 rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass">
                        <div className="mb-4 flex items-center justify-between">
                          <div>
                            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Performance Lens</p>
                            <h3 className="mt-2 text-xl font-semibold text-white">Portfolio & Benchmark</h3>
                          </div>
                        </div>
                        <PortfolioPerformance balanceSeries={performanceSeries.balance} priceSeries={performanceSeries.price} />
                      </div>
                      <TargetsAndAlerts targets={dashboardData?.targets} />
                    </div>

                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                      <StatusCard health={health} loading={loading} />
                      <PortfolioCard portfolio={dashboardData?.portfolio} />
                    </div>

                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                      <RiskMetrics portfolio={dashboardData?.portfolio} />
                      <ActivityLog logs={logs} />
                    </div>
                  </div>
                )}

                {activeTab === 'models' && (
                  <div className="space-y-6">
                    <ModelPerformance models={dashboardData?.model_performance || []} />
                    <ModelReasoning reasoning={dashboardData?.model_reasoning || []} />
                  </div>
                )}

                {activeTab === 'positions' && (
                  <div className="space-y-6">
                    <LivePositions positions={derived.positions} />
                  </div>
                )}

                {activeTab === 'performance' && (
                  <div className="space-y-6">
                    <div className="rounded-2xl border border-surface-200/40 bg-surface-100/80 p-6 shadow-glass">
                      <h3 className="text-lg font-semibold text-white">Balance Trajectory</h3>
                      <p className="mt-1 text-sm text-slate-400">Overlay of account balance vs indicative price ladder.</p>
                      <div className="mt-4">
                        <PortfolioPerformance balanceSeries={performanceSeries.balance} priceSeries={performanceSeries.price} />
                      </div>
                    </div>
                    <PerformanceTrends trades={dashboardData?.recent_trades || []} />
                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                      <RiskMetrics portfolio={dashboardData?.portfolio} />
                      <TargetsAndAlerts targets={dashboardData?.targets} />
                    </div>
                  </div>
                )}

                {activeTab === 'system' && (
                  <div className="space-y-6">
                    <SystemStatus status={dashboardData?.system_status} />
                    <ControlsPanel
                      health={health}
                      loading={loading}
                      onStart={startTrader}
                      onStop={stopTrader}
                      onRefresh={refresh}
                    />
                  </div>
                )}
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
};

export default App;

