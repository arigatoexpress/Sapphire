import React from 'react';
import { Box, Typography, Alert, AlertTitle, Link } from '@mui/material';
import { Warning as WarningIcon } from '@mui/icons-material';

const RegulatoryDisclaimer: React.FC = () => {
  return (
    <Alert
      severity="warning"
      icon={<WarningIcon />}
      sx={{
        mt: 2,
        mb: 2,
        bgcolor: 'rgba(245, 158, 11, 0.1)',
        border: '1px solid rgba(245, 158, 11, 0.3)',
        borderRadius: 2,
        '& .MuiAlert-icon': {
          color: '#F59E0B',
        },
      }}
    >
      <AlertTitle sx={{ fontWeight: 700, mb: 1 }}>
        Important Risk Disclosure
      </AlertTitle>
      <Typography variant="body2" sx={{ mb: 1 }}>
        <strong>Trading cryptocurrencies and digital assets involves substantial risk of loss.</strong> Past performance does not guarantee future results.
        The AI trading system operates autonomously and may execute trades that result in financial losses.
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        <strong>Capital Allocation:</strong> This system allocates $500 per AI agent ($3,000 total) for trading purposes.
        You may lose some or all of your invested capital. Only trade with funds you can afford to lose.
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        <strong>No Investment Advice:</strong> This platform provides automated trading services. It does not constitute investment,
        financial, trading, or other advice. All trading decisions are made by AI algorithms without human intervention.
      </Typography>
      <Typography variant="body2">
        <strong>Regulatory Notice:</strong> Cryptocurrency trading may be subject to regulatory oversight in your jurisdiction.
        Please ensure compliance with all applicable laws and regulations. This system is for informational and educational purposes only.
      </Typography>
    </Alert>
  );
};

export default RegulatoryDisclaimer;
