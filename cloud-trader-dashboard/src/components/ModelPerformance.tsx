import React from 'react';

interface ModelMetrics {
  model_name: string;
  total_decisions: number;
  successful_trades: number;
  avg_confidence: number;
  avg_response_time: number;
  win_rate: number;
  total_pnl: number;
  last_decision: string | null;
}

interface ModelPerformanceProps {
  models: ModelMetrics[];
}

const ModelPerformance: React.FC<ModelPerformanceProps> = ({ models }) => {
  const getModelIcon = (modelName: string) => {
    const icons: { [key: string]: string } = {
      'DeepSeek-Coder-V2': '🧠',
      'Qwen2.5-Coder': '🧮',
      'FinGPT': '💰',
      'Phi-3': '🔬'
    };
    return icons[modelName] || '🤖';
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'text-emerald-300';
    if (confidence >= 0.6) return 'text-amber-200';
    return 'text-rose-300';
  };

  const getWinRateColor = (winRate: number) => {
    if (winRate >= 0.6) return 'text-emerald-300';
    if (winRate >= 0.4) return 'text-amber-200';
    return 'text-rose-300';
  };

  const getPerformanceBadge = (winRate: number, confidence: number) => {
    const score = (winRate * 0.7) + (confidence * 0.3);
    if (score >= 0.75) return { text: 'Elite', color: 'bg-emerald-500/20 text-emerald-200 border border-emerald-400/40' };
    if (score >= 0.6) return { text: 'Strong', color: 'bg-sky-500/20 text-sky-200 border border-sky-400/40' };
    if (score >= 0.45) return { text: 'Developing', color: 'bg-amber-500/20 text-amber-200 border border-amber-400/40' };
    return { text: 'Calibration Needed', color: 'bg-rose-500/20 text-rose-200 border border-rose-400/40' };
  };

  const getPnLColor = (pnl: number) => {
    return pnl >= 0 ? 'text-emerald-300' : 'text-rose-300';
  };

  return (
    <section className="relative overflow-hidden rounded-4xl border border-white/12 bg-surface-75/80 p-6 shadow-glass">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(45,212,191,0.18),_transparent_70%)]" />
      <div className="relative flex items-center justify-between mb-6">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-emerald-200/80">Model mesh telemetry</p>
          <h2 className="text-2xl font-semibold text-white">AI Model Performance</h2>
        </div>
        <div className="text-sm font-medium text-slate-200/80">
          {models.length} active
        </div>
      </div>

      <div className="relative grid grid-cols-1 md:grid-cols-2 gap-6">
        {models.map((model) => {
          const badge = getPerformanceBadge(model.win_rate, model.avg_confidence);
          const compositeScore = (model.win_rate * 0.7 + model.avg_confidence * 0.3) * 100;

          return (
            <div key={model.model_name} className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 p-5 backdrop-blur-sm transition-transform hover:-translate-y-0.5">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.16),_transparent_65%)]" />
              <div className="relative flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="text-2xl drop-shadow">{getModelIcon(model.model_name)}</span>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-semibold text-white">{model.model_name}</h3>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[0.65rem] uppercase tracking-[0.2em] ${badge.color}`}>
                        {badge.text}
                      </span>
                    </div>
                    <p className="text-xs text-slate-300/80">
                      Last active {model.last_decision ? new Date(model.last_decision).toLocaleTimeString() : '—'}
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-3">
                  <div>
                    <div className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Decisions</div>
                    <div className="mt-1 text-xl font-semibold text-white">{model.total_decisions}</div>
                  </div>
                  <div>
                    <div className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Avg Confidence</div>
                    <div className={`mt-1 text-xl font-semibold ${getConfidenceColor(model.avg_confidence)}`}>
                      {(model.avg_confidence * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Response Time</div>
                    <div className="mt-1 text-xl font-semibold text-slate-200">
                      {model.avg_response_time > 0 ? `${model.avg_response_time.toFixed(2)}s` : 'N/A'}
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <div>
                    <div className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Win Rate</div>
                    <div className={`mt-1 text-xl font-semibold ${getWinRateColor(model.win_rate)}`}>
                      {(model.win_rate * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Total P&L</div>
                    <div className={`mt-1 text-xl font-semibold ${getPnLColor(model.total_pnl)}`}>
                      {model.total_pnl >= 0 ? '+' : '-'}${Math.abs(model.total_pnl).toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[0.65rem] uppercase tracking-[0.28em] text-slate-400">Success Rate</div>
                    <div className="mt-1 text-xl font-semibold text-slate-200">
                      {model.total_decisions > 0 ? ((model.successful_trades / model.total_decisions) * 100).toFixed(1) : '0.0'}%
                    </div>
                  </div>
                </div>
              </div>

              <div className="relative mt-4 pt-4 border-t border-white/10">
                <div className="flex items-center justify-between text-sm text-slate-300">
                  <span>Composite Fidelity</span>
                  <span className="font-semibold text-white/90">
                    {compositeScore.toFixed(1)}%
                  </span>
                </div>
                <div className="mt-3 h-2 w-full rounded-full bg-white/10">
                  <div
                    className={`h-2 rounded-full ${
                      badge.text === 'Elite'
                        ? 'bg-emerald-400'
                        : badge.text === 'Strong'
                          ? 'bg-sky-400'
                          : badge.text === 'Developing'
                            ? 'bg-amber-400'
                            : 'bg-rose-400'
                    }`}
                    style={{ width: `${Math.min(compositeScore, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {models.length === 0 && (
        <div className="relative text-center py-10 text-slate-300">
          <span className="text-4xl mb-2 block">🤖</span>
          <p className="text-sm">Model telemetry will populate after the first live decisions.</p>
        </div>
      )}
    </section>
  );
};

export default ModelPerformance;
