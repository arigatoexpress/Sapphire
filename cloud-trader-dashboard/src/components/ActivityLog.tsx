export interface LogEntry {
  timestamp: string;
  message: string;
  type: 'info' | 'success' | 'error' | 'warning';
}

interface ActivityLogProps {
  logs: LogEntry[];
}

const getLogIcon = (type: LogEntry['type']) => {
  switch (type) {
    case 'success':
      return '✅';
    case 'error':
      return '❌';
    case 'warning':
      return '⚠️';
    default:
      return 'ℹ️';
  }
};

const getLogColor = (type: LogEntry['type']) => {
  switch (type) {
    case 'success':
      return 'text-green-700';
    case 'error':
      return 'text-red-700';
    case 'warning':
      return 'text-yellow-700';
    default:
      return 'text-slate-700';
  }
};

const ActivityLog: React.FC<ActivityLogProps> = ({ logs }) => {
  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      });
    } catch {
      return timestamp;
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-slate-900">Activity Log</h3>
        <span className="text-sm text-slate-500">{logs.length} entries</span>
      </div>

      <div className="space-y-2 max-h-96 overflow-y-auto">
        {logs.length > 0 ? (
          logs.map((log, index) => (
            <div
              key={`${log.timestamp}-${index}`}
              className={`flex items-start space-x-3 p-3 rounded-lg border ${
                log.type === 'error' ? 'bg-red-50 border-red-200' :
                log.type === 'warning' ? 'bg-yellow-50 border-yellow-200' :
                log.type === 'success' ? 'bg-green-50 border-green-200' :
                'bg-slate-50 border-slate-200'
              }`}
            >
              <span className="text-lg flex-shrink-0">{getLogIcon(log.type)}</span>
              <div className="flex-1 min-w-0">
                <p className={`text-sm ${getLogColor(log.type)} break-words`}>
                  {log.message}
                </p>
                <p className="text-xs text-slate-500 mt-1 font-mono">
                  {formatTimestamp(log.timestamp)}
                </p>
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-8 text-slate-500">
            <svg className="w-12 h-12 mx-auto mb-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-sm">No activity yet</p>
            <p className="text-xs mt-1">System events will appear here</p>
          </div>
        )}
      </div>

      {/* Auto-scroll to bottom when new logs arrive */}
      <div ref={(el) => {
        if (el && logs.length > 0) {
          el.scrollIntoView({ behavior: 'smooth', block: 'end' });
        }
      }} />
    </div>
  );
};

export default ActivityLog;

