import React from 'react';
import { Box, Typography, Card, CardContent, Grid } from '@mui/material';

const Agents: React.FC = () => {
  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 700 }}>
        AI Agent Control Center
      </Typography>
      <Typography variant="body1" color="textSecondary" sx={{ mb: 4 }}>
        Monitor and manage your autonomous trading agents
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Agent Status & Activity
              </Typography>
              <Typography color="textSecondary">
                Real-time agent monitoring coming soon...
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Agents;
