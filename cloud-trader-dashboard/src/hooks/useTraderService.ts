import { useCallback, useEffect, useState } from 'react';
import { fetchHealth, postStart, postStop, HealthResponse } from '../api/client';
import { LogEntry } from '../components/ActivityLog';

export const useTraderService = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [pollInterval, setPollInterval] = useState(5000);

  const addLog = useCallback((message: string) => {
    const timestamp = new Date().toISOString();
    setLogs((prev) => [{ timestamp, message }, ...prev.slice(0, 49)]);
  }, []);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchHealth();
      setHealth(data);
      addLog(`Health check: ${data.running ? 'Running' : 'Stopped'} ${data.paper_trading ? '(Paper)' : ''}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error fetching health';
      setError(message);
      addLog(`Error: ${message}`);
    } finally {
      setLoading(false);
    }
  }, [addLog]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, pollInterval);
    return () => clearInterval(interval);
  }, [refresh, pollInterval]);

  const temporaryPoll = useCallback(() => {
    setPollInterval(2000);
    setTimeout(() => setPollInterval(5000), 10000);
  }, []);

  const startTrader = useCallback(async () => {
    setLoading(true);
    addLog('Start requested');
    try {
      await postStart();
      temporaryPoll();
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown start error';
      setError(message);
      addLog(`Start failed: ${message}`);
    } finally {
      setLoading(false);
    }
  }, [addLog, refresh, temporaryPoll]);

  const stopTrader = useCallback(async () => {
    setLoading(true);
    addLog('Stop requested');
    try {
      await postStop();
      temporaryPoll();
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown stop error';
      setError(message);
      addLog(`Stop failed: ${message}`);
    } finally {
      setLoading(false);
    }
  }, [addLog, refresh, temporaryPoll]);

  return { health, loading, error, logs, startTrader, stopTrader, refresh };
};

