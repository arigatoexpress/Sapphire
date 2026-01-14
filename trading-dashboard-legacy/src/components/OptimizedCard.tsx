/**
 * Optimized reusable card component with common styling
 * Reduces redundancy across components
 */

import React from 'react';
import { Card, CardContent, SxProps, Theme } from '@mui/material';
import { commonCardStyles, gradientCardStyles } from '../utils/themeUtils';

interface OptimizedCardProps {
  children: React.ReactNode;
  gradient?: { color1: string; color2: string };
  sx?: SxProps<Theme>;
  onClick?: () => void;
}

const OptimizedCard: React.FC<OptimizedCardProps> = ({
  children,
  gradient,
  sx = {},
  onClick
}) => {
  const baseStyles = gradient
    ? gradientCardStyles(gradient.color1, gradient.color2)
    : commonCardStyles;

  return (
    <Card
      sx={{ ...baseStyles, ...sx }}
      onClick={onClick}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
    >
      <CardContent>
        {children}
      </CardContent>
    </Card>
  );
};

export default OptimizedCard;
