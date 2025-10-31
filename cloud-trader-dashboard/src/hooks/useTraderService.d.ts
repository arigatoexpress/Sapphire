import { HealthResponse } from '../api/client';
interface LogEntry {
    timestamp: string;
    message: string;
    type: 'info' | 'success' | 'error' | 'warning';
}
export declare const useTraderService: () => {
    health: HealthResponse | null;
    loading: boolean;
    error: string | null;
    logs: LogEntry[];
    connectionStatus: "connecting" | "connected" | "disconnected";
    startTrader: () => Promise<void>;
    stopTrader: () => Promise<void>;
    refresh: () => Promise<void>;
    addLog: (message: string, type?: LogEntry["type"]) => void;
};
export {};
