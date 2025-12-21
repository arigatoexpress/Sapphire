import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { MasterLayout } from './layouts/MasterLayout';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';

// Core Pages
import { UnifiedDashboard } from './pages/UnifiedDashboard';
import { AgentLab } from './pages/AgentLab';
import { PortfolioPro } from './pages/PortfolioPro';
import { About } from './pages/About';
import Leaderboard from './pages/Leaderboard';
import Login from './pages/Login';
import { TerminalPro } from './pages/TerminalPro';
import { MonadMIT } from './pages/MonadMIT';

import ErrorBoundary from './components/ErrorBoundary';

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <Routes>
          {/* Public Route */}
          <Route path="/login" element={<Login />} />

          {/* Protected Routes */}
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <MasterLayout>
                  <Routes>
                    {/* Main Dashboard */}
                    <Route path="/" element={<UnifiedDashboard />} />

                    {/* Terminal Pro (New Social Dashboard) */}
                    <Route path="/terminal" element={<TerminalPro />} />

                    {/* Monad MIT (Symphony Integration) */}
                    <Route path="/mit" element={<MonadMIT />} />

                    {/* Agents Page */}
                    <Route path="/agents" element={<AgentLab />} />

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
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </ErrorBoundary>
  );
};

export default App;
