import React from 'react';
import { Box, Skeleton, Grid, Card, CardContent } from '@mui/material';

interface LoadingSkeletonProps {
  type: 'dashboard' | 'chart' | 'table' | 'card';
  count?: number;
}

const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({ type, count = 1 }) => {
  const renderSkeleton = () => {
    switch (type) {
      case 'dashboard':
        return (
          <Box sx={{ p: 3 }}>
            <Grid container spacing={3}>
              {/* Header skeleton */}
              <Grid item xs={12}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                  <Skeleton variant="text" width={300} height={40} />
                  <Skeleton variant="rectangular" width={120} height={36} />
                </Box>
              </Grid>

              {/* Metric cards skeleton */}
              <Grid item xs={12} md={3}>
                <Card>
                  <CardContent>
                    <Skeleton variant="text" width="60%" height={24} />
                    <Skeleton variant="text" width="40%" height={32} sx={{ mt: 1 }} />
                    <Skeleton variant="text" width="30%" height={16} sx={{ mt: 1 }} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={3}>
                <Card>
                  <CardContent>
                    <Skeleton variant="text" width="60%" height={24} />
                    <Skeleton variant="text" width="40%" height={32} sx={{ mt: 1 }} />
                    <Skeleton variant="text" width="30%" height={16} sx={{ mt: 1 }} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={3}>
                <Card>
                  <CardContent>
                    <Skeleton variant="text" width="60%" height={24} />
                    <Skeleton variant="text" width="40%" height={32} sx={{ mt: 1 }} />
                    <Skeleton variant="text" width="30%" height={16} sx={{ mt: 1 }} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={3}>
                <Card>
                  <CardContent>
                    <Skeleton variant="text" width="60%" height={24} />
                    <Skeleton variant="text" width="40%" height={32} sx={{ mt: 1 }} />
                    <Skeleton variant="text" width="30%" height={16} sx={{ mt: 1 }} />
                  </CardContent>
                </Card>
              </Grid>

              {/* Chart skeleton */}
              <Grid item xs={12} md={8}>
                <Card>
                  <CardContent>
                    <Skeleton variant="text" width={200} height={28} sx={{ mb: 2 }} />
                    <Skeleton variant="rectangular" width="100%" height={300} />
                  </CardContent>
                </Card>
              </Grid>

              {/* Table skeleton */}
              <Grid item xs={12} md={4}>
                <Card>
                  <CardContent>
                    <Skeleton variant="text" width={150} height={28} sx={{ mb: 2 }} />
                    {Array.from({ length: 5 }).map((_, index) => (
                      <Box key={index} sx={{ mb: 2 }}>
                        <Skeleton variant="text" width="80%" height={20} />
                        <Skeleton variant="text" width="60%" height={16} sx={{ mt: 0.5 }} />
                      </Box>
                    ))}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Box>
        );

      case 'chart':
        return (
          <Card>
            <CardContent>
              <Skeleton variant="text" width={200} height={28} sx={{ mb: 2 }} />
              <Skeleton variant="rectangular" width="100%" height={300} />
            </CardContent>
          </Card>
        );

      case 'card':
        return Array.from({ length: count }).map((_, index) => (
          <Card key={index} sx={{ mb: 2 }}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <Skeleton variant="circular" width={40} height={40} />
                <Box sx={{ flex: 1 }}>
                  <Skeleton variant="text" width="70%" height={24} />
                  <Skeleton variant="text" width="50%" height={16} sx={{ mt: 0.5 }} />
                </Box>
              </Box>
              <Box sx={{ mt: 2 }}>
                <Skeleton variant="rectangular" width="100%" height={60} />
              </Box>
            </CardContent>
          </Card>
        ));

      case 'table':
        return (
          <Card>
            <CardContent>
              <Skeleton variant="text" width={150} height={28} sx={{ mb: 2 }} />
              {Array.from({ length: count }).map((_, index) => (
                <Box key={index} sx={{ mb: 2, display: 'flex', gap: 2 }}>
                  <Skeleton variant="rectangular" width={60} height={20} />
                  <Skeleton variant="text" width={120} height={20} />
                  <Skeleton variant="text" width={80} height={20} />
                  <Skeleton variant="text" width={100} height={20} />
                </Box>
              ))}
            </CardContent>
          </Card>
        );

      default:
        return <Skeleton variant="rectangular" width="100%" height={200} />;
    }
  };

  return <>{renderSkeleton()}</>;
};

export default LoadingSkeleton;
