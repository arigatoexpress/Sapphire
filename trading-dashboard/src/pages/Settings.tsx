import React from 'react';
import { Box, Typography, Card, CardContent, Grid, TextField, Button } from '@mui/material';

const Settings: React.FC = () => {
  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 700 }}>
        System Settings
      </Typography>
      <Typography variant="body1" color="textSecondary" sx={{ mb: 4 }}>
        Configure your trading system parameters
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Risk Management
              </Typography>
              <TextField
                fullWidth
                label="Max Risk per Trade (%)"
                defaultValue="5"
                margin="normal"
              />
              <TextField
                fullWidth
                label="Portfolio Risk Limit (%)"
                defaultValue="15"
                margin="normal"
              />
              <Button variant="contained" sx={{ mt: 2 }}>
                Save Risk Settings
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Communication Settings
              </Typography>
              <TextField
                fullWidth
                label="Agent Participation Threshold"
                defaultValue="0.5"
                margin="normal"
                helperText="0.0 = No participation, 1.0 = Always participate"
              />
              <TextField
                fullWidth
                label="Communication Throttle (seconds)"
                defaultValue="30"
                margin="normal"
              />
              <Button variant="contained" sx={{ mt: 2 }}>
                Save Communication Settings
              </Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Settings;
