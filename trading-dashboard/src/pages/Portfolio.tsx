import React from 'react';
import { Box, Typography, Card, CardContent, Grid } from '@mui/material';

const Portfolio: React.FC = () => {
  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 700 }}>
        Portfolio Overview
      </Typography>
      <Typography variant="body1" color="textSecondary" sx={{ mb: 4 }}>
        Detailed portfolio analysis and performance metrics
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Portfolio Composition
              </Typography>
              <Typography color="textSecondary">
                Detailed portfolio breakdown coming soon...
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Portfolio;
