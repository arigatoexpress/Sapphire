import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { TrendingUp, TrendingDown, Minus, AlertCircle, CheckCircle } from 'lucide-react';

interface DailyVoteCardProps {
    symbol: string;
}

const DailyVoteCard = ({ symbol }: DailyVoteCardProps) => {
    const [prediction, setPrediction] = useState<'bullish' | 'bearish' | 'neutral'>('neutral');
    const [confidence, setConfidence] = useState(50);
    const [submitting, setSubmitting] = useState(false);
    const [result, setResult] = useState<{ success?: boolean; error?: string; message?: string } | null>(null);
    const { user } = useAuth();

    const handleSubmit = async () => {
        if (!user) return;

        setSubmitting(true);
        setResult(null);

        try {
            const response = await fetch('/api/vote', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${await user.getIdToken()}`
                },
                body: JSON.stringify({
                    symbol,
                    prediction,
                    confidence: confidence / 100
                })
            });

            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Failed to submit vote');
            setResult({ success: true, message: `Vote recorded! +${data.points_awarded || 5} pts` });
        } catch (error: any) {
            setResult({ error: error.message });
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-[#0a0b10] border border-white/10 rounded-2xl p-4 relative overflow-hidden">
            {/* Header */}
            <div className="flex justify-between items-center mb-4">
                <h3 className="text-white font-bold text-lg">Daily Prediction</h3>
                <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded">
                    +5 PTS
                </span>
            </div>

            {/* Prediction Buttons */}
            <div className="grid grid-cols-3 gap-2 mb-4">
                <button
                    onClick={() => setPrediction('bullish')}
                    className={`flex flex-col items-center justify-center p-2 rounded-xl border transition-all ${prediction === 'bullish'
                        ? 'bg-emerald-500/20 border-emerald-500 text-emerald-400'
                        : 'bg-white/5 border-white/5 text-slate-400 hover:bg-white/10'
                        }`}
                >
                    <TrendingUp size={20} className="mb-1" />
                    <span className="text-xs font-bold">Bullish</span>
                </button>
                <button
                    onClick={() => setPrediction('neutral')}
                    className={`flex flex-col items-center justify-center p-2 rounded-xl border transition-all ${prediction === 'neutral'
                        ? 'bg-amber-500/20 border-amber-500 text-amber-400'
                        : 'bg-white/5 border-white/5 text-slate-400 hover:bg-white/10'
                        }`}
                >
                    <Minus size={20} className="mb-1" />
                    <span className="text-xs font-bold">Neutral</span>
                </button>
                <button
                    onClick={() => setPrediction('bearish')}
                    className={`flex flex-col items-center justify-center p-2 rounded-xl border transition-all ${prediction === 'bearish'
                        ? 'bg-rose-500/20 border-rose-500 text-rose-400'
                        : 'bg-white/5 border-white/5 text-slate-400 hover:bg-white/10'
                        }`}
                >
                    <TrendingDown size={20} className="mb-1" />
                    <span className="text-xs font-bold">Bearish</span>
                </button>
            </div>

            {/* Confidence Slider */}
            <div className="mb-4">
                <div className="flex justify-between text-xs text-slate-400 mb-2">
                    <span>Confidence</span>
                    <span className="text-white font-mono">{confidence}%</span>
                </div>
                <input
                    type="range"
                    min="0"
                    max="100"
                    value={confidence}
                    onChange={(e) => setConfidence(parseInt(e.target.value))}
                    className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-blue-500 hover:accent-blue-400"
                />
            </div>

            {/* Submit Button & Messages */}
            <div className="mt-auto">
                {result && (
                    <div className={`mb-3 p-2 rounded text-xs flex items-center gap-2 ${result.success ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                        }`}>
                        {result.success ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
                        {result.message || result.error}
                    </div>
                )}

                <button
                    onClick={handleSubmit}
                    disabled={submitting || !user}
                    className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-bold rounded-xl transition-colors flex items-center justify-center gap-2"
                >
                    {submitting ? 'Submitting...' : user ? 'Submit Prediction' : 'Login to Vote'}
                </button>

                {!user && (
                    <p className="text-[10px] text-center mt-2 text-slate-500">
                        Sign in to earn points
                    </p>
                )}
            </div>

        </div>
    );
};

export default DailyVoteCard;
