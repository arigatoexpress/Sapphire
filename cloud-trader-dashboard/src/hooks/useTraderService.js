import React, { useEffect, useState, useCallback, useRef } from 'react';
import { fetchDashboard } from '../api/client';
export const useTraderService = () => {
    const [health, setHealth] = useState(null);
    const [dashboardData, setDashboardData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [retryCount, setRetryCount] = useState(0);
    const [logs, setLogs] = useState([]);
    const pollInterval = 15000; // Default 15s - faster updates for better UX
    const [connectionStatus, setConnectionStatus] = useState('connecting');
    const [mcpMessages, setMcpMessages] = useState([]);
    const mcpBaseUrl = import.meta.env.VITE_MCP_URL;
    const [mcpStatus, setMcpStatus] = useState(mcpBaseUrl ? 'connecting' : 'disconnected');
    const mcpSocketRef = useRef(null);
    const reconnectRef = useRef(null);
    const addLog = useCallback((message, type = 'info') => {
        const timestamp = new Date().toISOString();
        setLogs((prev) => [{
                timestamp,
                message,
                type
            }, ...prev.slice(0, 99)]); // Keep last 100 logs
    }, []);
    // Use refs to track state without causing re-renders
    const loadingRef = useRef(false);
    const healthRef = useRef(null);
    const retryCountRef = useRef(0);
    const refresh = useCallback(async () => {
        const wasLoading = loadingRef.current;
        if (!wasLoading) {
            loadingRef.current = true;
            setLoading(true);
        }
        setError(null);
        try {
            // Fetch dashboard data - this is our single source of truth
            const data = await fetchDashboard();
            // Only update state if data actually changed to prevent flickering
            setDashboardData((prevData) => {
                // Simple comparison - only update if timestamp changed or it's first load
                if (!prevData || prevData.system_status?.timestamp !== data.system_status?.timestamp) {
                    return data;
                }
                return prevData; // Return previous data to prevent re-render
            });
            // Extract health info from dashboard data
            const healthData = {
                running: data.system_status.services.cloud_trader === 'running',
                paper_trading: data.portfolio.source === 'local', // Assume paper trading if using local portfolio
                last_error: null
            };
            const prevHealth = healthRef.current;
            // Only update health if it actually changed
            if (!prevHealth || prevHealth.running !== healthData.running || prevHealth.paper_trading !== healthData.paper_trading) {
                healthRef.current = healthData;
                setHealth(healthData);
            }
            setConnectionStatus('connected');
            setError(null);
            retryCountRef.current = 0; // Reset retry count on successful connection
            // Only log health checks occasionally to avoid spam
            if (wasLoading || !prevHealth || prevHealth.running !== healthData.running) {
                addLog(`System ${healthData.running ? 'running' : 'stopped'} ${healthData.paper_trading ? '(Paper Trading)' : '(Live Trading)'}`, 'info');
            }
        }
        catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error fetching health';
            const currentRetryCount = retryCountRef.current;
            // Be more forgiving on initial loads and network errors
            const isNetworkError = errorMessage.includes('CORS') || errorMessage.includes('fetch') || errorMessage.includes('Failed to fetch') || errorMessage.includes('NetworkError') || errorMessage.includes('timeout');
            if (isNetworkError && currentRetryCount < 3) {
                // Network errors on initial attempts - these might be temporary
                setConnectionStatus('connecting');
                retryCountRef.current = currentRetryCount + 1;
                addLog(`Network connectivity issue (attempt ${currentRetryCount + 1}/3): ${errorMessage}`, 'warning');
                // Don't show error state yet, let it retry
                setError(null);
            }
            else if (isNetworkError) {
                // After 3 failed attempts, show a user-friendly error
                setError('Unable to connect to trading service. Please check your internet connection and try again.');
                setConnectionStatus('disconnected');
                addLog(`Connection failed after ${currentRetryCount} attempts: ${errorMessage}`, 'error');
            }
            else {
                // Other types of errors (parsing, server errors, etc.)
                setError(errorMessage);
                setConnectionStatus('disconnected');
                addLog(`Connection error: ${errorMessage}`, 'error');
            }
        }
        finally {
            loadingRef.current = false;
            setLoading(false);
        }
    }, [addLog]);
    // Use refs to avoid stale closures in polling
    const pollIntervalRef = React.useRef(pollInterval);
    const connectionStatusRef = React.useRef(connectionStatus);
    // Update refs when values change
    React.useEffect(() => {
        connectionStatusRef.current = connectionStatus;
    }, [connectionStatus]);
    // Store refresh in a ref to avoid dependency issues
    const refreshRef = useRef(refresh);
    useEffect(() => {
        refreshRef.current = refresh;
    }, [refresh]);
    useEffect(() => {
        let isMounted = true;
        let intervalId;
        // Initial load
        if (isMounted) {
            refreshRef.current();
        }
        // Set up polling with exponential backoff on errors
        const scheduleNextPoll = (useInterval) => {
            if (!isMounted)
                return;
            const currentInterval = useInterval ?? pollIntervalRef.current;
            intervalId = setTimeout(async () => {
                if (!isMounted)
                    return;
                await refreshRef.current();
                // Adjust polling interval based on connection status
                const currentStatus = connectionStatusRef.current;
                const baseInterval = pollIntervalRef.current;
                const nextInterval = currentStatus === 'disconnected'
                    ? Math.min(baseInterval * 1.5, 60000) // Max 60s on errors
                    : baseInterval; // Reset to normal
                scheduleNextPoll(nextInterval);
            }, currentInterval);
        };
        // Start polling after initial load
        const initialDelay = setTimeout(() => {
            if (isMounted) {
                scheduleNextPoll();
            }
        }, pollIntervalRef.current);
        return () => {
            isMounted = false;
            if (intervalId !== undefined)
                clearTimeout(intervalId);
            clearTimeout(initialDelay);
        };
    }, []); // Empty deps - using refs to avoid re-runs
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
                    mcpSocketRef.current = socket;
                };
                socket.onerror = () => {
                    setMcpStatus('disconnected');
                };
                socket.onclose = () => {
                    setMcpStatus('disconnected');
                    mcpSocketRef.current = null;
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
                console.error('Failed to initialise MCP socket', err);
            }
        };
        connect();
        return () => {
            controller.abort();
            const activeSocket = mcpSocketRef.current;
            if (activeSocket && activeSocket.readyState === WebSocket.OPEN) {
                activeSocket.close();
            }
            if (reconnectRef.current) {
                clearTimeout(reconnectRef.current);
            }
            mcpSocketRef.current = null;
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
