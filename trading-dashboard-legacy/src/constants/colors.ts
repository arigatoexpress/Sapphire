/**
 * Sapphire Trade - Unified Color Scheme
 * Professional, unique color palette for agents and UI elements
 */

export const AGENT_COLORS = {
    'trend-momentum-agent': {
        primary: '#00D9FF',      // Electric Cyan - represents speed and momentum
        secondary: '#0099CC',    // Deep Cyan
        gradient: 'linear-gradient(135deg, #00D9FF 0%, #0099CC 100%)',
        glow: '#00D9FF',
        name: 'Trend Momentum',
    },
    'strategy-optimization-agent': {
        primary: '#8B5CF6',      // Royal Purple - represents strategy and intelligence
        secondary: '#6D28D9',    // Deep Purple
        gradient: 'linear-gradient(135deg, #8B5CF6 0%, #6D28D9 100%)',
        glow: '#8B5CF6',
        name: 'Strategy Optimization',
    },
    'financial-sentiment-agent': {
        primary: '#F59E0B',      // Amber Gold - represents sentiment and emotion
        secondary: '#D97706',    // Deep Amber
        gradient: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
        glow: '#F59E0B',
        name: 'Financial Sentiment',
    },
    'market-prediction-agent': {
        primary: '#EC4899',      // Vibrant Pink - represents prediction and foresight
        secondary: '#DB2777',    // Deep Pink
        gradient: 'linear-gradient(135deg, #EC4899 0%, #DB2777 100%)',
        glow: '#EC4899',
        name: 'Market Prediction',
    },
    'volume-microstructure-agent': {
        primary: '#10B981',      // Emerald Green - represents volume and growth
        secondary: '#059669',    // Deep Emerald
        gradient: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
        glow: '#10B981',
        name: 'Volume Microstructure',
    },
    'vpin-hft': {
        primary: '#06B6D4',      // Sky Cyan - represents high-frequency trading
        secondary: '#0891B2',    // Deep Sky
        gradient: 'linear-gradient(135deg, #06B6D4 0%, #0891B2 100%)',
        glow: '#06B6D4',
        name: 'VPIN HFT',
    },
    'coordinator': {
        primary: '#0EA5E9',      // Sapphire Blue - brand color
        secondary: '#0284C7',    // Deep Sapphire
        gradient: 'linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%)',
        glow: '#0EA5E9',
        name: 'MCP Coordinator',
    },
} as const;

export const BRAND_COLORS = {
    sapphire: {
        50: '#F0F9FF',
        100: '#E0F2FE',
        200: '#BAE6FD',
        300: '#7DD3FC',
        400: '#38BDF8',
        500: '#0EA5E9',      // Primary brand color
        600: '#0284C7',
        700: '#0369A1',
        800: '#075985',
        900: '#0C4A6E',
    },
    accent: {
        primary: '#0EA5E9',
        secondary: '#8B5CF6',
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
        info: '#06B6D4',
    },
    surface: {
        dark: '#0A0A0F',
        card: 'rgba(15, 23, 42, 0.8)',
        elevated: 'rgba(30, 41, 59, 0.6)',
        border: 'rgba(148, 163, 184, 0.1)',
    },
} as const;

export const STATUS_COLORS = {
    active: '#10B981',
    analyzing: '#06B6D4',
    trading: '#0EA5E9',
    idle: '#64748B',
    error: '#EF4444',
    warning: '#F59E0B',
} as const;
