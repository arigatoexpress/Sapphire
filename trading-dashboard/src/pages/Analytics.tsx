import React from 'react';
import { Box, Typography, Card, CardContent, Grid } from '@mui/material';

const Analytics: React.FC = () => {
  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 700 }}>
        Trading Analytics
      </Typography>
      <Typography variant="body1" color="textSecondary" sx={{ mb: 4 }}>
        Advanced analytics and performance insights
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Performance Metrics
              </Typography>
              <Typography color="textSecondary">
                Detailed analytics dashboard coming soon...
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Analytics;
