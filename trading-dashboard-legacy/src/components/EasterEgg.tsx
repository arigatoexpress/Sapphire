import React, { useState, useEffect } from 'react';
import {
  Box,
  Dialog,
  DialogContent,
  Typography,
  Button,
  keyframes,
} from '@mui/material';
import { Rocket, EmojiEvents, Celebration } from '@mui/icons-material';

const bounce = keyframes`
  0%, 100% { transform: translateY(0) rotate(0deg); }
  25% { transform: translateY(-20px) rotate(-5deg); }
  50% { transform: translateY(-10px) rotate(5deg); }
  75% { transform: translateY(-15px) rotate(-3deg); }
`;

const sparkle = keyframes`
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.2); }
`;

const EasterEgg: React.FC<{ trigger: boolean; onClose: () => void }> = ({ trigger, onClose }) => {
  const [show, setShow] = useState(false);
  const [clankerCount, setClankerCount] = useState(0);

  useEffect(() => {
    if (trigger) {
      setShow(true);
      setClankerCount(prev => prev + 1);
    }
  }, [trigger]);

  const handleClose = () => {
    setShow(false);
    onClose();
  };

  return (
    <Dialog
      open={show}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: {
          background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.95), rgba(6, 182, 212, 0.95), rgba(236, 72, 153, 0.95))',
          backdropFilter: 'blur(20px)',
          borderRadius: 4,
          border: '2px solid rgba(255, 255, 255, 0.3)',
          boxShadow: '0 20px 60px rgba(139, 92, 246, 0.5)',
        }
      }}
    >
      <DialogContent sx={{ p: 4, textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
        {/* Animated background elements */}
        <Box
          sx={{
            position: 'absolute',
            top: -50,
            right: -50,
            width: 200,
            height: 200,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(255, 255, 255, 0.2) 0%, transparent 70%)',
            animation: `${sparkle} 2s ease-in-out infinite`,
          }}
        />
        <Box
          sx={{
            position: 'absolute',
            bottom: -30,
            left: -30,
            width: 150,
            height: 150,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(255, 255, 255, 0.15) 0%, transparent 70%)',
            animation: `${sparkle} 3s ease-in-out infinite 0.5s`,
          }}
        />

        <Box sx={{ position: 'relative', zIndex: 1 }}>
          <Rocket
            sx={{
              fontSize: 80,
              color: '#ffd700',
              mb: 2,
              animation: `${bounce} 1s ease-in-out infinite`,
            }}
          />

          <Typography
            variant="h3"
            sx={{
              fontWeight: 900,
              mb: 2,
              background: 'linear-gradient(45deg, #ffd700, #ff6b35, #ffd700)',
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundSize: '200% 200%',
              animation: 'gradientShift 3s ease infinite',
              '@keyframes gradientShift': {
                '0%': { backgroundPosition: '0% 50%' },
                '50%': { backgroundPosition: '100% 50%' },
                '100%': { backgroundPosition: '0% 50%' },
              },
            }}
          >
            🎉 RELEASE THE CLANKERS! 🎉
          </Typography>

          <Typography
            variant="h6"
            sx={{
              color: 'rgba(255, 255, 255, 0.95)',
              mb: 3,
              fontWeight: 600,
            }}
          >
            The AI trading bots have been unleashed! 🤖
          </Typography>

          <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2, mb: 3 }}>
            <Celebration sx={{ fontSize: 40, color: '#ffd700', animation: `${bounce} 1.2s ease-in-out infinite` }} />
            <EmojiEvents sx={{ fontSize: 40, color: '#ffd700', animation: `${bounce} 1.2s ease-in-out infinite 0.2s` }} />
            <Celebration sx={{ fontSize: 40, color: '#ffd700', animation: `${bounce} 1.2s ease-in-out infinite 0.4s` }} />
          </Box>

          <Typography
            variant="body1"
            sx={{
              color: 'rgba(255, 255, 255, 0.9)',
              mb: 3,
              lineHeight: 1.8,
              fontStyle: 'italic',
            }}
          >
            {clankerCount === 1 && "You found the secret! The clankers are now active and ready to trade! 🚀"}
            {clankerCount === 2 && "You're persistent! The clankers appreciate your dedication! 💪"}
            {clankerCount === 3 && "Third time's the charm! The clankers are now at maximum power! ⚡"}
            {clankerCount > 3 && `Wow, ${clankerCount} times! The clankers are in overdrive mode! 🔥`}
          </Typography>

          <Typography
            variant="body2"
            sx={{
              color: 'rgba(255, 255, 255, 0.7)',
              mb: 3,
            }}
          >
            All 6 AI agents are now operating at peak performance, analyzing markets in real-time,
            and executing trades with precision. The clankers are loose! 🤖💰
          </Typography>

          <Button
            variant="contained"
            onClick={handleClose}
            sx={{
              mt: 2,
              px: 4,
              py: 1.5,
              borderRadius: 3,
              background: 'linear-gradient(135deg, #ffd700, #ff6b35)',
              color: '#000',
              fontWeight: 700,
              fontSize: '1.1rem',
              textTransform: 'none',
              boxShadow: '0 8px 20px rgba(255, 215, 0, 0.4)',
              '&:hover': {
                background: 'linear-gradient(135deg, #ffed4e, #ff8c5a)',
                boxShadow: '0 12px 30px rgba(255, 215, 0, 0.6)',
                transform: 'translateY(-2px)',
              },
              transition: 'all 0.3s ease',
            }}
          >
            Let's Go Trading! 🚀
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
};

export default EasterEgg;
