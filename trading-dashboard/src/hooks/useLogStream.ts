import { useState, useEffect, useRef } from 'react';
import { getWebSocketUrl } from '../utils/apiConfig';

interface LogEntry {
    id: string;
    timestamp: string;
    level: string;
    module: string;
    message: string;
    metadata?: any;
}

interface UseLogStreamReturn {
    logs: LogEntry[];
    connected: boolean;
    error: string | null;
    clearLogs: () => void;
    paused: boolean;
    setPaused: (paused: boolean) => void;
}

export const useLogStream = (token?: string | null): UseLogStreamReturn => {
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [connected, setConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [paused, setPaused] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    // Buffer for incoming logs to reduce re-renders
    const logBufferRef = useRef<LogEntry[]>([]);

    useEffect(() => {
        // Flush buffer every 100ms
        const interval = setInterval(() => {
            if (logBufferRef.current.length > 0 && !paused) {
                setLogs(prev => {
                    const newLogs = [...prev, ...logBufferRef.current].slice(-1000); // Keep last 1000
                    logBufferRef.current = [];
                    return newLogs;
                });
            }
        }, 100);
        return () => clearInterval(interval);
    }, [paused]);

    const connect = () => {
        if (!token) return;

        try {
            const baseUrl = getWebSocketUrl().replace('/dashboard', '/logs').replace('/api/ws', '/ws');
            // Normalize URL construction
            const wsUrl = baseUrl.includes('/logs')
                ? `${baseUrl}?token=${token}`
                : `${baseUrl}/logs?token=${token}`; // Heuristic fix if url is base

            // Better url construction
            const configUrl = getWebSocketUrl();
            // If configUrl ends with /dashboard, strip it
            const rootWsUrl = configUrl.replace(/\/ws\/dashboard$/, '').replace(/\/api\/ws\/dashboard$/, '');
            const finalUrl = `${rootWsUrl}/ws/logs?token=${token}`;

            console.log(`🔌 Connecting to Log Stream: ${finalUrl}`);
            const ws = new WebSocket(finalUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                console.log('✅ Log Stream Connected');
                setConnected(true);
                setError(null);
            };

            ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    if (message.type === 'log') {
                        logBufferRef.current.push(message.data);
                    }
                } catch (e) {
                    console.error('Failed to parse log message:', e);
                }
            };

            ws.onclose = () => {
                console.log('🔴 Log Stream Disconnected');
                setConnected(false);
                // Reconnect
                reconnectTimeoutRef.current = setTimeout(connect, 3000);
            };

            ws.onerror = (e) => {
                console.error('Log Stream Error:', e);
                setError('Connection error');
            };

        } catch (e) {
            console.error('Failed to create Log Stream connection:', e);
            setError('Failed to connect');
        }
    };

    useEffect(() => {
        connect();
        return () => {
            if (wsRef.current) wsRef.current.close();
            if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        };
    }, [token]);

    return {
        logs,
        connected,
        error,
        clearLogs: () => setLogs([]),
        paused,
        setPaused
    };
};
