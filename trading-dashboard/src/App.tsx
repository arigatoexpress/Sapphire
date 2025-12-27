
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
import { MonadMIT } from './pages/MonadMIT';
import SystemMetrics from './pages/SystemMetrics';
import JupiterSwap from './pages/JupiterSwap';
import FiredancerDashboard from './pages/FiredancerDashboard';

import { SolanaWalletProvider } from './contexts/SolanaWalletContext'; // Import Wallet Provider
import ErrorBoundary from './components/ErrorBoundary';
import { AuthProvider } from './contexts/AuthContext';
import { TradingProvider } from './contexts/TradingContext';

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <TradingProvider>
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
                    <MasterLayout>
                      <Routes>
                        {/* Main Dashboard */}
                        <Route path="/" element={<UnifiedDashboard />} />

                        {/* Terminal Pro (New Social Dashboard) */}
                        <Route path="/terminal" element={<TerminalPro />} />

                        {/* Monad MIT (Symphony Integration) */}
                        <Route path="/mit" element={<MonadMIT />} />

                        {/* System Observability */}
                        <Route path="/system" element={<SystemMetrics />} />

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
                  </SolanaWalletProvider>
                </ProtectedRoute>
              }
            />
          </Routes>
        </TradingProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
};

export default App;
