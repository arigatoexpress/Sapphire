import { HealthResponse, DashboardResponse } from '../api/client';
interface LogEntry {
    timestamp: string;
    message: string;
    type: 'info' | 'success' | 'error' | 'warning';
}
interface MCPMessage {
    id: string;
    type: string;
    sender: string;
    timestamp: string;
    content: string;
    context?: string;
}
export declare const useTraderService: () => {
    health: HealthResponse | null;
    dashboardData: DashboardResponse | null;
    loading: boolean;
    error: string | null;
    logs: LogEntry[];
    connectionStatus: "connecting" | "connected" | "disconnected";
    mcpMessages: MCPMessage[];
    mcpStatus: "connecting" | "connected" | "disconnected";
    refresh: () => Promise<void>;
    addLog: (message: string, type?: LogEntry["type"]) => void;
};
export {};
