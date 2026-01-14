import React, { useState, useEffect } from 'react';
import { Container, Grid, Paper, Typography, Box, Button, Chip } from '@mui/material';
import { Shield, Zap, ExternalLink } from 'lucide-react';
import { getApiUrl } from '../utils/apiConfig';

interface MITFund {
    name: string;
    symbol: string;
    total_assets: number;
    performance_fee: number;
    management_fee: number;
    strategy: string;
    active: boolean;
}

const MonadMIT: React.FC = () => {
    const [fund, setFund] = useState<MITFund | null>(null);
    const [loading, setLoading] = useState(true);

    const API_URL = getApiUrl();

    useEffect(() => {
        fetchMITStatus();
    }, []);

    const fetchMITStatus = async () => {
        try {
            const response = await fetch(`${API_URL}/api/symphony/status`);
            const data = await response.json();
            setFund(data);
        } catch (e) {
            console.error("MIT fetch failed", e);
        } finally {
            setLoading(false);
        }
    };

    return (
        <Container maxWidth="lg" className="py-12">
            <Box className="flex justify-between items-center mb-10">
                <div>
                    <Typography variant="h3" className="font-bold text-white mb-2">
                        Monad MIT
                    </Typography>
                    <Typography variant="subtitle1" className="text-slate-400">
                        Symphony-powered managed investment tokens
                    </Typography>
                </div>
                <Button variant="contained" color="primary" startIcon={<ExternalLink size={18} />}>
                    Connect Wallet
                </Button>
            </Box>

            <Grid container spacing={4}>
                <Grid item xs={12} md={8}>
                    <Paper className="p-8 bg-slate-800/40 border border-slate-700 backdrop-blur-xl rounded-2xl">
                        <Box className="flex justify-between items-start mb-6">
                            <Box className="flex items-center space-x-4">
                                <div className="p-4 bg-indigo-500/20 rounded-2xl">
                                    <Shield className="text-indigo-400" size={32} />
                                </div>
                                <div>
                                    <Typography variant="h5" className="text-white font-bold">
                                        Sapphire Alpha Fund
                                    </Typography>
                                    <Typography variant="body2" className="text-slate-500 font-mono">
                                        sALP-v1
                                    </Typography>
                                </div>
                            </Box>
                            <Chip label="LIVE" color="success" size="small" />
                        </Box>

                        <Typography className="text-slate-300 mb-8 leading-relaxed">
                            The Sapphire Alpha Fund utilizes the Aster Analysis Engine to rotate capital between high-conviction
                            narratives across Monad and Solana. Managed by Symphony, sALP offers institutional-grade
                            risk management with autonomous execution.
                        </Typography>

                        <Grid container spacing={2}>
                            {[
                                { label: 'Min. TVL', value: '$1.2M' },
                                { label: 'Perf. Fee', value: '15%' },
                                { label: 'Mgt. Fee', value: '1%' },
                                { label: 'Settlement', value: 'Daily' },
                            ].map((stat, i) => (
                                <Grid item xs={6} sm={3} key={i}>
                                    <Box className="p-4 bg-slate-900/50 rounded-xl border border-slate-800">
                                        <Typography variant="caption" className="text-slate-500 block mb-1">
                                            {stat.label}
                                        </Typography>
                                        <Typography className="text-white font-bold font-mono">
                                            {stat.value}
                                        </Typography>
                                    </Box>
                                </Grid>
                            ))}
                        </Grid>
                    </Paper>
                </Grid>

                <Grid item xs={12} md={4}>
                    <Paper className="p-6 bg-slate-800/40 border border-slate-700 backdrop-blur-xl rounded-2xl h-full">
                        <Typography variant="h6" className="text-white font-bold mb-6 flex items-center gap-2">
                            <Zap size={20} className="text-yellow-400" /> Performance
                        </Typography>

                        <Box className="space-y-6">
                            <Box className="text-center p-8 bg-slate-900/60 rounded-2xl border border-slate-800">
                                <Typography variant="h3" className="text-green-400 font-mono font-bold mb-1">
                                    +24.8%
                                </Typography>
                                <Typography variant="body2" className="text-slate-500 uppercase tracking-widest">
                                    Last 30 Days
                                </Typography>
                            </Box>

                            <Box className="space-y-4">
                                <Typography variant="subtitle2" className="text-slate-400 font-bold uppercase text-xs">
                                    Fund Composition
                                </Typography>
                                <div className="space-y-2">
                                    <div className="flex justify-between text-sm">
                                        <span className="text-slate-400">Stablecoins</span>
                                        <span className="text-white font-mono">42%</span>
                                    </div>
                                    <div className="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden">
                                        <div className="bg-indigo-500 h-full" style={{ width: '42%' }}></div>
                                    </div>
                                </div>
                            </Box>
                        </Box>
                    </Paper>
                </Grid>
            </Grid>
        </Container>
    );
};

export default MonadMIT;
