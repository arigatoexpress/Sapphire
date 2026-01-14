import React, { useEffect, useState } from 'react';
import { Box } from '@mui/material';
import SapphireDust from './SapphireDust';
import DiamondSparkle from './DiamondSparkle';

interface TradeAlertEffectProps {
  trigger: boolean;
  type?: 'buy' | 'sell' | 'signal';
  onComplete?: () => void;
}

const TradeAlertEffect: React.FC<TradeAlertEffectProps> = ({
  trigger,
  type = 'signal',
  onComplete,
}) => {
  const [showEffect, setShowEffect] = useState(false);
  const [showSparkles, setShowSparkles] = useState(false);

  useEffect(() => {
    if (trigger) {
      setShowEffect(true);
      setShowSparkles(true);

      const sparkleTimeout = setTimeout(() => {
        setShowSparkles(false);
      }, 2000);

      const effectTimeout = setTimeout(() => {
        setShowEffect(false);
        if (onComplete) onComplete();
      }, 3000);

      return () => {
        clearTimeout(sparkleTimeout);
        clearTimeout(effectTimeout);
      };
    }
  }, [trigger, onComplete]);

  if (!showEffect) return null;

  const color = type === 'buy' ? '#10b981' : type === 'sell' ? '#ef4444' : '#0ea5e9';

  return (
    <Box
      sx={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        pointerEvents: 'none',
        zIndex: 9999,
      }}
    >
      {/* Sapphire dust effect */}
      <SapphireDust
        intensity={0.8}
        speed={0.8}
        color={color}
        size="medium"
        enabled={showEffect}
      />

      {/* Diamond sparkles */}
      <DiamondSparkle
        count={15}
        duration={2000}
        size={30}
        enabled={showSparkles}
        color={color}
      />

      {/* Burst effect at center */}
      <Box
        sx={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '200px',
          height: '200px',
          borderRadius: '50%',
          background: `radial-gradient(circle, ${color}40 0%, ${color}00 70%)`,
          animation: 'burst 1s ease-out forwards',
          '@keyframes burst': {
            '0%': {
              transform: 'translate(-50%, -50%) scale(0)',
              opacity: 1,
            },
            '50%': {
              transform: 'translate(-50%, -50%) scale(1.5)',
              opacity: 0.8,
            },
            '100%': {
              transform: 'translate(-50%, -50%) scale(3)',
              opacity: 0,
            },
          },
        }}
      />

      {/* Trade type indicator */}
      <Box
        sx={{
          position: 'absolute',
          top: '45%',
          left: '50%',
          transform: 'translateX(-50%)',
          color: color,
          fontSize: '3rem',
          fontWeight: 900,
          fontFamily: '"Orbitron", sans-serif',
          textShadow: `0 0 20px ${color}, 0 0 40px ${color}80`,
          animation: 'fadeInOut 2s ease-in-out',
          '@keyframes fadeInOut': {
            '0%': { opacity: 0, transform: 'translateX(-50%) translateY(-20px)' },
            '20%': { opacity: 1, transform: 'translateX(-50%) translateY(0)' },
            '80%': { opacity: 1, transform: 'translateX(-50%) translateY(0)' },
            '100%': { opacity: 0, transform: 'translateX(-50%) translateY(20px)' },
          },
        }}
      >
        {type === 'buy' ? '📈 BUY' : type === 'sell' ? '📉 SELL' : '⚡ SIGNAL'}
      </Box>
    </Box>
  );
};

export default TradeAlertEffect;
