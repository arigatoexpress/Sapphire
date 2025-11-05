import React from 'react';

interface ReasoningEntry {
  model_name: string;
  decision: string;
  reasoning: string;
  confidence: number;
  context: any;
  timestamp: string;
  symbol: string;
}

interface ModelReasoningProps {
  reasoning: ReasoningEntry[];
}

const ModelReasoning: React.FC<ModelReasoningProps> = ({ reasoning }) => {
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
    if (confidence >= 0.8) return 'bg-emerald-500/20 text-emerald-200 border border-emerald-400/40';
    if (confidence >= 0.6) return 'bg-amber-500/20 text-amber-200 border border-amber-400/40';
    return 'bg-rose-500/20 text-rose-200 border border-rose-400/40';
  };

  const getDecisionColor = (decision: string) => {
    switch (decision.toLowerCase()) {
      case 'buy':
        return 'bg-emerald-500/20 text-emerald-200 border border-emerald-400/40';
      case 'sell':
        return 'bg-rose-500/20 text-rose-200 border border-rose-400/40';
      case 'hold':
        return 'bg-slate-500/20 text-slate-200 border border-slate-400/40';
      default:
        return 'bg-sky-500/20 text-sky-200 border border-sky-400/40';
    }
  };

  return (
    <section className="relative overflow-hidden rounded-4xl border border-white/12 bg-surface-75/80 p-6 shadow-glass">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_bottom,_rgba(168,85,247,0.18),_transparent_70%)]" />
      <div className="relative flex items-center justify-between mb-6">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-purple-200/80">Reasoning trace</p>
          <h2 className="text-2xl font-semibold text-white">AI Model Reasoning</h2>
        </div>
        <div className="text-sm font-medium text-slate-200/80">
          {reasoning.length} recent decisions
        </div>
      </div>

      <div className="relative space-y-4 max-h-[28rem] overflow-y-auto pr-1">
        {reasoning.map((entry, index) => (
          <div key={index} className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.14),_transparent_70%)]" />
            <div className="relative flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <span className="text-xl drop-shadow">{getModelIcon(entry.model_name)}</span>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">{entry.model_name}</span>
                    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[0.65rem] uppercase tracking-[0.2em] ${getDecisionColor(entry.decision)}`}>
                      {entry.decision.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-xs text-slate-300/80">
                    {entry.symbol} • {new Date(entry.timestamp).toLocaleString()}
                  </p>
                </div>
              </div>
              <div className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-[0.65rem] font-medium uppercase tracking-[0.2em] ${getConfidenceColor(entry.confidence)}`}>
                {(entry.confidence * 100).toFixed(1)}% Conf.
              </div>
            </div>

            <div className="relative space-y-3 text-sm">
              <div>
                <span className="text-xs uppercase tracking-[0.28em] text-slate-400">Reasoning</span>
                <p className="mt-2 text-slate-200 leading-relaxed">{entry.reasoning}</p>
              </div>

              {entry.context && Object.keys(entry.context).length > 0 && (
                <div className="relative mt-3 pt-3 border-t border-white/10">
                  <span className="text-xs uppercase tracking-[0.28em] text-slate-400">Context</span>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-200">
                    {Object.entries(entry.context).slice(0, 4).map(([key, value]) => (
                      <div key={key} className="rounded-lg border border-white/10 bg-white/5 px-2 py-1">
                        <span className="font-semibold text-slate-100">{key}:</span>
                        <span className="ml-1 text-slate-200/90">
                          {typeof value === 'number' ? value.toFixed(4) : String(value).slice(0, 24)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {reasoning.length === 0 && (
        <div className="relative text-center py-12 text-slate-300">
          <span className="text-4xl mb-2 block">💭</span>
          <p className="text-sm">Reasoning transcripts will appear after the next model decision.</p>
        </div>
      )}
    </section>
  );
};

export default ModelReasoning;
