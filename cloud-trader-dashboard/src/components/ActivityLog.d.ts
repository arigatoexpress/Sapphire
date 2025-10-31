export interface LogEntry {
    timestamp: string;
    message: string;
    type: 'info' | 'success' | 'error' | 'warning';
}
interface ActivityLogProps {
    logs: LogEntry[];
}
declare const ActivityLog: React.FC<ActivityLogProps>;
export default ActivityLog;
