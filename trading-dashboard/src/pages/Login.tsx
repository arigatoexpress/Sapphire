import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Box, Container, Paper, TextField, Button, Typography, Alert, Tabs, Tab } from '@mui/material';

const Login = () => {
    const [tab, setTab] = useState(0);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [loading, setLoading] = useState(false);

    const { signIn, signUp, resetPassword, enterAsGuest } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setSuccess('');
        setLoading(true);

        try {
            if (tab === 0) {
                // Sign in
                await signIn(email, password);
                navigate('/');
            } else if (tab === 1) {
                // Sign up
                await signUp(email, password);
                navigate('/');
            } else {
                // Reset password
                await resetPassword(email);
                setSuccess('Password reset email sent!');
            }
        } catch (err: any) {
            setError(err.message || 'Authentication failed');
        } finally {
            setLoading(false);
        }
    };

    const handleGuestLogin = async () => {
        setLoading(true);
        try {
            await enterAsGuest();
            navigate('/');
        } catch (err: any) {
            setError(err.message || 'Guest login failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Box sx={{
            minHeight: '100vh',
            bgcolor: '#050505',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'radial-gradient(circle at 50% 0%, #1a1a2e 0%, #050505 100%)'
        }}>
            <Container maxWidth="sm">
                <Paper sx={{
                    p: 4,
                    bgcolor: '#0a0b10',
                    borderRadius: 2,
                    border: '1px solid #222'
                }}>
                    <Box sx={{ textAlign: 'center', mb: 4 }}>
                        <Typography variant="h4" sx={{ fontWeight: 800, color: '#fff', mb: 1 }}>
                            💎 SAPPHIRE <span style={{ color: '#00d4aa' }}>AI</span>
                        </Typography>
                        <Typography variant="body2" sx={{ color: '#666' }}>
                            Social Trading & AI Predictions
                        </Typography>
                    </Box>

                    <Tabs
                        value={tab}
                        onChange={(_, v) => setTab(v)}
                        sx={{ mb: 3 }}
                        variant="fullWidth"
                    >
                        <Tab label="Sign In" />
                        <Tab label="Sign Up" />
                        <Tab label="Reset Password" />
                    </Tabs>

                    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
                    {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

                    <form onSubmit={handleSubmit}>
                        <TextField
                            fullWidth
                            label="Email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            sx={{
                                mb: 2,
                                '& .MuiInputBase-input': { color: '#fff' },
                                '& .MuiInputLabel-root': { color: '#999' },
                                '& .MuiInputLabel-root.Mui-focused': { color: '#00d4aa' },
                                '& .MuiOutlinedInput-root': {
                                    '& fieldset': { borderColor: '#444' },
                                    '&:hover fieldset': { borderColor: '#666' },
                                    '&.Mui-focused fieldset': { borderColor: '#00d4aa' }
                                }
                            }}
                            required
                        />

                        {tab !== 2 && (
                            <TextField
                                fullWidth
                                label="Password"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                sx={{
                                    mb: 3,
                                    '& .MuiInputBase-input': { color: '#fff' },
                                    '& .MuiInputLabel-root': { color: '#999' },
                                    '& .MuiInputLabel-root.Mui-focused': { color: '#00d4aa' },
                                    '& .MuiOutlinedInput-root': {
                                        '& fieldset': { borderColor: '#444' },
                                        '&:hover fieldset': { borderColor: '#666' },
                                        '&.Mui-focused fieldset': { borderColor: '#00d4aa' }
                                    }
                                }}
                                required
                            />
                        )}

                        <Button
                            fullWidth
                            type="submit"
                            variant="contained"
                            disabled={loading}
                            sx={{
                                bgcolor: '#00d4aa',
                                '&:hover': { bgcolor: '#00b894' },
                                py: 1.5,
                                fontWeight: 700
                            }}
                        >
                            {loading ? 'Processing...' :
                                tab === 0 ? 'Sign In' :
                                    tab === 1 ? 'Create Account' :
                                        'Send Reset Email'}
                        </Button>
                    </form>

                    <Box sx={{ mt: 3, pt: 3, borderTop: '1px solid #222', textAlign: 'center' }}>
                        <Button
                            onClick={handleGuestLogin}
                            disabled={loading}
                            sx={{
                                color: '#666',
                                textTransform: 'none',
                                '&:hover': { color: '#fff', bgcolor: 'transparent' }
                            }}
                        >
                            Continue as Guest (No Sign Up)
                        </Button>
                    </Box>

                    {tab === 0 && (
                        <Typography variant="caption" sx={{ color: '#666', display: 'block', mt: 2, textAlign: 'center' }}>
                            Don't have an account? Switch to "Sign Up"
                        </Typography>
                    )}
                </Paper>
            </Container>
        </Box>
    );
};

export default Login;
