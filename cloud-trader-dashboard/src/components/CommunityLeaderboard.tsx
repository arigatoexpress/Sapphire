import React from 'react';
import type { LeaderboardEntry } from '../services/community';

interface CommunityLeaderboardProps {
  entries: LeaderboardEntry[];
  loading?: boolean;
}

const tierColors = ['bg-brand-accent-blue/20', 'bg-brand-accent-purple/20', 'bg-brand-accent-green/20'];

const CommunityLeaderboard: React.FC<CommunityLeaderboardProps> = ({ entries, loading = false }) => {
  return (
    <section className="relative overflow-hidden rounded-4xl border border-white/10 bg-brand-abyss/80 p-6 shadow-sapphire-lg">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.18),_transparent_70%)]" />
      <div className="relative space-y-6">
        <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-brand-ice/70">Community Hall</p>
            <h3 className="mt-2 text-2xl font-semibold text-white">Top Sapphire Contributors</h3>
            <p className="mt-2 text-sm text-brand-ice/80">
              Points accrue for daily check-ins, insightful comments, and sentiment votes. Bots can reference this leaderboard for credible crowd signals without over-weighting them.
            </p>
          </div>
        </header>

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, index) => (
              <div
                key={`leaderboard-skeleton-${index}`}
                className="h-16 animate-pulse rounded-3xl border border-white/10 bg-white/5"
              />
            ))}
          </div>
        ) : entries.length === 0 ? (
          <div className="rounded-3xl border border-white/10 bg-white/5 px-5 py-6 text-center text-sm text-brand-ice/70">
            Crowd pilots are just getting started. Check in, vote, and leave feedback to climb the leaderboard.
          </div>
        ) : (
          <ul className="space-y-3">
            {entries.map((entry, index) => {
              const tierColor = tierColors[index] ?? 'bg-white/5';
              return (
                <li
                  key={entry.publicId}
                  className={`relative overflow-hidden rounded-3xl border border-white/10 px-5 py-4 shadow-sapphire ${tierColor}`}
                >
                  <div className="relative flex items-center gap-4">
                    <div className="flex h-12 w-12 flex-none items-center justify-center rounded-full bg-black/30 text-lg font-semibold text-white">
                      #{index + 1}
                    </div>
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <p className="text-sm font-semibold text-white">{entry.displayName}</p>
                          <p className="text-xs text-brand-ice/60">{entry.publicId}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-lg font-semibold text-brand-accent-green">{(entry.points ?? entry.score).toLocaleString()} pts</p>
                          {entry.lastActive && (
                            <p className="text-xs text-brand-ice/60">Active {new Date(entry.lastActive).toLocaleDateString()}</p>
                          )}
                        </div>
                      </div>

                      <div className="mt-3 grid grid-cols-3 gap-3 text-xs text-brand-ice/70">
                        <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-center">
                          <p className="font-semibold text-white">{entry.checkIns ?? 0}</p>
                          <p>Check-ins</p>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-center">
                          <p className="font-semibold text-white">{entry.votes ?? 0}</p>
                          <p>Votes</p>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-center">
                          <p className="font-semibold text-white">{entry.comments ?? 0}</p>
                          <p>Comments</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
};

export default CommunityLeaderboard;

