import React, { useEffect, useRef, useState } from 'react';
import { Box } from '@mui/material';

interface Particle {
  id: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  opacity: number;
  life: number;
  color: string;
}

interface SapphireDustProps {
  intensity?: number; // 0-1, controls particle density
  speed?: number; // 0-1, controls particle speed
  color?: string; // Particle color
  size?: 'small' | 'medium' | 'large';
  enabled?: boolean;
}

const SapphireDust: React.FC<SapphireDustProps> = ({
  intensity = 0.5,
  speed = 0.5,
  color = '#0ea5e9', // Sapphire blue
  size = 'medium',
  enabled = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const animationFrameRef = useRef<number>();
  const containerRef = useRef<HTMLDivElement>(null);

  const particleCount = Math.floor(30 * intensity);
  const baseSpeed = 0.5 + speed * 0.5;
  const particleSize = size === 'small' ? 2 : size === 'medium' ? 3 : 4;

  // Initialize particles
  useEffect(() => {
    if (!enabled || !containerRef.current) return;

    const container = containerRef.current;
    const width = container.offsetWidth;
    const height = container.offsetHeight;

    particlesRef.current = Array.from({ length: particleCount }, (_, i) => ({
      id: i,
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * baseSpeed,
      vy: (Math.random() - 0.5) * baseSpeed,
      size: particleSize + Math.random() * 2,
      opacity: 0.3 + Math.random() * 0.4,
      life: Math.random(),
      color: color,
    }));
  }, [enabled, particleCount, baseSpeed, particleSize, color]);

  // Animation loop
  useEffect(() => {
    if (!enabled) return;

    const canvas = canvasRef.current;
    if (!canvas || !containerRef.current) return;

    const container = containerRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const animate = () => {
      const width = container.offsetWidth;
      const height = container.offsetHeight;

      canvas.width = width;
      canvas.height = height;

      ctx.clearRect(0, 0, width, height);

      particlesRef.current.forEach((particle) => {
        // Update position
        particle.x += particle.vx;
        particle.y += particle.vy;

        // Wrap around edges
        if (particle.x < 0) particle.x = width;
        if (particle.x > width) particle.x = 0;
        if (particle.y < 0) particle.y = height;
        if (particle.y > height) particle.y = 0;

        // Update life for twinkling effect
        particle.life += 0.02;
        const twinkle = (Math.sin(particle.life) + 1) / 2;
        const currentOpacity = particle.opacity * (0.5 + twinkle * 0.5);

        // Draw particle with glow
        ctx.save();
        ctx.globalAlpha = currentOpacity;

        // Outer glow
        const gradient = ctx.createRadialGradient(
          particle.x,
          particle.y,
          0,
          particle.x,
          particle.y,
          particle.size * 3
        );
        gradient.addColorStop(0, particle.color);
        gradient.addColorStop(0.5, `${particle.color}80`);
        gradient.addColorStop(1, `${particle.color}00`);

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size * 3, 0, Math.PI * 2);
        ctx.fill();

        // Core particle
        ctx.fillStyle = particle.color;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
      });

      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [enabled, color]);

  if (!enabled) return null;

  return (
    <Box
      ref={containerRef}
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
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
        }}
      />
    </Box>
  );
};

export default SapphireDust;
