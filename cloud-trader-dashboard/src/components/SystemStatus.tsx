import React from 'react';

interface CacheStatus {
  backend: string;
  connected: boolean;
}

interface SystemStatusData {
  services: { [key: string]: string };
  models: { [key: string]: string };
  cache: CacheStatus;
  storage_ready: boolean;
  pubsub_connected: boolean;
  feature_store_ready: boolean;
  bigquery_ready: boolean;
  timestamp: string;
}

interface SystemStatusProps {
  status: SystemStatusData | undefined;
}

const badgeTone = (value: string | boolean) => {
  const normalized = typeof value === 'string' ? value.toLowerCase() : value;
  if (normalized === true || normalized === 'online' || normalized === 'healthy' || normalized === 'connected') {
    return 'bg-emerald-100/60 text-emerald-600';
  }
  if (normalized === false || normalized === 'offline' || normalized === 'unhealthy' || normalized === 'disconnected') {
    return 'bg-rose-100/60 text-rose-600';
  }
  return 'bg-slate-200/60 text-slate-600';
};

const badgeIcon = (value: string | boolean) => {
  const normalized = typeof value === 'string' ? value.toLowerCase() : value;
  if (normalized === true || normalized === 'online' || normalized === 'healthy' || normalized === 'connected') {
    return '🟢';
  }
  if (normalized === false || normalized === 'offline' || normalized === 'unhealthy' || normalized === 'disconnected') {
    return '🔴';
  }
  return '🟡';
};

const SystemStatus: React.FC<SystemStatusProps> = ({ status }) => {
  const services = status?.services ?? {};
  const models = status?.models ?? {};

  const infrastructureChecks = [
    {
      label: `Cache (${status?.cache?.backend ?? 'memory'})`,
      value: status?.cache?.connected ?? false,
    },
    {
      label: 'Storage',
      value: status?.storage_ready ?? false,
    },
    {
      label: 'Pub/Sub',
      value: status?.pubsub_connected ?? false,
    },
    {
      label: 'Feature Store',
      value: status?.feature_store_ready ?? false,
    },
    {
      label: 'BigQuery',
      value: status?.bigquery_ready ?? false,
    },
  ];

  return (
    <div className="sapphire-panel border border-brand-border/50 bg-brand-abyss/70 p-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.32em] text-brand-muted/80">System Status</p>
          <h2 className="text-xl font-semibold text-brand-ice">Runtime Snapshot</h2>
        </div>
        <div className="flex items-center gap-2 text-xs text-brand-muted/70">
          <span>Last updated:</span>
          <span className="rounded-full bg-brand-border/60 px-2 py-1 text-brand-ice">
            {status?.timestamp ? new Date(status.timestamp).toLocaleTimeString() : 'Never'}
          </span>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[2fr,1fr]">
        <div className="space-y-4">
          <section>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-brand-muted/70">Core Services</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {Object.entries(services).map(([service, svcStatus]) => (
                <div key={service} className="flex items-center justify-between rounded-lg bg-brand-midnight/70 px-3 py-2">
                  <div className="flex items-center gap-2 text-brand-ice">
                    <span>{badgeIcon(svcStatus)}</span>
                    <span className="capitalize tracking-wide">{service.replace('_', ' ')}</span>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badgeTone(svcStatus)}`}>
                    {svcStatus}
                  </span>
                </div>
              ))}
              {Object.keys(services).length === 0 && (
                <div className="rounded-lg bg-brand-midnight/60 px-3 py-6 text-center text-sm text-brand-muted">
                  No service telemetry available
                </div>
              )}
            </div>
          </section>

          <section>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-brand-muted/70">AI Models</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {Object.entries(models).map(([model, mdlStatus]) => (
                <div key={model} className="flex items-center justify-between rounded-lg bg-brand-midnight/70 px-3 py-2">
                  <div className="flex items-center gap-2 text-brand-ice">
                    <span>{badgeIcon(mdlStatus)}</span>
                    <span className="tracking-wide">{model}</span>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badgeTone(mdlStatus)}`}>
                    {mdlStatus}
                  </span>
                </div>
              ))}
              {Object.keys(models).length === 0 && (
                <div className="rounded-lg bg-brand-midnight/60 px-3 py-6 text-center text-sm text-brand-muted">
                  No model telemetry available
                </div>
              )}
            </div>
          </section>
        </div>

        <aside className="rounded-xl border border-brand-border/60 bg-brand-midnight/70 p-4">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-[0.2em] text-brand-muted/70">Data Backbone</h3>
          <div className="space-y-3">
            {infrastructureChecks.map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between">
                <span className="text-sm text-brand-muted">{label}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badgeTone(value)}`}>
                  {value ? 'Connected' : 'Offline'}
                </span>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
};

export default SystemStatus;
