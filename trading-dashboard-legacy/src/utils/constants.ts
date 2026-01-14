/**
 * Shared constants used across the application
 */

export const AGENT_TYPES = [
  'trend-momentum-agent',
  'strategy-optimization-agent',
  'financial-sentiment-agent',
  'market-prediction-agent',
  'volume-microstructure-agent',
  'vpin-hft',
] as const;

export const AGENT_CONFIG = {
  'trend-momentum-agent': {
    name: 'Trend Momentum',
    model: 'Gemini 2.0 Flash Exp',
    emoji: '📈',
  },
  'strategy-optimization-agent': {
    name: 'Strategy Optimization',
    model: 'Gemini Exp-1206',
    emoji: '🎯',
  },
  'financial-sentiment-agent': {
    name: 'Financial Sentiment',
    model: 'Gemini 2.0 Flash Exp',
    emoji: '💭',
  },
  'market-prediction-agent': {
    name: 'Market Prediction',
    model: 'Gemini Exp-1206',
    emoji: '🔮',
  },
  'volume-microstructure-agent': {
    name: 'Volume Microstructure',
    model: 'Codey 001',
    emoji: '📊',
  },
  'vpin-hft': {
    name: 'VPIN HFT',
    model: 'Gemini 2.0 Flash Exp',
    emoji: '⚡',
  },
} as const;

import { getApiUrl } from './apiConfig';

export const API_BASE_URL = getApiUrl();

export const REFRESH_INTERVALS = {
  data: 5000, // 5 seconds
  trades: 3000, // 3 seconds
  metrics: 10000, // 10 seconds
  portfolio: 15000, // 15 seconds
} as const;

export const CHART_TIME_RANGES = ['1h', '24h', '7d', '30d'] as const;
export type ChartTimeRange = typeof CHART_TIME_RANGES[number];

export const TRADE_STATUS_COLORS = {
  pending: '#f59e0b',
  filled: '#10b981',
  partial: '#3b82f6',
  cancelled: '#ef4444',
} as const;
