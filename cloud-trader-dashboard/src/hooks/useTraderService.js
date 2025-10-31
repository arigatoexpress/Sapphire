import { useCallback, useEffect, useState } from 'react';
import { fetchHealth, postStart, postStop } from '../api/client';
export const useTraderService = () => {
    const [health, setHealth] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [logs, setLogs] = useState([]);
    const [pollInterval, setPollInterval] = useState(10000); // Default 10s
    const [connectionStatus, setConnectionStatus] = useState('connecting');
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
            const data = await fetchHealth();
            setHealth(data);
            setConnectionStatus('connected');
            setError(null);
            // Only log health checks occasionally to avoid spam
            if (wasLoading || !health || health.running !== data.running) {
                addLog(`System ${data.running ? 'running' : 'stopped'} ${data.paper_trading ? '(Paper Trading)' : '(Live Trading)'}`, 'info');
            }
        }
        catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error fetching health';
            setError(errorMessage);
            setConnectionStatus('disconnected');
            addLog(`Connection error: ${errorMessage}`, 'error');
            // If it's a network error, don't spam the logs
            if (!errorMessage.includes('fetch')) {
                addLog(`Health check failed: ${errorMessage}`, 'error');
            }
        }
        finally {
            setLoading(false);
        }
    }, [loading, health, addLog]);
    useEffect(() => {
        // Initial load
        refresh();
        // Set up polling with exponential backoff on errors
        let intervalId;
        let currentInterval = pollInterval;
        const scheduleNextPoll = () => {
            intervalId = setTimeout(async () => {
                await refresh();
                // Adjust polling interval based on connection status
                if (connectionStatus === 'disconnected') {
                    currentInterval = Math.min(currentInterval * 1.5, 30000); // Max 30s
                }
                else {
                    currentInterval = pollInterval; // Reset to normal
                }
                scheduleNextPoll();
            }, currentInterval);
        };
        scheduleNextPoll();
        return () => {
            if (intervalId)
                clearTimeout(intervalId);
        };
    }, [refresh, pollInterval, connectionStatus]);
    const temporaryPoll = useCallback(() => {
        setPollInterval(2000);
        setTimeout(() => setPollInterval(10000), 15000); // Reset after 15 seconds
    }, []);
    const startTrader = useCallback(async () => {
        setLoading(true);
        setError(null);
        addLog('🚀 Starting trading system...', 'info');
        try {
            const response = await postStart();
            addLog('✅ Trading system started successfully', 'success');
            temporaryPoll();
            await refresh();
        }
        catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown start error';
            setError(errorMessage);
            addLog(`❌ Failed to start trading system: ${errorMessage}`, 'error');
        }
        finally {
            setLoading(false);
        }
    }, [addLog, temporaryPoll, refresh]);
    const stopTrader = useCallback(async () => {
        setLoading(true);
        setError(null);
        addLog('🛑 Stopping trading system...', 'warning');
        try {
            const response = await postStop();
            addLog('✅ Trading system stopped successfully', 'success');
            temporaryPoll();
            await refresh();
        }
        catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown stop error';
            setError(errorMessage);
            addLog(`❌ Failed to stop trading system: ${errorMessage}`, 'error');
        }
        finally {
            setLoading(false);
        }
    }, [addLog, temporaryPoll, refresh]);
    // Connection status indicator
    useEffect(() => {
        if (connectionStatus === 'disconnected' && !error) {
            addLog('🔄 Attempting to reconnect...', 'warning');
        }
        else if (connectionStatus === 'connected' && error) {
            setConnectionStatus('disconnected');
        }
    }, [connectionStatus, error, addLog]);
    return {
        health,
        loading,
        error,
        logs,
        connectionStatus,
        startTrader,
        stopTrader,
        refresh,
        addLog
    };
};
