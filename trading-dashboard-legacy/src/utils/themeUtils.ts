/**
 * Shared theme utilities and common styling patterns
 * Reduces redundancy across components
 */

import { SxProps, Theme } from '@mui/material';

export const commonCardStyles: SxProps<Theme> = {
  background: '#0A0A0F',
  border: '2px solid rgba(14, 165, 233, 0.4)',
  borderRadius: 3,
  position: 'relative',
  overflow: 'hidden',
  transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
  '&:hover': {
    borderColor: '#0EA5E9',
    boxShadow: '0 8px 32px rgba(14, 165, 233, 0.4)',
    transform: 'translateY(-4px)',
  },
};

export const gradientCardStyles = (color1: string, color2: string): SxProps<Theme> => ({
  ...commonCardStyles,
  background: `linear-gradient(135deg, ${color1}15 0%, ${color2}15 100%)`,
  borderColor: `${color1}40`,
  '&:hover': {
    ...commonCardStyles['&:hover'],
    borderColor: color1,
    boxShadow: `0 8px 32px ${color1}40`,
  },
});

export const gradientTextStyles = (color1: string, color2: string): SxProps<Theme> => ({
  background: `linear-gradient(135deg, ${color1} 0%, ${color2} 100%)`,
  backgroundClip: 'text',
  WebkitBackgroundClip: 'text',
  WebkitTextFillColor: 'transparent',
});

export const glowEffectStyles = (color: string, intensity: number = 0.3): SxProps<Theme> => ({
  boxShadow: `0 4px 20px ${color}${Math.floor(intensity * 255).toString(16).padStart(2, '0')}`,
  '&:hover': {
    boxShadow: `0 8px 32px ${color}${Math.floor(intensity * 255 * 1.5).toString(16).padStart(2, '0')}`,
  },
});

export const pulseAnimationStyles: SxProps<Theme> = {
  animation: 'pulse 2s infinite',
  '@keyframes pulse': {
    '0%': { opacity: 1, transform: 'scale(1)' },
    '50%': { opacity: 0.7, transform: 'scale(1.1)' },
    '100%': { opacity: 1, transform: 'scale(1)' },
  },
};

export const fadeInUpStyles: SxProps<Theme> = {
  animation: 'fadeInUp 0.6s ease-out',
  '@keyframes fadeInUp': {
    from: {
      opacity: 0,
      transform: 'translateY(20px)',
    },
    to: {
      opacity: 1,
      transform: 'translateY(0)',
    },
  },
};

export const agentColors: Record<string, { primary: string; accent: string; glow: string }> = {
  'trend-momentum-agent': {
    primary: '#06b6d4',
    accent: '#0891b2',
    glow: '#06b6d4',
  },
  'strategy-optimization-agent': {
    primary: '#8b5cf6',
    accent: '#7c3aed',
    glow: '#8b5cf6',
  },
  'financial-sentiment-agent': {
    primary: '#ef4444',
    accent: '#dc2626',
    glow: '#ef4444',
  },
  'market-prediction-agent': {
    primary: '#f59e0b',
    accent: '#d97706',
    glow: '#f59e0b',
  },
  'volume-microstructure-agent': {
    primary: '#ec4899',
    accent: '#db2777',
    glow: '#ec4899',
  },
  'vpin-hft': {
    primary: '#06b6d4',
    accent: '#0891b2',
    glow: '#06b6d4',
  },
};

export const getAgentColor = (agentType: string): { primary: string; accent: string; glow: string } => {
  return agentColors[agentType] || { primary: '#64748b', accent: '#475569', glow: '#64748b' };
};

export const commonBackgroundGradient = [
  'radial-gradient(ellipse at 20% 30%, rgba(14, 165, 233, 0.03) 0%, transparent 50%)',
  'radial-gradient(ellipse at 80% 70%, rgba(139, 92, 246, 0.03) 0%, transparent 50%)',
  'radial-gradient(ellipse at 50% 50%, rgba(6, 182, 212, 0.02) 0%, transparent 60%)',
].join(', ');

export const organicMeshPattern = {
  backgroundImage: `radial-gradient(circle at 1px 1px, rgba(14, 165, 233, 0.015) 1px, transparent 0)`,
  backgroundSize: '40px 40px',
  opacity: 0.6,
};

export const statusColorMap: Record<string, string> = {
  active: '#10b981',
  idle: '#64748b',
  analyzing: '#3b82f6',
  trading: '#f59e0b',
  error: '#ef4444',
};

export const formatCurrency = (value: number, decimals: number = 2): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
};

export const formatPercentage = (value: number, decimals: number = 2): string => {
  return `${(value * 100).toFixed(decimals)}%`;
};

export const formatNumber = (value: number, decimals: number = 0): string => {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
};
