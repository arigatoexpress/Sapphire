import { HealthResponse } from '../api/client';

interface StatusCardProps {
  health: HealthResponse | null;
  loading: boolean;
}

const StatusCard: React.FC<StatusCardProps> = ({ health, loading }) => {
  if (loading || !health) {
    return <div className="bg-gray-200 p-4 rounded-md text-center">Loading status...</div>;
  }

  const statusColor = health.running ? 'success' : 'error';

  return (
    <div className="bg-white border border-gray-200 rounded-md p-4 space-y-2">
      <div className="flex items-center">
        <h2 className="text-lg font-semibold">Status:</h2>
        <span className={`ml-2 text-${statusColor} font-bold`}>
          {health.running ? 'Running' : 'Stopped'}
        </span>
        {health.paper_trading && (
          <span className="ml-2 px-2 py-1 bg-warning text-white text-xs rounded-full">Paper Trading</span>
        )}
      </div>
      {health.last_error && <div className="text-error">Last Error: {health.last_error}</div>}
    </div>
  );
};

export default StatusCard;

