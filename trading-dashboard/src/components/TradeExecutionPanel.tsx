import React, { useEffect, useState, useMemo, useCallback, memo } from 'react';
import { Box, Card, CardContent, Typography, Chip, List, ListItem, ListItemText, LinearProgress } from '@mui/material';
import { TrendingUp, TrendingDown, CheckCircle, Error as ErrorIcon } from '@mui/icons-material';
import { getApiUrl } from '../utils/apiConfig';

interface ExecutionHistoryItem {
    timestamp: number;
    platform: string;
    symbol: string;
    side: string;
    quantity: number;
    success: boolean;
    latency_ms: number;
    error_message?: string;
    order_id?: string;
}

// Utility functions as stable references
const formatTime = (timestamp: number): string => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleTimeString();
};

const getLatencyColor = (latency: number): string => {
    if (latency < 100) return '#10b981'; // Green
    if (latency < 300) return '#f59e0b'; // Yellow
    return '#ef4444'; // Red
};

// Memoized trade item component for optimized rendering
interface TradeExecutionItemProps {
    item: ExecutionHistoryItem;
}

const TradeExecutionItem = memo<TradeExecutionItemProps>(({ item }) => {
    const formattedTime = useMemo(() => formatTime(item.timestamp), [item.timestamp]);
    const latencyColor = useMemo(() => getLatencyColor(item.latency_ms), [item.latency_ms]);

    const bgColor = item.success ? 'rgba(16, 185, 129, 0.05)' : 'rgba(239, 68, 68, 0.05)';
    const borderColor = item.success ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)';
    const hoverBg = item.success ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)';

    return (
        <ListItem
            sx={{
                bgcolor: bgColor,
                mb: 1,
                borderRadius: 2,
                border: `1px solid ${borderColor}`,
                transition: 'all 0.2s ease',
                '&:hover': { bgcolor: hoverBg }
            }}
        >
            <ListItemText
                primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                        {item.success ? (
                            <CheckCircle sx={{ color: '#10b981', fontSize: 18 }} />
                        ) : (
                            <ErrorIcon sx={{ color: '#ef4444', fontSize: 18 }} />
                        )}
                        {item.side === 'BUY' ? (
                            <TrendingUp sx={{ color: '#10b981', fontSize: 18 }} />
                        ) : (
                            <TrendingDown sx={{ color: '#ef4444', fontSize: 18 }} />
                        )}
                        <Typography variant="body2" sx={{ color: 'white', fontWeight: 600 }}>
                            {item.symbol}
                        </Typography>
                        <Chip
                            label={item.platform.toUpperCase()}
                            size="small"
                            sx={{
                                bgcolor: 'rgba(102, 126, 234, 0.2)',
                                color: '#667eea',
                                height: 20,
                                fontSize: '0.7rem'
                            }}
                        />
                    </Box>
                }
                secondary={
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 0.5 }}>
                        <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.6)' }}>
                            {formattedTime}
                        </Typography>
                        <Chip
                            label={`${item.latency_ms.toFixed(0)}ms`}
                            size="small"
                            sx={{
                                bgcolor: 'rgba(255,255,255,0.1)',
                                color: latencyColor,
                                height: 18,
                                fontSize: '0.65rem'
                            }}
                        />
                        {item.order_id && (
                            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.4)' }}>
                                #{item.order_id.slice(0, 8)}
                            </Typography>
                        )}
                        {item.error_message && (
                            <Typography variant="caption" sx={{ color: '#ef4444' }}>
                                {item.error_message}
                            </Typography>
                        )}
                    </Box>
                }
            />
        </ListItem>
    );
});

TradeExecutionItem.displayName = 'TradeExecutionItem';

const TradeExecutionPanel: React.FC = memo(() => {
    const [history, setHistory] = useState<ExecutionHistoryItem[]>([]);
    const [loading, setLoading] = useState(true);

    // Memoized fetch function
    const fetchHistory = useCallback(async () => {
        try {
            const apiUrl = getApiUrl();
            const response = await fetch(`${apiUrl}/api/platform-router/history?limit=10`);
            const data = await response.json();

            if (data.success) {
                setHistory(data.history);
            }
        } catch (err) {
            console.error('Failed to fetch execution history:', err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchHistory();
        const interval = setInterval(fetchHistory, 3000);
        return () => clearInterval(interval);
    }, [fetchHistory]);

    // Memoized content rendering
    const content = useMemo(() => {
        if (loading) {
            return <LinearProgress />;
        }

        if (history.length === 0) {
            return (
                <Typography sx={{ color: 'rgba(255,255,255,0.5)', textAlign: 'center', py: 4 }}>
                    No recent executions
                </Typography>
            );
        }

        return (
            <List sx={{ maxHeight: 400, overflow: 'auto' }}>
                {history.map((item, index) => (
                    <TradeExecutionItem
                        key={`${item.timestamp}-${index}`}
                        item={item}
                    />
                ))}
            </List>
        );
    }, [loading, history]);

    return (
        <Card sx={{ height: '100%', bgcolor: '#0f1419', border: '1px solid rgba(255,255,255,0.1)' }}>
            <CardContent>
                <Typography variant="h6" sx={{ color: 'white', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                    ⚡ Recent Trade Executions
                </Typography>
                {content}
            </CardContent>
        </Card>
    );
});

TradeExecutionPanel.displayName = 'TradeExecutionPanel';

export default TradeExecutionPanel;
