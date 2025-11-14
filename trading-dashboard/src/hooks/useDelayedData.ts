import { useMemo } from 'react';

/**
 * Hook to delay sensitive trading data (positions, trades) by 1 minute
 * while keeping other real-time data (metrics, activity) immediate
 */
export const useDelayedData = <T extends { timestamp?: string; last_activity?: string }>(
  data: T[],
  delayMinutes: number = 1
): T[] => {
  return useMemo(() => {
    const now = Date.now();
    const delayMs = delayMinutes * 60 * 1000; // Convert minutes to milliseconds
    const cutoffTime = now - delayMs;

    return data.filter((item) => {
      // Get timestamp from various possible fields
      const timestamp = item.timestamp || item.last_activity;
      if (!timestamp) {
        // If no timestamp, include it (assume it's old enough or not sensitive)
        return true;
      }

      // Parse timestamp (handle ISO strings)
      const itemTime = new Date(timestamp).getTime();
      
      // Only include items older than the delay
      return itemTime <= cutoffTime;
    });
  }, [data, delayMinutes]);
};

/**
 * Hook to filter agent activities, delaying trade counts and position updates
 * but keeping activity scores and communication counts real-time
 */
export const useDelayedAgentActivities = <T extends {
  trading_count?: number;
  last_activity?: string;
  timestamp?: string;
  [key: string]: any;
}>(
  activities: T[],
  delayMinutes: number = 1
): T[] => {
  return useMemo(() => {
    const now = Date.now();
    const delayMs = delayMinutes * 60 * 1000;
    const cutoffTime = now - delayMs;

    return activities.map((activity) => {
      const timestamp = activity.timestamp || activity.last_activity;
      
      // If activity is recent (within delay window), hide trading_count
      if (timestamp) {
        const activityTime = new Date(timestamp).getTime();
        if (activityTime > cutoffTime) {
          // Return activity with trading_count set to 0 or previous value
          return {
            ...activity,
            trading_count: 0, // Hide recent trades
          };
        }
      }

      // If no timestamp or old enough, return as-is
      return activity;
    });
  }, [activities, delayMinutes]);
};

/**
 * Hook to delay recent signals (trades) by 1 minute
 */
export const useDelayedSignals = <T extends { timestamp?: string }>(
  signals: T[],
  delayMinutes: number = 1
): T[] => {
  return useDelayedData(signals, delayMinutes);
};

