import React from 'react';
import { Box } from '@mui/material';
import { AGENT_COLORS } from '../constants/colors';

interface AgentGeometricIconProps {
  agentId: string;
  size?: number;
}

const AgentGeometricIcon: React.FC<AgentGeometricIconProps> = ({ agentId, size = 50 }) => {
  const agentColor = AGENT_COLORS[agentId as keyof typeof AGENT_COLORS] || AGENT_COLORS.coordinator;

  // Unique geometric patterns for each agent
  const patterns: Record<string, React.ReactNode> = {
    'trend-momentum-agent': (
      // Upward arrow pattern with momentum lines
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id="momentumGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={agentColor.primary} stopOpacity="1" />
            <stop offset="100%" stopColor={agentColor.secondary} stopOpacity="1" />
          </linearGradient>
        </defs>
        {/* Momentum lines */}
        <line x1="20" y1="70" x2="30" y2="50" stroke="url(#momentumGrad)" strokeWidth="3" strokeLinecap="round" />
        <line x1="30" y1="50" x2="40" y2="30" stroke="url(#momentumGrad)" strokeWidth="3" strokeLinecap="round" />
        <line x1="40" y1="30" x2="50" y2="20" stroke="url(#momentumGrad)" strokeWidth="3" strokeLinecap="round" />
        {/* Main arrow */}
        <path d="M 50 20 L 70 40 L 60 40 L 60 70 L 40 70 L 40 40 Z" fill="url(#momentumGrad)" />
        {/* Speed lines */}
        <circle cx="75" cy="25" r="3" fill={agentColor.primary} opacity="0.8" />
        <circle cx="80" cy="30" r="2" fill={agentColor.primary} opacity="0.6" />
        <circle cx="85" cy="35" r="2" fill={agentColor.primary} opacity="0.4" />
      </svg>
    ),
    'strategy-optimization-agent': (
      // Hexagonal pattern representing strategy and optimization
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id="strategyGrad" x1="50%" y1="0%" x2="50%" y2="100%">
            <stop offset="0%" stopColor={agentColor.primary} stopOpacity="1" />
            <stop offset="100%" stopColor={agentColor.secondary} stopOpacity="1" />
          </linearGradient>
        </defs>
        {/* Outer hexagon */}
        <polygon points="50,10 85,30 85,70 50,90 15,70 15,30" fill="none" stroke="url(#strategyGrad)" strokeWidth="3" />
        {/* Inner hexagon */}
        <polygon points="50,25 70,40 70,60 50,75 30,60 30,40" fill="url(#strategyGrad)" opacity="0.3" />
        {/* Center optimization symbol */}
        <circle cx="50" cy="50" r="8" fill="url(#strategyGrad)" />
        <path d="M 45 50 L 50 45 L 55 50 L 50 55 Z" fill="white" opacity="0.8" />
      </svg>
    ),
    'financial-sentiment-agent': (
      // Wave pattern representing sentiment flow
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id="sentimentGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={agentColor.primary} stopOpacity="1" />
            <stop offset="50%" stopColor={agentColor.secondary} stopOpacity="1" />
            <stop offset="100%" stopColor={agentColor.primary} stopOpacity="1" />
          </linearGradient>
        </defs>
        {/* Sentiment waves */}
        <path d="M 10 50 Q 25 30, 40 50 T 70 50 T 90 50" fill="none" stroke="url(#sentimentGrad)" strokeWidth="4" strokeLinecap="round" />
        <path d="M 10 60 Q 25 40, 40 60 T 70 60 T 90 60" fill="none" stroke="url(#sentimentGrad)" strokeWidth="3" strokeLinecap="round" opacity="0.7" />
        <path d="M 10 70 Q 25 50, 40 70 T 70 70 T 90 70" fill="none" stroke="url(#sentimentGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
        {/* Emotion indicators */}
        <circle cx="20" cy="30" r="4" fill={agentColor.primary} opacity="0.8" />
        <circle cx="50" cy="25" r="5" fill={agentColor.primary} opacity="0.9" />
        <circle cx="80" cy="30" r="4" fill={agentColor.primary} opacity="0.8" />
      </svg>
    ),
    'market-prediction-agent': (
      // Crystal/divination pattern
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <radialGradient id="predictionGrad" cx="50%" cy="50%">
            <stop offset="0%" stopColor={agentColor.primary} stopOpacity="1" />
            <stop offset="100%" stopColor={agentColor.secondary} stopOpacity="0.5" />
          </radialGradient>
        </defs>
        {/* Crystal shape */}
        <polygon points="50,15 70,35 65,50 50,85 35,50 30,35" fill="url(#predictionGrad)" opacity="0.8" />
        <polygon points="50,20 65,35 60,45 50,75 40,45 35,35" fill="none" stroke={agentColor.primary} strokeWidth="2" />
        {/* Prediction lines */}
        <line x1="50" y1="50" x2="20" y2="20" stroke={agentColor.primary} strokeWidth="2" strokeDasharray="3,3" opacity="0.6" />
        <line x1="50" y1="50" x2="80" y2="20" stroke={agentColor.primary} strokeWidth="2" strokeDasharray="3,3" opacity="0.6" />
        <line x1="50" y1="50" x2="50" y2="10" stroke={agentColor.primary} strokeWidth="2" strokeDasharray="3,3" opacity="0.6" />
        {/* Future indicators */}
        <circle cx="20" cy="20" r="3" fill={agentColor.primary} />
        <circle cx="80" cy="20" r="3" fill={agentColor.primary} />
        <circle cx="50" cy="10" r="3" fill={agentColor.primary} />
      </svg>
    ),
    'volume-microstructure-agent': (
      // Layered volume bars pattern
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id="volumeGrad" x1="0%" y1="100%" x2="0%" y2="0%">
            <stop offset="0%" stopColor={agentColor.primary} stopOpacity="1" />
            <stop offset="100%" stopColor={agentColor.secondary} stopOpacity="1" />
          </linearGradient>
        </defs>
        {/* Volume bars */}
        <rect x="15" y="60" width="12" height="30" fill="url(#volumeGrad)" rx="2" />
        <rect x="30" y="45" width="12" height="45" fill="url(#volumeGrad)" rx="2" />
        <rect x="45" y="30" width="12" height="60" fill="url(#volumeGrad)" rx="2" />
        <rect x="60" y="40" width="12" height="50" fill="url(#volumeGrad)" rx="2" />
        <rect x="75" y="50" width="12" height="40" fill="url(#volumeGrad)" rx="2" />
        {/* Microstructure lines */}
        <line x1="20" y1="55" x2="80" y2="55" stroke={agentColor.primary} strokeWidth="1.5" opacity="0.6" />
        <line x1="25" y1="50" x2="75" y2="50" stroke={agentColor.primary} strokeWidth="1.5" opacity="0.4" />
      </svg>
    ),
    'vpin-hft': (
      // Lightning bolt with speed lines
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <linearGradient id="vpinGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={agentColor.primary} stopOpacity="1" />
            <stop offset="50%" stopColor={agentColor.secondary} stopOpacity="1" />
            <stop offset="100%" stopColor={agentColor.primary} stopOpacity="1" />
          </linearGradient>
        </defs>
        {/* Main lightning bolt */}
        <path d="M 50 10 L 35 40 L 45 40 L 30 70 L 50 50 L 40 50 L 65 90 L 50 60 L 60 60 L 70 30 Z" fill="url(#vpinGrad)" />
        {/* Speed lines */}
        <line x1="10" y1="20" x2="25" y2="35" stroke={agentColor.primary} strokeWidth="2" strokeLinecap="round" opacity="0.7" />
        <line x1="15" y1="30" x2="28" y2="42" stroke={agentColor.primary} strokeWidth="1.5" strokeLinecap="round" opacity="0.5" />
        <line x1="75" y1="20" x2="90" y2="35" stroke={agentColor.primary} strokeWidth="2" strokeLinecap="round" opacity="0.7" />
        <line x1="72" y1="30" x2="85" y2="42" stroke={agentColor.primary} strokeWidth="1.5" strokeLinecap="round" opacity="0.5" />
        {/* HFT indicators */}
        <circle cx="20" cy="15" r="2" fill={agentColor.primary} opacity="0.8" />
        <circle cx="80" cy="15" r="2" fill={agentColor.primary} opacity="0.8" />
      </svg>
    ),
    'coordinator': (
      // Central hub pattern
      <svg width={size} height={size} viewBox="0 0 100 100">
        <defs>
          <radialGradient id="coordGrad" cx="50%" cy="50%">
            <stop offset="0%" stopColor={agentColor.primary} stopOpacity="1" />
            <stop offset="70%" stopColor={agentColor.secondary} stopOpacity="0.6" />
            <stop offset="100%" stopColor={agentColor.primary} stopOpacity="0.2" />
          </radialGradient>
        </defs>
        {/* Central circle */}
        <circle cx="50" cy="50" r="25" fill="url(#coordGrad)" />
        {/* Connection lines */}
        <line x1="50" y1="50" x2="20" y2="20" stroke={agentColor.primary} strokeWidth="2" opacity="0.5" />
        <line x1="50" y1="50" x2="80" y2="20" stroke={agentColor.primary} strokeWidth="2" opacity="0.5" />
        <line x1="50" y1="50" x2="80" y2="50" stroke={agentColor.primary} strokeWidth="2" opacity="0.5" />
        <line x1="50" y1="50" x2="80" y2="80" stroke={agentColor.primary} strokeWidth="2" opacity="0.5" />
        <line x1="50" y1="50" x2="20" y2="80" stroke={agentColor.primary} strokeWidth="2" opacity="0.5" />
        <line x1="50" y1="50" x2="20" y2="50" stroke={agentColor.primary} strokeWidth="2" opacity="0.5" />
        {/* Inner symbol */}
        <circle cx="50" cy="50" r="8" fill={agentColor.primary} />
      </svg>
    ),
  };

  return (
    <Box
      sx={{
        width: size,
        height: size,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        filter: `drop-shadow(0 0 ${size * 0.2}px ${agentColor.primary}80)`,
      }}
    >
      {patterns[agentId] || patterns.coordinator}
    </Box>
  );
};

export default AgentGeometricIcon;
