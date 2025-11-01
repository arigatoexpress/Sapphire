import React, { useState, useEffect, useMemo } from 'react';
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
  const { health, loading, error } = useTraderService();
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);

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
  }, []);

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <h1 className="text-2xl font-bold mb-4">Cloud Trader Dashboard</h1>

      {dashboardLoading ? (
        <p>Loading...</p>
      ) : error ? (
        <p className="text-red-500">Error: {error}</p>
      ) : (
        <div>
          <p>Dashboard loaded successfully!</p>
          <p>Balance: ${dashboardData?.portfolio?.balance ?? 0}</p>
          <p>Health: {health?.running ? 'Running' : 'Stopped'}</p>
        </div>
      )}
    </div>
  );
};

export default App;

