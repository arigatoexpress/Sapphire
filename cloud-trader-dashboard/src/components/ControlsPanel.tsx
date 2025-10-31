import { HealthResponse } from '../api/client';

interface ControlsPanelProps {
  health: HealthResponse | null;
  loading: boolean;
  onStart: () => void;
  onStop: () => void;
  onRefresh: () => void;
}

const ControlsPanel: React.FC<ControlsPanelProps> = ({ health, loading, onStart, onStop, onRefresh }) => {
  const isRunning = health?.running ?? false;
  const disabled = loading;

  return (
    <div className="flex justify-center gap-4 flex-wrap">
      <button
        onClick={onStart}
        disabled={disabled || isRunning}
        className="px-4 py-2 bg-success text-white rounded-md disabled:opacity-50"
        aria-label="Start Trader"
      >
        Start
      </button>
      <button
        onClick={onStop}
        disabled={disabled || !isRunning}
        className="px-4 py-2 bg-error text-white rounded-md disabled:opacity-50"
        aria-label="Stop Trader"
      >
        Stop
      </button>
      <button
        onClick={onRefresh}
        disabled={loading}
        className="px-4 py-2 bg-primary text-white rounded-md disabled:opacity-50"
        aria-label="Refresh Status"
      >
        Refresh
      </button>
    </div>
  );
};

export default ControlsPanel;

