/**
 * Dynamic Agent Color System
 * Each agent has a unique personality-based color palette that changes with activity
 */

export interface AgentColorPalette {
  primary: string;
  secondary: string;
  accent: string;
  glow: string;
  gradient: string;
  name: string;
  personality: string;
}

// Base color palettes for each agent personality
const basePalettes: Record<string, AgentColorPalette> = {
  'trend-momentum-agent': {
    primary: '#00D9FF',      // Electric Cyan - Speed & Momentum
    secondary: '#0099CC',    // Deep Cyan
    accent: '#00F0FF',       // Bright Cyan
    glow: '#00D9FF',
    gradient: 'linear-gradient(135deg, #00D9FF 0%, #0099CC 100%)',
    name: 'Trend Momentum',
    personality: 'energetic',
  },
  'strategy-optimization-agent': {
    primary: '#8B5CF6',      // Royal Purple - Intelligence & Strategy
    secondary: '#6D28D9',    // Deep Purple
    accent: '#A78BFA',       // Light Purple
    glow: '#8B5CF6',
    gradient: 'linear-gradient(135deg, #8B5CF6 0%, #6D28D9 100%)',
    name: 'Strategy Optimization',
    personality: 'analytical',
  },
  'financial-sentiment-agent': {
    primary: '#F59E0B',      // Amber Gold - Emotion & Sentiment
    secondary: '#D97706',    // Deep Amber
    accent: '#FBBF24',       // Bright Amber
    glow: '#F59E0B',
    gradient: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
    name: 'Financial Sentiment',
    personality: 'empathetic',
  },
  'market-prediction-agent': {
    primary: '#EC4899',      // Vibrant Pink - Prediction & Foresight
    secondary: '#DB2777',    // Deep Pink
    accent: '#F472B6',       // Light Pink
    glow: '#EC4899',
    gradient: 'linear-gradient(135deg, #EC4899 0%, #DB2777 100%)',
    name: 'Market Prediction',
    personality: 'visionary',
  },
  'volume-microstructure-agent': {
    primary: '#10B981',      // Emerald Green - Volume & Growth
    secondary: '#059669',     // Deep Emerald
    accent: '#34D399',       // Bright Emerald
    glow: '#10B981',
    gradient: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
    name: 'Volume Microstructure',
    personality: 'precise',
  },
  'vpin-hft': {
    primary: '#06B6D4',      // Sky Cyan - High-Frequency Trading
    secondary: '#0891B2',    // Deep Sky
    accent: '#22D3EE',      // Bright Sky
    glow: '#06B6D4',
    gradient: 'linear-gradient(135deg, #06B6D4 0%, #0891B2 100%)',
    name: 'VPIN HFT',
    personality: 'lightning',
  },
  'coordinator': {
    primary: '#0EA5E9',      // Sapphire Blue - Coordination
    secondary: '#0284C7',    // Deep Sapphire
    accent: '#38BDF8',      // Light Sapphire
    glow: '#0EA5E9',
    gradient: 'linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%)',
    name: 'MCP Coordinator',
    personality: 'orchestrator',
  },
};

/**
 * Get dynamic color based on agent activity and status
 */
export const getDynamicAgentColor = (
  agentId: string,
  status: 'active' | 'idle' | 'analyzing' | 'trading',
  activityScore: number = 0,
  recentActivity: boolean = false
): AgentColorPalette => {
  const base = basePalettes[agentId] || basePalettes.coordinator;
  
  // Create dynamic variations based on activity
  const intensity = Math.min(1, activityScore / 100);
  const isActive = status === 'active' || status === 'trading' || status === 'analyzing';
  const pulse = recentActivity ? 0.3 : 0;
  
  // Adjust colors based on activity level
  const adjustColor = (color: string, factor: number) => {
    // Convert hex to RGB
    const hex = color.replace('#', '');
    const r = parseInt(hex.substr(0, 2), 16);
    const g = parseInt(hex.substr(2, 2), 16);
    const b = parseInt(hex.substr(4, 2), 16);
    
    // Brighten based on activity
    const brightness = isActive ? 1 + (intensity * 0.2) + pulse : 0.7;
    const newR = Math.min(255, Math.floor(r * brightness));
    const newG = Math.min(255, Math.floor(g * brightness));
    const newB = Math.min(255, Math.floor(b * brightness));
    
    return `#${newR.toString(16).padStart(2, '0')}${newG.toString(16).padStart(2, '0')}${newB.toString(16).padStart(2, '0')}`;
  };

  return {
    ...base,
    primary: adjustColor(base.primary, intensity),
    accent: adjustColor(base.accent, intensity + 0.1),
    glow: adjustColor(base.glow, intensity + 0.2),
  };
};

export const AGENT_COLORS = basePalettes;

