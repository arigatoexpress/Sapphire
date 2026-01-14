import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { TrendingUp, Award, Flame, Trophy } from 'lucide-react';

const PointsWidget = () => {
    const [stats, setStats] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const { user } = useAuth();

    useEffect(() => {
        if (!user) {
            setLoading(false);
            return;
        }

        const fetchStats = async () => {
            try {
                const response = await fetch(`/api/user/stats?uid=${user.uid}`, {
                    headers: { 'Authorization': `Bearer ${await user.getIdToken()}` }
                });
                const data = await response.json();
                setStats(data);
            } catch (error) {
                console.error('Failed to fetch user stats:', error);
            } finally {
                setLoading(false);
            }
        };

        fetchStats();
        const interval = setInterval(fetchStats, 30000); // Refresh every 30s

        return () => clearInterval(interval);
    }, [user]);

    if (!user) return null;

    if (loading) {
        return (
            <div className="flex items-center gap-4 px-4 py-2 bg-[#0a0b10] border border-white/10 rounded-xl animate-pulse">
                <div className="h-4 w-20 bg-white/10 rounded"></div>
            </div>
        );
    }

    if (!stats) return null;

    return (
        <div className="flex items-center gap-6 px-4 py-2 bg-[#0a0b10] border border-white/10 rounded-xl shadow-lg">
            {/* User Rank */}
            <div className="flex items-center gap-2">
                <div className="bg-emerald-500/10 p-1.5 rounded-lg">
                    <Trophy size={16} className="text-emerald-400" />
                </div>
                <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Rank</span>
                    <span className="text-sm font-bold text-emerald-400 font-mono">#{stats.rank ?? 0}</span>
                </div>
            </div>

            {/* Separator */}
            <div className="h-6 w-px bg-white/10"></div>

            {/* Total Points */}
            <div className="flex items-center gap-2">
                <div className="bg-amber-500/10 p-1.5 rounded-lg">
                    <Award size={16} className="text-amber-400" />
                </div>
                <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Points</span>
                    <span className="text-sm font-bold text-amber-400 font-mono">{(stats.total_points ?? 0).toLocaleString()}</span>
                </div>
            </div>

            {/* Separator */}
            <div className="h-6 w-px bg-white/10"></div>

            {/* Streak */}
            <div className="flex items-center gap-2">
                <div className="bg-rose-500/10 p-1.5 rounded-lg">
                    <Flame size={16} className="text-rose-400" />
                </div>
                <div>
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Streak</span>
                    <span className="text-sm font-bold text-rose-400 font-mono">{stats.streak_days ?? 0} Days</span>
                </div>
            </div>

            {/* Accuracy Badge */}
            {(stats.accuracy ?? 0) > 0 && (
                <>
                    <div className="h-6 w-px bg-white/10"></div>
                    <div className="flex items-center gap-1.5 bg-blue-500/10 px-2 py-1 rounded-lg border border-blue-500/20">
                        <TrendingUp size={12} className="text-blue-400" />
                        <span className="text-xs font-bold text-blue-400">{(stats.accuracy ?? 0).toFixed(0)}% Acc</span>
                    </div>
                </>
            )}

            {/* Badges (Hidden on mobile usually, keeping simple) */}
            {stats.rank <= 10 && (
                <span className="text-[10px] bg-yellow-500/20 text-yellow-500 px-1.5 py-0.5 rounded border border-yellow-500/30">
                    TOP 10
                </span>
            )}
        </div>
    );
};

export default PointsWidget;
