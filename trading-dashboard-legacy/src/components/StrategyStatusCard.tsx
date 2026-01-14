import React from 'react';
import { Box, Paper, Typography, Chip, LinearProgress } from '@mui/material';
import { Shield, Target, Layers, TrendingUp, Zap } from 'lucide-react';

interface StrategyConfig {
    maxPositions: number;
    currentPositions: number;
    maxPositionSize: number;
    minConfidence: number;
    minAgreement: number;
    baseNotional: number;
}

interface StrategyStatusCardProps {
    config?: StrategyConfig;
    positionCount?: number;
}

const DEFAULT_CONFIG: StrategyConfig = {
    maxPositions: 4,
    currentPositions: 0,
    maxPositionSize: 25,
    minConfidence: 80,
    minAgreement: 60,
    baseNotional: 500
};

export const StrategyStatusCard: React.FC<StrategyStatusCardProps> = ({
    config = DEFAULT_CONFIG,
    positionCount = 0
}) => {
    const effectiveConfig = { ...DEFAULT_CONFIG, ...config, currentPositions: positionCount };
    const positionUtilization = (effectiveConfig.currentPositions / effectiveConfig.maxPositions) * 100;

    return (
        <Paper sx={{
            p: 3,
            borderRadius: 2,
            background: 'linear-gradient(135deg, rgba(10,11,16,0.95), rgba(15,16,22,0.9))',
            border: '1px solid rgba(138,43,226,0.2)',
            position: 'relative',
            overflow: 'hidden'
        }}>
            {/* Purple glow effect */}
            <Box sx={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: 2,
                background: 'linear-gradient(90deg, transparent, #8a2be2, transparent)',
                opacity: 0.6
            }} />

            {/* Header */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
                <Box sx={{
                    p: 1,
                    borderRadius: 1.5,
                    background: 'rgba(138,43,226,0.15)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                }}>
                    <Shield size={20} color="#8a2be2" />
                </Box>
                <Box>
                    <Typography variant="overline" sx={{ color: '#8a2be2', fontWeight: 700, letterSpacing: 1.2 }}>
                        STRATEGY MODE
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#666', display: 'block' }}>
                        Capital efficiency optimized
                    </Typography>
                </Box>
                <Chip
                    label="ULTRA-CONCENTRATED"
                    size="small"
                    sx={{
                        ml: 'auto',
                        bgcolor: 'rgba(138,43,226,0.2)',
                        color: '#8a2be2',
                        fontWeight: 700,
                        fontSize: '0.6rem'
                    }}
                />
            </Box>

            {/* Position Utilization */}
            <Box sx={{ mb: 2.5 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="caption" sx={{ color: '#888' }}>
                        <Layers size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                        Position Slots
                    </Typography>
                    <Typography variant="caption" sx={{
                        color: '#fff',
                        fontWeight: 700,
                        fontFamily: 'JetBrains Mono, monospace'
                    }}>
                        {effectiveConfig.currentPositions} / {effectiveConfig.maxPositions}
                    </Typography>
                </Box>
                <LinearProgress
                    variant="determinate"
                    value={positionUtilization}
                    sx={{
                        height: 6,
                        borderRadius: 1,
                        bgcolor: 'rgba(255,255,255,0.05)',
                        '& .MuiLinearProgress-bar': {
                            bgcolor: positionUtilization >= 75 ? '#ff6b6b' : '#8a2be2',
                            borderRadius: 1
                        }
                    }}
                />
            </Box>

            {/* Strategy Metrics Grid */}
            <Box sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: 2,
                mt: 3
            }}>
                <Box sx={{
                    p: 1.5,
                    borderRadius: 1,
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,255,255,0.04)'
                }}>
                    <Typography variant="caption" sx={{ color: '#666', display: 'block', mb: 0.5 }}>
                        Max Size
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.5 }}>
                        <Typography sx={{
                            color: '#00d4aa',
                            fontWeight: 700,
                            fontFamily: 'JetBrains Mono',
                            fontSize: '1.1rem'
                        }}>
                            {effectiveConfig.maxPositionSize}%
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#555' }}>per trade</Typography>
                    </Box>
                </Box>

                <Box sx={{
                    p: 1.5,
                    borderRadius: 1,
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,255,255,0.04)'
                }}>
                    <Typography variant="caption" sx={{ color: '#666', display: 'block', mb: 0.5 }}>
                        Min Confidence
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.5 }}>
                        <Typography sx={{
                            color: '#ffc107',
                            fontWeight: 700,
                            fontFamily: 'JetBrains Mono',
                            fontSize: '1.1rem'
                        }}>
                            {effectiveConfig.minConfidence}%
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#555' }}>threshold</Typography>
                    </Box>
                </Box>

                <Box sx={{
                    p: 1.5,
                    borderRadius: 1,
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,255,255,0.04)'
                }}>
                    <Typography variant="caption" sx={{ color: '#666', display: 'block', mb: 0.5 }}>
                        Position Sizing
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.5 }}>
                        <Typography sx={{
                            color: '#fff',
                            fontWeight: 700,
                            fontFamily: 'JetBrains Mono',
                            fontSize: '1.1rem'
                        }}>
                            Dynamic
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#555' }}>Conviction</Typography>
                    </Box>
                </Box>

                <Box sx={{
                    p: 1.5,
                    borderRadius: 1,
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,255,255,0.04)'
                }}>
                    <Typography variant="caption" sx={{ color: '#666', display: 'block', mb: 0.5 }}>
                        Risk Style
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Zap size={14} color="#00d4aa" />
                        <Typography sx={{
                            color: '#00d4aa',
                            fontWeight: 700,
                            fontSize: '0.8rem'
                        }}>
                            High Conviction
                        </Typography>
                    </Box>
                </Box>
            </Box>

            {/* Features List */}
            <Box sx={{
                mt: 3,
                pt: 2,
                borderTop: '1px solid rgba(255,255,255,0.05)',
                display: 'flex',
                gap: 1,
                flexWrap: 'wrap'
            }}>
                <Chip label="ATR Stops" size="small" sx={{ bgcolor: 'rgba(0,212,170,0.1)', color: '#00d4aa', fontSize: '0.6rem' }} />
                <Chip label="Re-entry Queue" size="small" sx={{ bgcolor: 'rgba(255,193,7,0.1)', color: '#ffc107', fontSize: '0.6rem' }} />
                <Chip label="Counter-Retail" size="small" sx={{ bgcolor: 'rgba(138,43,226,0.1)', color: '#8a2be2', fontSize: '0.6rem' }} />
                <Chip label="Dynamic Leverage" size="small" sx={{ bgcolor: 'rgba(255,107,107,0.1)', color: '#ff6b6b', fontSize: '0.6rem' }} />
            </Box>
        </Paper>
    );
};

export default StrategyStatusCard;
