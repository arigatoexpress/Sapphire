import React, { useEffect, useState } from 'react';
import { Box } from '@mui/material';

interface Sparkle {
  id: number;
  x: number;
  y: number;
  size: number;
  rotation: number;
  opacity: number;
  life: number;
  delay: number;
}

interface DiamondSparkleProps {
  count?: number;
  duration?: number;
  size?: number;
  enabled?: boolean;
  color?: string;
}

const DiamondSparkle: React.FC<DiamondSparkleProps> = ({
  count = 5,
  duration = 2000,
  size = 20,
  enabled = true,
  color = '#0ea5e9',
}) => {
  const [sparkles, setSparkles] = useState<Sparkle[]>([]);

  useEffect(() => {
    if (!enabled) return;

    const newSparkles: Sparkle[] = Array.from({ length: count }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      y: Math.random() * 100,
      size: size + Math.random() * size * 0.5,
      rotation: Math.random() * 360,
      opacity: 0,
      life: 0,
      delay: i * (duration / count),
    }));

    setSparkles(newSparkles);

    const interval = setInterval(() => {
      setSparkles((prev) =>
        prev.map((sparkle) => ({
          ...sparkle,
          life: sparkle.life + 16, // ~60fps
          opacity: Math.min(1, (sparkle.life - sparkle.delay) / (duration * 0.3)),
        }))
      );
    }, 16);

    const timeout = setTimeout(() => {
      setSparkles([]);
    }, duration);

    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [enabled, count, duration, size]);

  if (!enabled || sparkles.length === 0) return null;

  return (
    <Box
      sx={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      {sparkles.map((sparkle) => {
        if (sparkle.life < sparkle.delay || sparkle.opacity <= 0) return null;

        // FIX: Use Math.max(0, ...) to prevent negative values and clamp opacity
        const fadeOut = sparkle.life > duration * 0.7;
        let currentOpacity = fadeOut
          ? sparkle.opacity * (1 - (sparkle.life - duration * 0.7) / (duration * 0.3))
          : sparkle.opacity;
        
        currentOpacity = Math.max(0, currentOpacity);

        return (
          <Box
            key={sparkle.id}
            sx={{
              position: 'absolute',
              left: `${sparkle.x}%`,
              top: `${sparkle.y}%`,
              width: `${sparkle.size}px`,
              height: `${sparkle.size}px`,
              transform: `translate(-50%, -50%) rotate(${sparkle.rotation}deg)`,
              opacity: currentOpacity,
              transition: 'opacity 0.1s ease-out',
            }}
          >
            {/* Diamond shape using CSS */}
            <Box
              sx={{
                width: '100%',
                height: '100%',
                position: 'relative',
                '&::before': {
                  content: '""',
                  position: 'absolute',
                  top: '0',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  width: '0',
                  height: '0',
                  borderLeft: `${sparkle.size / 2}px solid transparent`,
                  borderRight: `${sparkle.size / 2}px solid transparent`,
                  borderBottom: `${sparkle.size / 2}px solid ${color}`,
                  filter: `drop-shadow(0 0 ${sparkle.size / 2}px ${color})`,
                },
                '&::after': {
                  content: '""',
                  position: 'absolute',
                  bottom: '0',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  width: '0',
                  height: '0',
                  borderLeft: `${sparkle.size / 2}px solid transparent`,
                  borderRight: `${sparkle.size / 2}px solid transparent`,
                  borderTop: `${sparkle.size / 2}px solid ${color}`,
                  filter: `drop-shadow(0 0 ${sparkle.size / 2}px ${color})`,
                },
              }}
            />
            {/* Glow effect */}
            <Box
              sx={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                width: `${sparkle.size * 2}px`,
                height: `${sparkle.size * 2}px`,
                borderRadius: '50%',
                background: `radial-gradient(circle, ${color}40 0%, ${color}00 70%)`,
                animation: 'pulse 1s ease-in-out infinite',
                '@keyframes pulse': {
                  '0%, 100%': { transform: 'translate(-50%, -50%) scale(1)', opacity: 0.5 },
                  '50%': { transform: 'translate(-50%, -50%) scale(1.5)', opacity: 0.8 },
                },
              }}
            />
          </Box>
        );
      })}
    </Box>
  );
};

export default DiamondSparkle;

