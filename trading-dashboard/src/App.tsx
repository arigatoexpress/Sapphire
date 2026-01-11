
import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { MasterLayout } from './layouts/MasterLayout';
import ProtectedRoute from './components/ProtectedRoute';

// Core Pages
import { UnifiedDashboard } from './pages/UnifiedDashboard';
import { AgentLab } from './pages/AgentLab';
import AgentPerformance from './pages/AgentPerformance';
import { PortfolioPro } from './pages/PortfolioPro';
import { About } from './pages/About';
import Leaderboard from './pages/Leaderboard';
import Login from './pages/Login';
import { TerminalPro } from './pages/TerminalPro';
import MonadMIT from './pages/MonadMIT';
import SystemMetrics from './pages/SystemMetrics';
import JupiterSwap from './pages/JupiterSwap';
import FiredancerDashboard from './pages/FiredancerDashboard';
import { LiveMonitor } from './pages/LiveMonitor';
import PlatformMetricsPage from './pages/PlatformMetrics';


import { SolanaWalletProvider } from './contexts/SolanaWalletContext'; // Import Wallet Provider
import ErrorBoundary from './components/ErrorBoundary';

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <Routes>
        {/* Public Routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/hud" element={<FiredancerDashboard />} />

        {/* Protected Routes */}
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <SolanaWalletProvider>
                <Routes>
                  {/* Main Dashboard (Firedancer Style) - Standalone Layout */}
                  <Route path="/" element={<FiredancerDashboard />} />

                  {/* Legacy Routes - Wrapped in MasterLayout */}
                  <Route path="/*" element={
                    <MasterLayout>
                      <Routes>
                        {/* Legacy Dashboard */}
                        <Route path="/legacy" element={<UnifiedDashboard />} />

                        {/* Terminal Pro */}
                        <Route path="/terminal" element={<TerminalPro />} />

                        {/* Monad MIT */}
                        <Route path="/mit" element={<MonadMIT />} />

                        {/* System Observability */}
                        <Route path="/system" element={<SystemMetrics />} />
                        <Route path="/platforms" element={<PlatformMetricsPage />} />
                        <Route path="/monitor" element={<LiveMonitor />} />

                        {/* Jupiter Swap */}
                        <Route path="/jupiter" element={<JupiterSwap />} />

                        {/* Agents Page */}
                        <Route path="/agents" element={<AgentLab />} />

                        {/* Agent Performance Dashboard */}
                        <Route path="/agent-performance" element={<AgentPerformance />} />

                        {/* Portfolio Page */}
                        <Route path="/portfolio" element={<PortfolioPro />} />

                        {/* About Page */}
                        <Route path="/about" element={<About />} />

                        {/* Leaderboard Page */}
                        <Route path="/leaderboard" element={<Leaderboard />} />

                        {/* Fallback */}
                        <Route path="*" element={<UnifiedDashboard />} />
                      </Routes>
                    </MasterLayout>
                  } />
                </Routes>
              </SolanaWalletProvider>
            </ProtectedRoute>
          }
        />
      </Routes>
    </ErrorBoundary>
  );
};

export default App;
