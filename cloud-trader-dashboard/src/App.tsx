import React, { useState, useEffect } from 'react';
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

interface DashboardData {
  portfolio: any;
  positions: any[];
  recent_trades: any[];
  model_performance: any[];
  model_reasoning: any[];
  system_status: any;
  targets: any;
}

const App: React.FC = () => {
  const { health, loading, error, logs, startTrader, stopTrader, refresh } = useTraderService();
  const [isMobile, setIsMobile] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'models' | 'positions' | 'performance' | 'system'>('overview');
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
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
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
    } finally {
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
  ] as const;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-gradient-to-r from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">CT</span>
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-900">Cloud Trader</h1>
                <p className="text-sm text-slate-500">Autonomous Trading System</p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <div className="text-sm text-slate-600">Total P&L</div>
                <div className={`text-lg font-bold ${dashboardData?.portfolio?.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  ${dashboardData?.portfolio?.total_pnl?.toFixed(2) || '0.00'}
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <div className={`w-2 h-2 rounded-full ${health?.running ? 'bg-green-500' : 'bg-red-500'}`}></div>
                <span className="text-sm font-medium text-slate-600">
                  {health?.running ? 'Live' : 'Stopped'}
                </span>
              </div>
              <NotificationCenter alerts={dashboardData?.targets?.alerts || []} />
              <button
                onClick={fetchDashboardData}
                className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors"
              >
                🔄 Refresh
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Error Banner */}
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Connection Error</h3>
                <p className="text-sm text-red-700 mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Mobile Tab Navigation */}
        {isMobile && (
          <div className="mb-6">
            <div className="flex space-x-1 bg-slate-100 p-1 rounded-lg">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex-1 flex items-center justify-center px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                    activeTab === tab.id
                      ? 'bg-white text-slate-900 shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <span className="mr-1">{tab.icon}</span>
                  <span className="hidden sm:inline">{tab.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Tab Content */}
        {dashboardLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <span className="ml-3 text-slate-600">Loading dashboard data...</span>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Overview Tab */}
            {activeTab === 'overview' && (
              <>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <StatusCard health={health} loading={loading} />
                  <PortfolioCard portfolio={dashboardData?.portfolio} />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <PerformanceChart data={dashboardData?.recent_trades || []} />
                  <RiskMetrics positions={dashboardData?.positions || []} />
                </div>
                <TargetsAndAlerts targets={dashboardData?.targets} />
                <ActivityLog logs={logs} />
              </>
            )}

            {/* Models Tab */}
            {activeTab === 'models' && (
              <div className="space-y-6">
                <ModelPerformance models={dashboardData?.model_performance || []} />
                <ModelReasoning reasoning={dashboardData?.model_reasoning || []} />
              </div>
            )}

            {/* Positions Tab */}
            {activeTab === 'positions' && (
              <div className="space-y-6">
                <LivePositions positions={dashboardData?.positions || []} />
              </div>
            )}

            {/* Performance Tab */}
            {activeTab === 'performance' && (
              <div className="space-y-6">
                <PerformanceTrends trades={dashboardData?.recent_trades || []} />
                <PerformanceChart data={dashboardData?.recent_trades || []} detailed />
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <RiskMetrics positions={dashboardData?.positions || []} />
                  <TargetsAndAlerts targets={dashboardData?.targets} />
                </div>
              </div>
            )}

            {/* System Tab */}
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
      </div>
    </div>
  );
};

export default App;

