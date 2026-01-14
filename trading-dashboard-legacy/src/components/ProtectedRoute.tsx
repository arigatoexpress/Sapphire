import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Box, CircularProgress } from '@mui/material';

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <Box sx={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                minHeight: '100vh',
                bgcolor: '#050505'
            }}>
                <CircularProgress sx={{ color: '#00d4aa' }} />
            </Box>
        );
    }

    return user ? <>{children}</> : <Navigate to="/login" />;
};

export default ProtectedRoute;
