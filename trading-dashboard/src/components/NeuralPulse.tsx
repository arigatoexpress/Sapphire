import React, { useEffect, useState } from 'react';
import { Box } from '@mui/material';

interface NeuralPulseProps {
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  color: string;
  duration?: number;
  onComplete?: () => void;
}

const NeuralPulse: React.FC<NeuralPulseProps> = ({
  startX,
  startY,
  endX,
  endY,
  color,
  duration = 2000,
  onComplete,
}) => {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const startTime = Date.now();
    const animate = () => {
      const elapsed = Date.now() - startTime;
      const newProgress = Math.min(elapsed / duration, 1);
      setProgress(newProgress);

      if (newProgress < 1) {
        requestAnimationFrame(animate);
      } else if (onComplete) {
        onComplete();
      }
    };
    const frameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameId);
  }, [duration, onComplete]);

  // Calculate current position along the line
  const currentX = startX + (endX - startX) * progress;
  const currentY = startY + (endY - startY) * progress;

  // Calculate distance for glow effect
  const distance = Math.sqrt(
    Math.pow(endX - startX, 2) + Math.pow(endY - startY, 2)
  );
  const glowSize = Math.max(8, Math.min(20, distance * 0.1));

  return (
    <>
      {/* Main pulse orb */}
      <Box
        sx={{
          position: 'absolute',
          left: `${currentX}px`,
          top: `${currentY}px`,
          width: `${glowSize}px`,
          height: `${glowSize}px`,
          borderRadius: '50%',
          background: `radial-gradient(circle, ${color} 0%, ${color}00 70%)`,
          boxShadow: `0 0 ${glowSize * 2}px ${color}, 0 0 ${glowSize * 4}px ${color}80, 0 0 ${glowSize * 6}px ${color}40`,
          transform: 'translate(-50%, -50%)',
          opacity: 1 - progress * 0.7,
          pointerEvents: 'none',
          zIndex: 10,
          transition: 'opacity 0.1s ease-out',
        }}
      />
      {/* Trailing spark effect */}
      <Box
        sx={{
          position: 'absolute',
          left: `${currentX}px`,
          top: `${currentY}px`,
          width: `${glowSize * 0.6}px`,
          height: `${glowSize * 0.6}px`,
          borderRadius: '50%',
          background: `radial-gradient(circle, ${color}FF 0%, ${color}00 100%)`,
          boxShadow: `0 0 ${glowSize}px ${color}`,
          transform: 'translate(-50%, -50%)',
          opacity: (1 - progress * 0.7) * 0.5,
          pointerEvents: 'none',
          zIndex: 9,
          animation: 'sparkle 0.3s ease-in-out infinite',
          '@keyframes sparkle': {
            '0%, 100%': { transform: 'translate(-50%, -50%) scale(1)', opacity: 0.5 },
            '50%': { transform: 'translate(-50%, -50%) scale(1.3)', opacity: 0.8 },
          },
        }}
      />
    </>
  );
};

export default NeuralPulse;

