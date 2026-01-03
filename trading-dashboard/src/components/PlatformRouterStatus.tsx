import React, { useEffect, useState, useMemo, useCallback, memo } from 'react';
import { Box, Card, CardContent, Typography, Chip, Grid, LinearProgress, Tooltip } from '@mui/material';
import { CheckCircle, Error, Warning, Speed } from '@mui/icons-material';
import { getApiUrl } from '../utils/apiConfig';

interface PlatformHealth {
    platform: string;
    is_healthy: boolean;
    status: 'healthy' | 'unhealthy';
    consecutive_failures: number;
    error_message?: string;
    last_check: number;
}

interface PlatformMetrics {
    total_executions: number;
    successful_executions: number;
    failed_executions: number;
    success_rate: number;
    avg_latency_ms: number;
}

interface PlatformRouterStatusData {
    adapters: string[];
    health: {
        platforms: Record<string, PlatformHealth>;
        overall_healthy: boolean;
        total_platforms: number;
        healthy_platforms: number;
    };
    metrics: {
        total_executions: number;
        successful_executions: number;
        overall_success_rate: number;
        by_platform: Record<string, PlatformMetrics>;
    };
}

// Memoized sub-component for individual platform cards
interface PlatformHealthCardProps {
    name: string;
    health: PlatformHealth;
    metrics?: PlatformMetrics;
}

const PlatformHealthCard = memo<PlatformHealthCardProps>(({ name, health, metrics }) => {
    const healthColor = useMemo(() => {
        if (health.is_healthy) return '#10b981';
        if (health.consecutive_failures > 0 && health.consecutive_failures < 3) return '#f59e0b';
        return '#ef4444';
    }, [health.is_healthy, health.consecutive_failures]);

    const healthIcon = useMemo(() => {
        if (health.is_healthy) {
            return <CheckCircle sx={{ color: '#10b981' }} />;
        } else if (health.consecutive_failures > 0) {
            return <Warning sx={{ color: '#f59e0b' }} />;
        } else {
            return <Error sx={{ color: '#ef4444' }} />;
        }
    }, [health.is_healthy, health.consecutive_failures]);

    return (
        <Grid item xs={6}>
            <Tooltip title={health.error_message || 'Healthy'} arrow>
                <Box
                    sx={{
                        p: 1.5,
                        borderRadius: 2,
                        bgcolor: 'rgba(255,255,255,0.1)',
                        backdropFilter: 'blur(10px)',
                        border: `2px solid ${healthColor}`,
                        transition: 'all 0.3s ease',
                        '&:hover': {
                            bgcolor: 'rgba(255,255,255,0.15)',
                            transform: 'translateY(-2px)'
                        }
                    }}
                >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="subtitle2" sx={{ textTransform: 'uppercase', fontWeight: 700 }}>
                            {name}
                        </Typography>
                        {healthIcon}
                    </Box>
                    {metrics && (
                        <Box sx={{ mt: 1 }}>
                            <Typography variant="caption" sx={{ opacity: 0.9 }}>
                                {metrics.total_executions} trades
                            </Typography>
                            <Box sx={{ display: 'flex', gap: 1, mt: 0.5 }}>
                                <Chip
                                    size="small"
                                    label={`${(metrics.success_rate * 100).toFixed(1)}%`}
                                    sx={{
                                        bgcolor: 'rgba(255,255,255,0.2)',
                                        color: 'white',
                                        height: 20,
                                        fontSize: '0.7rem'
                                    }}
                                />
                                <Chip
                                    size="small"
                                    label={`${metrics.avg_latency_ms.toFixed(0)}ms`}
                                    sx={{
                                        bgcolor: 'rgba(255,255,255,0.2)',
                                        color: 'white',
                                        height: 20,
                                        fontSize: '0.7rem'
                                    }}
                                />
                            </Box>
                        </Box>
                    )}
                </Box>
            </Tooltip>
        </Grid>
    );
});

PlatformHealthCard.displayName = 'PlatformHealthCard';

const PlatformRouterStatus: React.FC = memo(() => {
    const [status, setStatus] = useState<PlatformRouterStatusData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Memoized fetch function
    const fetchStatus = useCallback(async () => {
        try {
            const apiUrl = getApiUrl();
            const response = await fetch(`${apiUrl}/api/platform-router/status`);
            const data = await response.json();

            if (data.success) {
                setStatus(data);
                setError(null);
            } else {
                setError(data.error || 'Failed to load platform router status');
            }
        } catch (err) {
            setError('Failed to connect to platform router');
            console.error('Platform router status error:', err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 5000);
        return () => clearInterval(interval);
    }, [fetchStatus]);

    // Memoized computed values
    const backgroundGradient = useMemo(() => {
        if (!status) return 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
        return status.health.overall_healthy
            ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
            : 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)';
    }, [status?.health?.overall_healthy]);

    const statusLabel = useMemo(() => {
        if (!status) return 'LOADING';
        return status.health.overall_healthy ? 'ALL SYSTEMS OPERATIONAL' : 'DEGRADED';
    }, [status?.health?.overall_healthy]);

    if (loading) {
        return (
            <Card sx={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', minHeight: 120 }}>
                <CardContent>
                    <LinearProgress />
                    <Typography sx={{ mt: 2, color: 'white' }}>Loading Platform Router...</Typography>
                </CardContent>
            </Card>
        );
    }

    if (error || !status) {
        return (
            <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', minHeight: 120 }}>
                <CardContent>
                    <Typography variant="h6" sx={{ color: 'white', display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Error /> Platform Router Offline
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'white', opacity: 0.9, mt: 1 }}>
                        {error}
                    </Typography>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card
            sx={{
                background: backgroundGradient,
                color: 'white',
                backdropFilter: 'blur(10px)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.1)'
            }}
        >
            <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                    <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Speed /> Platform Router
                    </Typography>
                    <Chip
                        label={statusLabel}
                        sx={{
                            bgcolor: status.health.overall_healthy ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                            color: 'white',
                            fontWeight: 600,
                            border: `1px solid ${status.health.overall_healthy ? '#10b981' : '#ef4444'}`
                        }}
                    />
                </Box>

                <Grid container spacing={2}>
                    {Object.entries(status.health.platforms).map(([name, health]) => (
                        <PlatformHealthCard
                            key={name}
                            name={name}
                            health={health}
                            metrics={status.metrics.by_platform[name]}
                        />
                    ))}
                </Grid>

                {/* Overall Stats */}
                <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid rgba(255,255,255,0.2)' }}>
                    <Grid container spacing={2}>
                        <Grid item xs={4}>
                            <Typography variant="caption" sx={{ opacity: 0.8 }}>Total Trades</Typography>
                            <Typography variant="h6" sx={{ fontWeight: 700 }}>
                                {status.metrics.total_executions}
                            </Typography>
                        </Grid>
                        <Grid item xs={4}>
                            <Typography variant="caption" sx={{ opacity: 0.8 }}>Success Rate</Typography>
                            <Typography variant="h6" sx={{ fontWeight: 700 }}>
                                {(status.metrics.overall_success_rate * 100).toFixed(1)}%
                            </Typography>
                        </Grid>
                        <Grid item xs={4}>
                            <Typography variant="caption" sx={{ opacity: 0.8 }}>Platforms</Typography>
                            <Typography variant="h6" sx={{ fontWeight: 700 }}>
                                {status.health.healthy_platforms}/{status.health.total_platforms}
                            </Typography>
                        </Grid>
                    </Grid>
                </Box>
            </CardContent>
        </Card>
    );
});

PlatformRouterStatus.displayName = 'PlatformRouterStatus';

export default PlatformRouterStatus;
