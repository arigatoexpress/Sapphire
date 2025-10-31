const API_URL = import.meta.env.VITE_API_URL || '';

export interface HealthResponse {
  running: boolean;
  paper_trading: boolean;
  last_error: string | null;
}

interface ActionResponse {
  status: string;
}

const fetchWithTimeout = async (
  url: string,
  options: RequestInit = {},
  timeout = 10_000,
) => {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }
    return (await response.json()) as unknown;
  } finally {
    clearTimeout(id);
  }
};

export const fetchHealth = async (): Promise<HealthResponse> => {
  return (await fetchWithTimeout(`${API_URL}/healthz`)) as HealthResponse;
};

export const postStart = async (): Promise<ActionResponse> => {
  return (await fetchWithTimeout(`${API_URL}/start`, { method: 'POST' })) as ActionResponse;
};

export const postStop = async (): Promise<ActionResponse> => {
  return (await fetchWithTimeout(`${API_URL}/stop`, { method: 'POST' })) as ActionResponse;
};

