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
    if (confidence >= 0.8) return 'text-green-600';
    if (confidence >= 0.6) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getWinRateColor = (winRate: number) => {
    if (winRate >= 0.6) return 'text-green-600';
    if (winRate >= 0.4) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getPerformanceBadge = (winRate: number, confidence: number) => {
    const score = (winRate * 0.7) + (confidence * 0.3);
    if (score >= 0.75) return { text: 'Excellent', color: 'bg-green-100 text-green-800' };
    if (score >= 0.6) return { text: 'Good', color: 'bg-blue-100 text-blue-800' };
    if (score >= 0.45) return { text: 'Fair', color: 'bg-yellow-100 text-yellow-800' };
    return { text: 'Needs Improvement', color: 'bg-red-100 text-red-800' };
  };

  const getPnLColor = (pnl: number) => {
    return pnl >= 0 ? 'text-green-600' : 'text-red-600';
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-slate-900">AI Model Performance</h2>
        <div className="text-sm text-slate-500">
          {models.length} models active
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {models.map((model) => (
          <div key={model.model_name} className="border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-3">
                <span className="text-2xl">{getModelIcon(model.model_name)}</span>
                <div>
                  <div className="flex items-center space-x-2">
                    <h3 className="font-medium text-slate-900">{model.model_name}</h3>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPerformanceBadge(model.win_rate, model.avg_confidence).color}`}>
                      {getPerformanceBadge(model.win_rate, model.avg_confidence).text}
                    </span>
                  </div>
                  <p className="text-sm text-slate-500">
                    Last active: {model.last_decision ? new Date(model.last_decision).toLocaleTimeString() : 'Never'}
                  </p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-3">
                <div>
                  <div className="text-xs text-slate-500 uppercase tracking-wide">Decisions</div>
                  <div className="text-lg font-semibold text-slate-900">{model.total_decisions}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 uppercase tracking-wide">Avg Confidence</div>
                  <div className={`text-lg font-semibold ${getConfidenceColor(model.avg_confidence)}`}>
                    {(model.avg_confidence * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 uppercase tracking-wide">Response Time</div>
                  <div className="text-lg font-semibold text-slate-900">
                    {model.avg_response_time > 0 ? `${model.avg_response_time.toFixed(2)}s` : 'N/A'}
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <div className="text-xs text-slate-500 uppercase tracking-wide">Win Rate</div>
                  <div className={`text-lg font-semibold ${getWinRateColor(model.win_rate)}`}>
                    {(model.win_rate * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 uppercase tracking-wide">Total P&L</div>
                  <div className={`text-lg font-semibold ${getPnLColor(model.total_pnl)}`}>
                    ${model.total_pnl.toFixed(2)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500 uppercase tracking-wide">Success Rate</div>
                  <div className="text-lg font-semibold text-slate-900">
                    {model.total_decisions > 0 ? ((model.successful_trades / model.total_decisions) * 100).toFixed(1) : '0.0'}%
                  </div>
                </div>
              </div>
            </div>

            {/* Performance indicator */}
            <div className="mt-4 pt-4 border-t border-slate-100">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">Overall Score</span>
                  <span className="text-sm font-medium text-slate-700">
                    {((model.win_rate * 0.7 + model.avg_confidence * 0.3) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${
                      getPerformanceBadge(model.win_rate, model.avg_confidence).text === 'Excellent' ? 'bg-green-500' :
                      getPerformanceBadge(model.win_rate, model.avg_confidence).text === 'Good' ? 'bg-blue-500' :
                      getPerformanceBadge(model.win_rate, model.avg_confidence).text === 'Fair' ? 'bg-yellow-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${Math.min((model.win_rate * 0.7 + model.avg_confidence * 0.3) * 100, 100)}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {models.length === 0 && (
        <div className="text-center py-8 text-slate-500">
          <span className="text-4xl mb-2 block">🤖</span>
          <p>No model performance data available yet</p>
          <p className="text-sm">Models will appear here once they start making trading decisions</p>
        </div>
      )}
    </div>
  );
};

export default ModelPerformance;
