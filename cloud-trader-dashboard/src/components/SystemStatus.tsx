import React from 'react';

interface SystemStatusData {
  services: { [key: string]: string };
  models: { [key: string]: string };
  redis_connected: boolean;
  timestamp: string;
}

interface SystemStatusProps {
  status: SystemStatusData | undefined;
}

const SystemStatus: React.FC<SystemStatusProps> = ({ status }) => {
  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'healthy':
      case 'online':
        return 'bg-green-100 text-green-800';
      case 'unhealthy':
      case 'offline':
        return 'bg-red-100 text-red-800';
      case 'unreachable':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-yellow-100 text-yellow-800';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'healthy':
      case 'online':
        return '🟢';
      case 'unhealthy':
      case 'offline':
        return '🔴';
      case 'unreachable':
        return '⚫';
      default:
        return '🟡';
    }
  };

  const services = status?.services || {};
  const models = status?.models || {};

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-slate-900">System Status</h2>
        <div className="flex items-center space-x-2 text-sm text-slate-500">
          <span>Last updated: {status?.timestamp ? new Date(status.timestamp).toLocaleTimeString() : 'Never'}</span>
          <div className={`w-2 h-2 rounded-full ${status?.redis_connected ? 'bg-green-500' : 'bg-red-500'}`}></div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Services Status */}
        <div>
          <h3 className="text-lg font-medium text-slate-900 mb-4 flex items-center">
            <span className="mr-2">🔧</span>
            Core Services
          </h3>
          <div className="space-y-3">
            {Object.entries(services).map(([service, status]) => (
              <div key={service} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                <div className="flex items-center space-x-3">
                  <span className="text-lg">{getStatusIcon(status)}</span>
                  <span className="font-medium text-slate-900 capitalize">
                    {service.replace('_', ' ')}
                  </span>
                </div>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(status)}`}>
                  {status}
                </span>
              </div>
            ))}
            {Object.keys(services).length === 0 && (
              <div className="text-center py-4 text-slate-500">
                <p>No service data available</p>
              </div>
            )}
          </div>
        </div>

        {/* Models Status */}
        <div>
          <h3 className="text-lg font-medium text-slate-900 mb-4 flex items-center">
            <span className="mr-2">🤖</span>
            AI Models
          </h3>
          <div className="space-y-3">
            {Object.entries(models).map(([model, status]) => (
              <div key={model} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                <div className="flex items-center space-x-3">
                  <span className="text-lg">{getStatusIcon(status)}</span>
                  <span className="font-medium text-slate-900">{model}</span>
                </div>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(status)}`}>
                  {status}
                </span>
              </div>
            ))}
            {Object.keys(models).length === 0 && (
              <div className="text-center py-4 text-slate-500">
                <p>No model data available</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Redis Connection Status */}
      <div className="mt-6 pt-6 border-t border-slate-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <span className="text-lg">{status?.redis_connected ? '🟢' : '🔴'}</span>
            <div>
              <span className="font-medium text-slate-900">Redis Connection</span>
              <p className="text-sm text-slate-500">Data streaming and caching</p>
            </div>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
            status?.redis_connected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}>
            {status?.redis_connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* System Health Summary */}
      <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-50 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-slate-900">
            {Object.values(services).filter(s => s === 'healthy').length}/{Object.keys(services).length}
          </div>
          <div className="text-sm text-slate-600">Services Healthy</div>
        </div>
        <div className="bg-slate-50 rounded-lg p-4 text-center">
          <div className="text-2xl font-bold text-slate-900">
            {Object.values(models).filter(s => s === 'healthy').length}/{Object.keys(models).length}
          </div>
          <div className="text-sm text-slate-600">Models Healthy</div>
        </div>
        <div className="bg-slate-50 rounded-lg p-4 text-center">
          <div className={`text-2xl font-bold ${status?.redis_connected ? 'text-green-600' : 'text-red-600'}`}>
            {status?.redis_connected ? '✓' : '✗'}
          </div>
          <div className="text-sm text-slate-600">Data Pipeline</div>
        </div>
      </div>
    </div>
  );
};

export default SystemStatus;
