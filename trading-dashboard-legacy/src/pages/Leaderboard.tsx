import { useState, useEffect } from 'react';
import { Box, Container, Typography, Tabs, Tab, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material';
import { Trophy, TrendingUp, Target, Flame } from 'lucide-react';

const Leaderboard = () => {
    const [tab, setTab] = useState(0);
    const [leaderboard, setLeaderboard] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const tabs = ['all', 'monthly', 'accuracy', 'streaks'];

    useEffect(() => {
        const fetchLeaderboard = async () => {
            setLoading(true);
            try {
                const response = await fetch(`/api/leaderboard?timeframe=${tabs[tab]}`);
                const data = await response.json();
                setLeaderboard(data);
            } catch (error) {
                console.error('Failed to fetch leaderboard:', error);
            } finally {
                setLoading(false);
            }
        };

        fetchLeaderboard();
    }, [tab]);

    const getRankIcon = (rank: number) => {
        if (rank === 1) return '🥇';
        if (rank === 2) return '🥈';
        if (rank === 3) return '🥉';
        return rank;
    };

    return (
        <Box sx={{ minHeight: '100vh', bgcolor: '#050505', color: '#fff', py: 4 }}>
            <Container maxWidth="lg">
                <Box sx={{ textAlign: 'center', mb: 4 }}>
                    <Trophy size={48} color="#ffd700" style={{ marginBottom: 16 }} />
                    <Typography variant="h3" sx={{ fontWeight: 800, color: '#fff', mb: 1 }}>
                        LEADERBOARD
                    </Typography>
                    <Typography variant="body1" sx={{ color: '#666' }}>
                        Compete with the best traders and earn rewards
                    </Typography>
                </Box>

                <Paper sx={{ bgcolor: '#0a0b10', borderRadius: 2, border: '1px solid #222' }}>
                    <Tabs
                        value={tab}
                        onChange={(_, v) => setTab(v)}
                        variant="fullWidth"
                        sx={{
                            borderBottom: '1px solid #222',
                            '& .MuiTab-root': { color: '#666' },
                            '& .Mui-selected': { color: '#00d4aa' }
                        }}
                    >
                        <Tab
                            icon={<Trophy size={18} />}
                            iconPosition="start"
                            label="All-Time"
                        />
                        <Tab
                            icon={<TrendingUp size={18} />}
                            iconPosition="start"
                            label="This Month"
                        />
                        <Tab
                            icon={<Target size={18} />}
                            iconPosition="start"
                            label="Accuracy"
                        />
                        <Tab
                            icon={<Flame size={18} />}
                            iconPosition="start"
                            label="Streaks"
                        />
                    </Tabs>

                    <TableContainer>
                        <Table>
                            <TableHead>
                                <TableRow sx={{ bgcolor: '#0f1016' }}>
                                    <TableCell sx={{ color: '#666', fontWeight: 700 }}>Rank</TableCell>
                                    <TableCell sx={{ color: '#666', fontWeight: 700 }}>User</TableCell>
                                    {tab === 0 && <TableCell align="right" sx={{ color: '#666', fontWeight: 700 }}>Total Points</TableCell>}
                                    {tab === 1 && <TableCell align="right" sx={{ color: '#666', fontWeight: 700 }}>Monthly Points</TableCell>}
                                    {tab === 2 && (
                                        <>
                                            <TableCell align="right" sx={{ color: '#666', fontWeight: 700 }}>Accuracy</TableCell>
                                            <TableCell align="right" sx={{ color: '#666', fontWeight: 700 }}>Votes</TableCell>
                                        </>
                                    )}
                                    {tab === 3 && <TableCell align="right" sx={{ color: '#666', fontWeight: 700 }}>Streak Days</TableCell>}
                                    <TableCell align="right" sx={{ color: '#666', fontWeight: 700 }}>Streak</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {loading ? (
                                    <TableRow>
                                        <TableCell colSpan={4} align="center" sx={{ color: '#666', py: 4 }}>
                                            Loading...
                                        </TableCell>
                                    </TableRow>
                                ) : leaderboard.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={4} align="center" sx={{ color: '#666', py: 4 }}>
                                            No data yet
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    leaderboard.map((user, idx) => (
                                        <TableRow
                                            key={idx}
                                            sx={{
                                                '&:hover': { bgcolor: '#ffffff05' },
                                                bgcolor: user.rank <= 3 ? '#ffd70010' : 'transparent'
                                            }}
                                        >
                                            <TableCell sx={{ color: '#fff', fontSize: '1.2rem', fontWeight: 700 }}>
                                                {getRankIcon(user.rank)}
                                            </TableCell>
                                            <TableCell sx={{ color: '#fff' }}>
                                                {user.email?.split('@')[0] || 'Anonymous'}
                                            </TableCell>
                                            {tab === 0 && (
                                                <TableCell align="right" sx={{ color: '#ffd700', fontWeight: 700 }}>
                                                    {user.total_points}
                                                </TableCell>
                                            )}
                                            {tab === 1 && (
                                                <TableCell align="right" sx={{ color: '#00d4aa', fontWeight: 700 }}>
                                                    {user.monthly_points}
                                                </TableCell>
                                            )}
                                            {tab === 2 && (
                                                <>
                                                    <TableCell align="right" sx={{ color: '#00d4aa', fontWeight: 700 }}>
                                                        {user.accuracy.toFixed(1)}%
                                                    </TableCell>
                                                    <TableCell align="right" sx={{ color: '#666' }}>
                                                        {user.total_votes}
                                                    </TableCell>
                                                </>
                                            )}
                                            {tab === 3 && (
                                                <TableCell align="right" sx={{ color: '#ff6b6b', fontWeight: 700 }}>
                                                    {user.streak_days} 🔥
                                                </TableCell>
                                            )}
                                            <TableCell align="right" sx={{ color: '#666' }}>
                                                {user.streak_days >= 7 ? '🔥' : '-'}
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </TableContainer>
                </Paper>

                <Box sx={{ textAlign: 'center', mt: 4, p: 3, bgcolor: '#0a0b10', borderRadius: 2, border: '1px solid #222' }}>
                    <Typography variant="h6" sx={{ fontWeight: 700, color: '#00d4aa', mb: 2 }}>
                        How to Earn Points
                    </Typography>
                    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 2 }}>
                        <Box>
                            <Typography variant="body2" sx={{ color: '#666' }}>Daily Check-in</Typography>
                            <Typography variant="h6" sx={{ color: '#ffd700', fontWeight: 700 }}>+10 pts</Typography>
                        </Box>
                        <Box>
                            <Typography variant="body2" sx={{ color: '#666' }}>Submit Prediction</Typography>
                            <Typography variant="h6" sx={{ color: '#00d4aa', fontWeight: 700 }}>+5 pts</Typography>
                        </Box>
                        <Box>
                            <Typography variant="body2" sx={{ color: '#666' }}>Correct Prediction</Typography>
                            <Typography variant="h6" sx={{ color: '#ff6b6b', fontWeight: 700 }}>+50 pts</Typography>
                        </Box>
                    </Box>
                    <Typography variant="caption" sx={{ color: '#666', mt: 2, display: 'block' }}>
                        High confidence correct predictions (+80%) earn +100 points!
                    </Typography>
                </Box>
            </Container>
        </Box>
    );
};

export default Leaderboard;
