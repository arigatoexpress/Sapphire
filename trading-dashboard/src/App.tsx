import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { useDashboardWebSocket } from './hooks/useWebSocket';

// Import pages
import { DualityDashboard } from './pages/DualityDashboard';
import { Agents } from './pages/Agents';
import { Analytics } from './pages/Analytics';
import { Portfolio } from './pages/Portfolio';
import { MissionControl } from './pages/MissionControl';
import { SystemArchitecture } from './pages/SystemArchitecture';
import { CommandControl } from './pages/CommandControl';
import { About } from './pages/About';

function App() {
  const { data, connected } = useDashboardWebSocket();

  // Use real data if available, otherwise empty (loading state handled in components)
  const bots = data?.agents || [];
  const messages = data?.messages || [];
  const trades = data?.recentTrades || [];
  const openPositions = data?.open_positions || [];

  const totalAllocation = bots.reduce((acc: number, bot: any) => acc + (bot.allocation || 0), 0);
  const totalPnl = bots.reduce((acc: number, bot: any) => acc + (bot.pnl || 0), 0);

  // Total Value = Initial Allocation + PnL
  const totalValue = totalAllocation + totalPnl;

  // PnL Percent based on actual total allocation
  const pnlPercent = totalAllocation > 0 ? (totalPnl / totalAllocation) * 100 : 0;

  return (
    <AppShell connectionStatus={connected ? 'connected' : 'disconnected'}>
      <Routes>
        <Route
          path="/"
          element={<Navigate to="/dashboard" replace />}
        />
        <Route
          path="/dashboard"
          element={
            <DualityDashboard
              bots={bots}
              messages={messages}
              trades={trades}
              openPositions={openPositions}
              totalValue={totalValue}
              totalPnl={totalPnl}
              pnlPercent={pnlPercent}
            />
          }
        />
        <Route
          path="/agents"
          element={
            <Agents
              bots={bots}
              messages={messages}
            />
          }
        />
        <Route
          path="/analytics"
          element={
            <Analytics
              bots={bots}
              trades={trades}
            />
          }
        />
        <Route
          path="/portfolio"
          element={
            <Portfolio
              totalValue={totalValue}
              totalPnl={totalPnl}
              pnlPercent={pnlPercent}
              trades={trades}
              openPositions={openPositions}
            />
          }
        />
        <Route
          path="/mission-control"
          element={<MissionControl />}
        />
        <Route
          path="/architecture"
          element={<SystemArchitecture />}
        />
        <Route
          path="/command"
          element={<CommandControl />}
        />
        <Route
          path="/about"
          element={<About />}
        />
      </Routes>
    </AppShell>
  );
}

export default App;
