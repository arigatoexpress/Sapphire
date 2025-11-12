import { HealthResponse } from '../api/client';

interface StatusCardProps {
  health: HealthResponse | null;
  loading: boolean;
}

const StatusCard: React.FC<StatusCardProps> = ({ health, loading }) => {
  if (loading || !health) {
    return (
      <div
        className="sapphire-panel p-6 text-center text-brand-muted"
        role="status"
        aria-live="polite"
        aria-busy="true"
      >
        <span className="sr-only">Loading status...</span>
        <div className="animate-pulse space-y-3">
          <div className="mx-auto h-10 w-10 rounded-full bg-brand-border/60" />
          <p className="text-sm">Calibrating systems…</p>
        </div>
      </div>
    );
  }

  const statusBadge = health.running ? 'bg-accent-emerald/85 text-brand-midnight' : 'bg-warning-amber/85 text-brand-midnight';

  return (
    <div className="sapphire-panel p-6 text-brand-muted">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-brand-muted/80">System Status</p>
          <h3 className="mt-2 text-2xl font-semibold text-brand-ice">{health.running ? 'Operational' : 'Standby'}</h3>
          <p className="mt-2 text-sm text-brand-muted">
            {health.running
              ? 'Autonomous execution enabled · risk guardrails engaged'
              : 'Trader halted · awaiting operator command'}
          </p>
        </div>
        <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${statusBadge}`}>
          <span className="h-2 w-2 rounded-full bg-brand-midnight" />
          {health.running ? 'Live' : 'Paused'}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="relative overflow-hidden rounded-xl border border-brand-border/60 bg-brand-abyss/75 p-4 text-xs text-brand-muted shadow-sapphire">
          <p className="text-[0.65rem] uppercase tracking-[0.3em] text-brand-muted/70">Mode</p>
          <p className="mt-2 text-base font-medium text-brand-ice">{health.paper_trading ? 'Paper Trading' : 'Live Execution'}</p>
          <p className="mt-1">
            {health.paper_trading
              ? 'Synthetic orders for signal QA'
              : 'Orders routed to orchestrator'}
          </p>
        </div>

        <div className="relative overflow-hidden rounded-xl border border-brand-border/60 bg-brand-abyss/75 p-4 text-xs text-brand-muted shadow-sapphire">
          <p className="text-[0.65rem] uppercase tracking-[0.3em] text-brand-muted/70">Diagnostics</p>
          <p className="mt-2 text-base font-medium text-brand-ice">
            {health.last_error ? 'Attention Required' : 'Nominal'}
          </p>
          <p className="mt-1">
            {health.last_error ?? 'No critical alerts in the last hour.'}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-brand-muted/80">System Controls</h4>
        <p className="mt-1 text-xs text-brand-muted/70">
          Operator controls are disabled for public viewing to ensure system integrity.
        </p>
      </div>
    </div>
  );
};

export default StatusCard;

