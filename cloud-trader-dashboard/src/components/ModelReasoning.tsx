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
    if (confidence >= 0.8) return 'bg-green-100 text-green-800';
    if (confidence >= 0.6) return 'bg-yellow-100 text-yellow-800';
    return 'bg-red-100 text-red-800';
  };

  const getDecisionColor = (decision: string) => {
    switch (decision.toLowerCase()) {
      case 'buy':
        return 'bg-green-100 text-green-800';
      case 'sell':
        return 'bg-red-100 text-red-800';
      case 'hold':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-blue-100 text-blue-800';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-slate-900">AI Model Reasoning</h2>
        <div className="text-sm text-slate-500">
          {reasoning.length} recent decisions
        </div>
      </div>

      <div className="space-y-4 max-h-96 overflow-y-auto">
        {reasoning.map((entry, index) => (
          <div key={index} className="border border-slate-200 rounded-lg p-4 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center space-x-3">
                <span className="text-xl">{getModelIcon(entry.model_name)}</span>
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-medium text-slate-900">{entry.model_name}</span>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getDecisionColor(entry.decision)}`}>
                      {entry.decision.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-sm text-slate-500">
                    {entry.symbol} • {new Date(entry.timestamp).toLocaleString()}
                  </p>
                </div>
              </div>
              <div className={`px-3 py-1 rounded-full text-xs font-medium ${getConfidenceColor(entry.confidence)}`}>
                {(entry.confidence * 100).toFixed(1)}% confidence
              </div>
            </div>

            <div className="space-y-2">
              <div>
                <span className="text-sm font-medium text-slate-700">Reasoning:</span>
                <p className="text-sm text-slate-600 mt-1">{entry.reasoning}</p>
              </div>

              {entry.context && Object.keys(entry.context).length > 0 && (
                <div className="mt-3 pt-3 border-t border-slate-100">
                  <span className="text-sm font-medium text-slate-700">Context:</span>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                    {Object.entries(entry.context).slice(0, 4).map(([key, value]) => (
                      <div key={key} className="bg-slate-50 px-2 py-1 rounded">
                        <span className="font-medium text-slate-600">{key}:</span>
                        <span className="ml-1 text-slate-800">
                          {typeof value === 'number' ? value.toFixed(4) : String(value).slice(0, 20)}
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
        <div className="text-center py-12 text-slate-500">
          <span className="text-4xl mb-2 block">💭</span>
          <p>No reasoning data available yet</p>
          <p className="text-sm">Model reasoning will appear here as decisions are made</p>
        </div>
      )}
    </div>
  );
};

export default ModelReasoning;
