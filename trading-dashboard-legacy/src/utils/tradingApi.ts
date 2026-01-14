import { getApiUrl } from './apiConfig';

const API_BASE_URL = getApiUrl();

// Get admin token from localStorage or env
const getAdminToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('ADMIN_API_TOKEN') || import.meta.env.VITE_ADMIN_API_TOKEN || null;
};

/**
 * Toggle agent enable/disable status
 */
export const toggleAgent = async (agentId: string, enabled: boolean): Promise<boolean> => {
  const token = getAdminToken();
  if (!token) {
    throw new Error('Admin API token required for agent control');
  }

  const endpoint = enabled
    ? `/api/agents/${agentId}/enable`
    : `/api/agents/${agentId}/disable`;

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Token': token,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    return data.status === 'enabled' || data.status === 'disabled';
  } catch (error) {
    console.error(`Failed to ${enabled ? 'enable' : 'disable'} agent ${agentId}:`, error);
    throw error;
  }
};

/**
 * Get current agent status
 */
export const getAgentStatus = async (agentId: string): Promise<{ enabled: boolean }> => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/agents`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const agents = await response.json();
    const agent = agents.agents?.find((a: any) => a.id === agentId || a.agent_id === agentId);

    return {
      enabled: agent?.status === 'active' || agent?.enabled === true,
    };
  } catch (error) {
    console.error(`Failed to get agent status for ${agentId}:`, error);
    return { enabled: true }; // Default to enabled on error
  }
};

/**
 * Get paper trading mode status
 */
export const getPaperTradingStatus = async (): Promise<{ enabled: boolean }> => {
  try {
    const response = await fetch(`${API_BASE_URL}/healthz`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const health = await response.json();
    return {
      enabled: health.paper_trading === true,
    };
  } catch (error) {
    console.error('Failed to get paper trading status:', error);
    return { enabled: false }; // Default to disabled on error
  }
};

/**
 * Toggle paper trading mode (requires API endpoint to be implemented)
 * Note: Currently paper trading is controlled via env var,
 * but this function is ready for when a toggle endpoint is added
 */
export const togglePaperTrading = async (enabled: boolean): Promise<boolean> => {
  const token = getAdminToken();
  if (!token) {
    throw new Error('Admin API token required for paper trading control');
  }

  // This endpoint would need to be added to the backend
  // For now, return false to indicate it's not yet implemented
  console.warn('Paper trading toggle endpoint not yet implemented - controlled via env var');
  return false;
};
