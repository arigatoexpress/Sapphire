import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Grid,
  LinearProgress,
  Chip,
  Avatar,
  Tooltip,
  IconButton,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  AccountBalance,
  Psychology,
  Analytics,
  Warning,
  Refresh,
  Info,
} from '@mui/icons-material';
import { useTrading } from '../contexts/TradingContext';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  color: string;
  loading?: boolean;
  tooltip?: string;
}

const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon,
  trend,
  trendValue,
  color,
  loading,
  tooltip
}) => {
  const getTrendIcon = () => {
    switch (trend) {
      case 'up':
        return <TrendingUp sx={{ color: '#00d4aa', fontSize: 16 }} />;
      case 'down':
        return <TrendingDown sx={{ color: '#ff6b35', fontSize: 16 }} />;
      default:
        return null;
    }
  };

  const getTrendColor = () => {
    switch (trend) {
      case 'up':
        return '#00d4aa';
      case 'down':
        return '#ff6b35';
      default:
        return '#888';
    }
  };

  return (
    <Card
      sx={{
        height: '100%',
        background: `linear-gradient(135deg, ${color}15 0%, ${color}08 100%)`,
        border: `1px solid ${color}30`,
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: `0 12px 24px ${color}20`,
          borderColor: `${color}50`,
        },
        position: 'relative',
        overflow: 'hidden',
        '&::before': {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '3px',
          background: `linear-gradient(90deg, ${color}, ${color}80)`,
        }
      }}
    >
      <CardContent sx={{ p: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={2}>
          <Box>
            <Typography
              variant="overline"
              sx={{
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'text.secondary',
                letterSpacing: '0.5px',
                textTransform: 'uppercase'
              }}
            >
              {title}
            </Typography>
            {tooltip && (
              <Tooltip title={tooltip} arrow placement="top">
                <IconButton size="small" sx={{ p: 0, ml: 0.5, mt: -0.5 }}>
                  <Info sx={{ fontSize: 14, color: 'text.secondary' }} />
                </IconButton>
              </Tooltip>
            )}
          </Box>
          <Avatar
            sx={{
              bgcolor: `${color}20`,
              color: color,
              width: 48,
              height: 48,
            }}
          >
            {icon}
          </Avatar>
        </Box>

        {loading ? (
          <Box sx={{ mt: 2 }}>
            <LinearProgress sx={{ borderRadius: 1, height: 6 }} />
          </Box>
        ) : (
          <>
            <Typography
              variant="h3"
              sx={{
                fontWeight: 700,
                fontSize: '2rem',
                color: 'text.primary',
                mb: 1,
                background: `linear-gradient(45deg, ${color}, ${color}CC)`,
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}
            >
              {typeof value === 'number' ? value.toLocaleString() : value}
            </Typography>

            {subtitle && (
              <Typography
                variant="body2"
                sx={{
                  color: 'text.secondary',
                  mb: trend ? 1 : 0,
                  fontSize: '0.875rem'
                }}
              >
                {subtitle}
              </Typography>
            )}

            {trend && trendValue && (
              <Box display="flex" alignItems="center" gap={0.5}>
                {getTrendIcon()}
                <Typography
                  variant="body2"
                  sx={{
                    color: getTrendColor(),
                    fontWeight: 600,
                    fontSize: '0.8rem'
                  }}
                >
                  {trendValue}
                </Typography>
              </Box>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
};

const EnhancedMetrics: React.FC = () => {
  const { portfolio, agentActivities, recentSignals, loading, refreshData } = useTrading();

  const calculatePortfolioChange = () => {
    if (!portfolio) return { trend: 'neutral' as const, value: '0%' };
    // This would calculate actual portfolio change - for now, mock data
    const change = 2.5; // Mock positive change
    const trend: 'up' | 'down' | 'neutral' = change > 0 ? 'up' : change < 0 ? 'down' : 'neutral';
    return {
      trend,
      value: `${change > 0 ? '+' : ''}${change.toFixed(1)}%`
    };
  };

  const portfolioChange = calculatePortfolioChange();

  return (
    <Box sx={{ mb: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" sx={{ fontWeight: 600, color: 'text.primary' }}>
          Key Metrics
        </Typography>
        <Tooltip title="Refresh data" arrow>
          <IconButton
            onClick={refreshData}
            disabled={loading}
            sx={{
              bgcolor: 'background.paper',
              border: '1px solid',
              borderColor: 'divider',
              '&:hover': {
                bgcolor: 'action.hover',
              }
            }}
          >
            <Refresh sx={{ fontSize: 20 }} />
          </IconButton>
        </Tooltip>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Bot Trading Capital"
            value={portfolio?.agent_allocations ? Object.values(portfolio.agent_allocations).reduce((sum: number, val: any) => sum + (val || 0), 0) : 3000}
            subtitle="AI agent trading capital"
            icon={<AccountBalance />}
            color="#00d4aa"
            trend={portfolioChange.trend}
            trendValue={portfolioChange.value}
            loading={loading}
            tooltip="Total trading capital allocated to AI agents ($500 per agent)"
          />
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Active Agents"
            value={agentActivities.length}
            subtitle={`${agentActivities.filter(a => a.activity_score > 5).length} high activity`}
            icon={<Psychology />}
            color="#ff6b35"
            loading={loading}
            tooltip="AI agents currently engaged in trading"
          />
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Trading Signals"
            value={recentSignals.length}
            subtitle="Recent activity"
            icon={<Analytics />}
            color="#4ecdc4"
            loading={loading}
            tooltip="Trading decisions made in last 24 hours"
          />
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Risk Level"
            value={portfolio ? `${(portfolio.risk_limit * 100).toFixed(1)}%` : '15.0%'}
            subtitle="Max drawdown limit"
            icon={<Warning />}
            color={portfolio?.agent_allocations ? '#00d4aa' : '#ffaa00'}
            loading={loading}
            tooltip="Maximum allowed portfolio drawdown"
          />
        </Grid>
      </Grid>

      {/* Status Indicators */}
      <Box sx={{ mt: 3, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <Chip
          label="System Online"
          sx={{
            bgcolor: '#00d4aa20',
            color: '#00d4aa',
            border: '1px solid #00d4aa40',
            '& .MuiChip-icon': { color: '#00d4aa' }
          }}
          icon={<div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#00d4aa', marginLeft: 8 }} />}
        />
        <Chip
          label="Automated Trading"
          sx={{
            bgcolor: '#ff6b3520',
            color: '#ff6b35',
            border: '1px solid #ff6b3540',
          }}
        />
        <Chip
          label="Risk Controls Active"
          sx={{
            bgcolor: '#4ecdc420',
            color: '#4ecdc4',
            border: '1px solid #4ecdc440',
          }}
        />
      </Box>
    </Box>
  );
};

export default EnhancedMetrics;
