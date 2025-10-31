export interface LogEntry {
  timestamp: string;
  message: string;
}

interface ActivityLogProps {
  logs: LogEntry[];
}

const ActivityLog: React.FC<ActivityLogProps> = ({ logs }) => {
  return (
    <div className="bg-white border border-gray-200 rounded-md p-4">
      <h2 className="text-lg font-semibold mb-2">Activity Log</h2>
      <ul className="space-y-1 max-h-60 overflow-y-auto">
        {logs.map((log, index) => (
          <li key={`${log.timestamp}-${index}`} className="text-sm text-neutral">
            <span className="font-mono">{log.timestamp}</span>: {log.message}
          </li>
        ))}
        {!logs.length && <li className="text-sm text-neutral">No activity yet.</li>}
      </ul>
    </div>
  );
};

export default ActivityLog;

