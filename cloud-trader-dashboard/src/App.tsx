import ControlsPanel from './components/ControlsPanel';
import ActivityLog from './components/ActivityLog';
import StatusCard from './components/StatusCard';
import { useTraderService } from './hooks/useTraderService';

const App: React.FC = () => {
  const { health, loading, error, logs, startTrader, stopTrader, refresh } = useTraderService();

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-4xl bg-white shadow-lg rounded-lg p-6 space-y-6">
        <header className="text-center">
          <h1 className="text-2xl font-bold text-primary">Cloud Trader Dashboard</h1>
        </header>
        {error && <div className="bg-error/10 p-4 rounded-md text-error">{error}</div>}
        <StatusCard health={health} loading={loading} />
        <ControlsPanel
          health={health}
          loading={loading}
          onStart={startTrader}
          onStop={stopTrader}
          onRefresh={refresh}
        />
        <ActivityLog logs={logs} />
      </div>
    </div>
  );
};

export default App;

