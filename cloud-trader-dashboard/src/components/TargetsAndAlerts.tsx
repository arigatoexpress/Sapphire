import React from 'react';

interface TargetsData {
  daily_pnl_target: number;
  max_drawdown_limit: number;
  min_confidence_threshold: number;
  target_win_rate: number;
  alerts: string[];
}

interface TargetsAndAlertsProps {
  targets: TargetsData | undefined;
}

const TargetsAndAlerts: React.FC<TargetsAndAlertsProps> = ({ targets }) => {
  if (!targets) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
        <div className="text-center py-4 text-slate-500">
          <p>Loading targets and alerts...</p>
        </div>
      </div>
    );
  }

  const getAlertIcon = (alert: string) => {
    if (alert.includes('⚠️') || alert.toLowerCase().includes('exceeded')) return '⚠️';
    if (alert.includes('🎯')) return '🎯';
    return 'ℹ️';
  };

  const getAlertColor = (alert: string) => {
    if (alert.includes('⚠️') || alert.toLowerCase().includes('exceeded')) return 'bg-red-50 border-red-200 text-red-800';
    if (alert.includes('🎯')) return 'bg-green-50 border-green-200 text-green-800';
    return 'bg-blue-50 border-blue-200 text-blue-800';
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-slate-900">Targets & Alerts</h2>
        <div className="text-sm text-slate-500">
          {targets.alerts.length} active alert{targets.alerts.length !== 1 ? 's' : ''}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Performance Targets */}
        <div>
          <h3 className="text-lg font-medium text-slate-900 mb-4">Performance Targets</h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center space-x-3">
                <span className="text-lg">🎯</span>
                <div>
                  <div className="font-medium text-slate-900">Daily P&L Target</div>
                  <div className="text-sm text-slate-500">Profit goal per day</div>
                </div>
              </div>
              <span className="text-lg font-bold text-green-600">${targets.daily_pnl_target.toFixed(2)}</span>
            </div>

            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center space-x-3">
                <span className="text-lg">📉</span>
                <div>
                  <div className="font-medium text-slate-900">Max Drawdown Limit</div>
                  <div className="text-sm text-slate-500">Maximum loss threshold</div>
                </div>
              </div>
              <span className="text-lg font-bold text-red-600">${Math.abs(targets.max_drawdown_limit).toFixed(2)}</span>
            </div>

            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center space-x-3">
                <span className="text-lg">🎯</span>
                <div>
                  <div className="font-medium text-slate-900">Target Win Rate</div>
                  <div className="text-sm text-slate-500">Minimum success rate</div>
                </div>
              </div>
              <span className="text-lg font-bold text-blue-600">{(targets.target_win_rate * 100).toFixed(1)}%</span>
            </div>

            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
              <div className="flex items-center space-x-3">
                <span className="text-lg">🧠</span>
                <div>
                  <div className="font-medium text-slate-900">Min Confidence</div>
                  <div className="text-sm text-slate-500">AI decision threshold</div>
                </div>
              </div>
              <span className="text-lg font-bold text-purple-600">{(targets.min_confidence_threshold * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* Active Alerts */}
        <div>
          <h3 className="text-lg font-medium text-slate-900 mb-4">Active Alerts</h3>
          {targets.alerts.length === 0 ? (
            <div className="text-center py-8 text-slate-500">
              <span className="text-4xl mb-2 block">✅</span>
              <p>All systems normal</p>
              <p className="text-sm">No alerts at this time</p>
            </div>
          ) : (
            <div className="space-y-3">
              {targets.alerts.map((alert, index) => (
                <div key={index} className={`p-4 rounded-lg border ${getAlertColor(alert)}`}>
                  <div className="flex items-start space-x-3">
                    <span className="text-lg flex-shrink-0">{getAlertIcon(alert)}</span>
                    <div className="flex-1">
                      <p className="font-medium">{alert.replace(/^[⚠️🎯ℹ️]\s*/, '')}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Risk Summary */}
      <div className="mt-6 pt-6 border-t border-slate-200">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-slate-900">{targets.alerts.length}</div>
            <div className="text-sm text-slate-600">Active Alerts</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">${targets.daily_pnl_target.toFixed(0)}</div>
            <div className="text-sm text-slate-600">Daily Target</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-600">${Math.abs(targets.max_drawdown_limit).toFixed(0)}</div>
            <div className="text-sm text-slate-600">Max Loss</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">{(targets.target_win_rate * 100).toFixed(0)}%</div>
            <div className="text-sm text-slate-600">Target Win Rate</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TargetsAndAlerts;
