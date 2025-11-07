import React, { useMemo } from 'react';

interface CrowdSentimentWidgetProps {
  totalVotes: number;
  bullishVotes: number;
  bearishVotes: number;
  hasVoted: boolean;
  onVote: (vote: 'bullish' | 'bearish') => void;
  onAuthenticate: () => void;
  isAuthenticated: boolean;
  onReset?: () => void;
  loading?: boolean;
}

const CrowdSentimentWidget: React.FC<CrowdSentimentWidgetProps> = ({
  totalVotes,
  bullishVotes,
  bearishVotes,
  hasVoted,
  onVote,
  onAuthenticate,
  isAuthenticated,
  onReset,
  loading = false,
}) => {
  const bullishPercentage = useMemo(() => {
    if (totalVotes === 0) return 0;
    return Math.round((bullishVotes / totalVotes) * 100);
  }, [totalVotes, bullishVotes]);

  const bearishPercentage = useMemo(() => {
    if (totalVotes === 0) return 0;
    return Math.round((bearishVotes / totalVotes) * 100);
  }, [totalVotes, bearishVotes]);

  return (
    <section className="relative overflow-hidden rounded-4xl border border-white/10 bg-surface-75/80 p-6 shadow-glass">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.14),_transparent_70%)]" />
      <div className="relative space-y-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-accent-ai">Crowd Signal</p>
            <h3 className="mt-2 text-2xl font-semibold text-white">Community Vibe Poll</h3>
            <p className="mt-2 text-sm text-slate-300">
              Add your take to Sapphire’s open science diary. Are markets feeling bullish or bearish today?
            </p>
          </div>
          {onReset && (
            <button
              onClick={onReset}
              className="rounded-full border border-white/15 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.3em] text-white/70 hover:bg-white/10"
            >
              Reset Votes
            </button>
          )}
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <button
            onClick={() => (isAuthenticated ? onVote('bullish') : onAuthenticate())}
            disabled={loading || (!isAuthenticated && hasVoted)}
            className="group rounded-3xl border border-emerald-400/40 bg-emerald-500/15 px-5 py-4 text-left shadow-glass transition-transform hover:-translate-y-1 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <div className="flex items-center gap-3">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-emerald-400/30 text-lg">🟢</span>
              <div>
                <h4 className="text-lg font-semibold text-white">Bullish</h4>
                <p className="text-sm text-slate-200/80">Expecting upside momentum and positive risk appetite.</p>
              </div>
            </div>
          </button>

          <button
            onClick={() => (isAuthenticated ? onVote('bearish') : onAuthenticate())}
            disabled={loading || (!isAuthenticated && hasVoted)}
            className="group rounded-3xl border border-red-400/40 bg-red-500/15 px-5 py-4 text-left shadow-glass transition-transform hover:-translate-y-1 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <div className="flex items-center gap-3">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-red-400/30 text-lg">🔴</span>
              <div>
                <h4 className="text-lg font-semibold text-white">Bearish</h4>
                <p className="text-sm text-slate-200/80">Expecting downside moves, risk-off posture, or hedging demand.</p>
              </div>
            </div>
          </button>
        </div>

        <div className="rounded-3xl border border-white/10 bg-black/20 px-5 py-4">
          <p className="text-xs uppercase tracking-[0.35em] text-slate-400">Community Breakdown</p>
          {hasVoted ? (
            <>
          <div className="mt-3 flex flex-col gap-3 text-sm text-slate-200">
            <div className="flex items-center justify-between">
              <span>Participants</span>
              <span className="text-white font-semibold">{totalVotes}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-emerald-300" />Bullish</span>
              <span className="text-white font-semibold">{bullishPercentage}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-red-300" />Bearish</span>
              <span className="text-white font-semibold">{bearishPercentage}%</span>
            </div>
          </div>

          <div className="mt-4 h-2 w-full rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400"
              style={{ width: `${bullishPercentage}%` }}
            />
          </div>
            </>
          ) : (
            <div className="mt-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
              <p className="font-medium text-white">Vote to unlock community consensus.</p>
              <p className="mt-1 text-xs text-slate-300/80">
                We protect privacy by sharing only anonymized aggregates. Cast your signal to see how the crowd is leaning.
              </p>
              {!isAuthenticated && (
                <button
                  onClick={onAuthenticate}
                  className="mt-3 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.28em] text-white transition hover:bg-white/20"
                >
                  Authenticate & Vote
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default CrowdSentimentWidget;

