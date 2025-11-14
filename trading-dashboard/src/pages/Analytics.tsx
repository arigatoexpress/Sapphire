import React from 'react';
import { Box } from '@mui/material';
import NeuralNetwork from '../components/NeuralNetwork';

const Analytics: React.FC = () => {
  return (
    <Box sx={{ width: '100%', height: '100vh', position: 'relative', overflow: 'hidden' }}>
      <NeuralNetwork />
    </Box>
  );
};

export default Analytics;
