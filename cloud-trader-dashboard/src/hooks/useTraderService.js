import React, { useEffect, useState, useCallback, useRef } from 'react';
import { fetchDashboard } from '../api/client';
export const useTraderService = () => {
    const [health, setHealth] = useState(null);
    const [dashboardData, setDashboardData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [logs, setLogs] = useState([]);
    const [pollInterval, setPollInterval] = useState(15000); // Default 15s - faster updates for better UX
    const [connectionStatus, setConnectionStatus] = useState('connecting');
    const [mcpMessages, setMcpMessages] = useState([]);
    const mcpBaseUrl = import.meta.env.VITE_MCP_URL;
    const [mcpStatus, setMcpStatus] = useState(mcpBaseUrl ? 'connecting' : 'disconnected');
    const [mcpSocket, setMcpSocket] = useState(null);
    const reconnectRef = useRef(null);
    const addLog = useCallback((message, type = 'info') => {
        const timestamp = new Date().toISOString();
        setLogs((prev) => [{
                timestamp,
                message,
                type
            }, ...prev.slice(0, 99)]); // Keep last 100 logs
    }, []);
    const refresh = useCallback(async () => {
        const wasLoading = loading;
        if (!wasLoading)
            setLoading(true);
        setError(null);
        try {
            // Fetch dashboard data - this is our single source of truth
            const data = await fetchDashboard();
            // Update dashboard data
            setDashboardData(data);
            // Extract health info from dashboard data
            const healthData = {
                running: data.system_status.services.cloud_trader === 'running',
                paper_trading: data.portfolio.source === 'local', // Assume paper trading if using local portfolio
                last_error: null
            };
            setHealth(healthData);
            setConnectionStatus('connected');
            setError(null);
            // Only log health checks occasionally to avoid spam
            if (wasLoading || !health || health.running !== healthData.running) {
                addLog(`System ${healthData.running ? 'running' : 'stopped'} ${healthData.paper_trading ? '(Paper Trading)' : '(Live Trading)'}`, 'info');
            }
        }
        catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error fetching health';
            setError(errorMessage);
            setConnectionStatus('disconnected');
            addLog(`Connection error: ${errorMessage}`, 'error');
        }
        finally {
            setLoading(false);
        }
    }, [addLog]); // Only depend on addLog to prevent excessive re-renders
    // Use refs to avoid stale closures in polling
    const pollIntervalRef = React.useRef(pollInterval);
    const connectionStatusRef = React.useRef(connectionStatus);
    // Update refs when values change
    React.useEffect(() => {
        pollIntervalRef.current = pollInterval;
    }, [pollInterval]);
    React.useEffect(() => {
        connectionStatusRef.current = connectionStatus;
    }, [connectionStatus]);
    useEffect(() => {
        // Initial load
        refresh();
        // Set up polling with exponential backoff on errors
        let intervalId;
        let currentInterval = pollIntervalRef.current;
        const scheduleNextPoll = () => {
            intervalId = setTimeout(async () => {
                await refresh();
                // Adjust polling interval based on connection status
                if (connectionStatusRef.current === 'disconnected') {
                    currentInterval = Math.min(currentInterval * 1.5, 60000); // Max 60s on errors
                }
                else {
                    currentInterval = pollIntervalRef.current; // Reset to normal
                }
                scheduleNextPoll();
            }, currentInterval);
        };
        scheduleNextPoll();
        return () => {
            if (intervalId !== undefined)
                clearTimeout(intervalId);
        };
    }, [refresh]); // Only depend on refresh to prevent excessive re-runs
    const temporaryPoll = useCallback(() => {
        setPollInterval(2000);
        setTimeout(() => setPollInterval(10000), 15000); // Reset after 15 seconds
    }, []);
    // Connection status indicator
    useEffect(() => {
        if (connectionStatus === 'disconnected' && !error) {
            addLog('🔄 Attempting to reconnect...', 'warning');
        }
        else if (connectionStatus === 'connected' && error) {
            setConnectionStatus('disconnected');
        }
    }, [connectionStatus, error, addLog]);
    useEffect(() => {
        if (!mcpBaseUrl) {
            setMcpStatus('disconnected');
            return;
        }
        const controller = new AbortController();
        const connect = () => {
            try {
                const wsUrl = mcpBaseUrl.replace('http', 'ws');
                const socket = new WebSocket(wsUrl);
                setMcpStatus('connecting');
                socket.onopen = () => {
                    setMcpStatus('connected');
                    setMcpSocket(socket);
                };
                socket.onerror = () => {
                    setMcpStatus('disconnected');
                };
                socket.onclose = () => {
                    setMcpStatus('disconnected');
                    const timeoutId = setTimeout(() => {
                        if (!controller.signal.aborted) {
                            connect();
                        }
                    }, 3000);
                    reconnectRef.current = timeoutId;
                };
                socket.onmessage = (event) => {
                    try {
                        const payload = JSON.parse(event.data);
                        const message = payload.message;
                        if (!message)
                            return;
                        const entry = {
                            id: message.payload?.reference_id || crypto.randomUUID(),
                            type: message.message_type ?? 'unknown',
                            sender: message.sender_id ?? 'MCP',
                            timestamp: message.timestamp ?? new Date().toISOString(),
                            content: message.payload?.rationale || message.payload?.answer || message.payload?.notes || JSON.stringify(message.payload),
                            context: message.payload?.question || message.payload?.symbol,
                        };
                        setMcpMessages((prev) => [entry, ...prev].slice(0, 50));
                    }
                    catch (err) {
                        console.error('Failed to parse MCP message', err);
                    }
                };
            }
            catch (err) {
                setMcpStatus('disconnected');
            }
        };
        connect();
        return () => {
            controller.abort();
            if (mcpSocket && mcpSocket.readyState === WebSocket.OPEN) {
                mcpSocket.close();
            }
            if (reconnectRef.current) {
                clearTimeout(reconnectRef.current);
            }
            setMcpSocket(null);
        };
    }, [mcpBaseUrl]);
    return {
        health,
        dashboardData,
        loading,
        error,
        logs,
        connectionStatus,
        mcpMessages,
        mcpStatus,
        refresh,
        addLog
    };
};
