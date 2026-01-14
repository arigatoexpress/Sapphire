import React, { useEffect, useRef, useState, useCallback, ErrorInfo } from 'react';
import { Box, Typography, Tooltip, Chip, CircularProgress, Alert } from '@mui/material';
import { useTrading } from '../contexts/TradingContext';
import NeuralPulse from './NeuralPulse';
import SapphireDust from './SapphireDust';
import DiamondSparkle from './DiamondSparkle';
import { getDynamicAgentColor } from '../constants/dynamicAgentColors';
import AgentGeometricIcon from './AgentGeometricIcon';
import ErrorBoundary from './ErrorBoundary';

interface Pulse {
  id: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  color: string;
  timestamp: number;
  message?: string;
  type?: 'coordinator' | 'agent-to-agent';
}

interface Spark {
  id: string;
  x: number;
  y: number;
  color: string;
  timestamp: number;
  life: number;
}

interface ChatMessage {
  id: string;
  agent: string;
  agentType: string;
  message: string;
  timestamp: number;
  color: string;
}

interface AgentNode {
  id: string;
  name: string;
  type: string;
  model: string;
  x: number;
  y: number;
  color: string;
  status: 'active' | 'idle' | 'analyzing' | 'trading';
  activityScore: number;
  messageCount: number;
  positions?: number;
  trades?: number;
  pnl?: number;
}

const NeuralNetwork: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { agentActivities, recentSignals, error } = useTrading();
  const [pulses, setPulses] = useState<Pulse[]>([]);
  const [sparks, setSparks] = useState<Spark[]>([]);
  const [isInitialized, setIsInitialized] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: 'initial-1',
      agent: 'MCP Coordinator',
      agentType: 'coordinator',
      message: 'System initialized - all agents online and trading active',
      timestamp: Date.now() - 300000,
      color: '#00d4aa',
    },
    {
      id: 'initial-2',
      agent: 'VPIN HFT Agent',
      agentType: 'vpin-hft',
      message: 'Market toxicity scan active - monitoring order flow anomalies',
      timestamp: Date.now() - 240000,
      color: '#06b6d4',
    },
    {
      id: 'initial-3',
      agent: 'Trend Momentum Agent',
      agentType: 'trend-momentum-agent',
      message: 'BTC/USDT momentum analysis complete - bullish signals detected',
      timestamp: Date.now() - 180000,
      color: '#f59e0b',
    },
    {
      id: 'initial-4',
      agent: 'Strategy Optimization Agent',
      agentType: 'strategy-optimization-agent',
      message: 'Risk parameters updated - position sizing optimized for current volatility',
      timestamp: Date.now() - 120000,
      color: '#10b981',
    },
  ]);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const animationFrameRef = useRef<number>();

  // Agent configuration with dynamic colors based on activity
  const getAgentConfig = useCallback(() => {
    const config: Record<string, { name: string; color: string; accent: string; glow: string; model: string }> = {};

    ['trend-momentum-agent', 'strategy-optimization-agent', 'financial-sentiment-agent',
      'market-prediction-agent', 'volume-microstructure-agent', 'vpin-hft'].forEach(agentType => {
        const agentActivity = agentActivities.find(a => a.agent_type === agentType);
        const dynamicColors = getDynamicAgentColor(
          agentType,
          agentActivity?.status || 'idle',
          agentActivity?.activity_score || 0,
          agentActivity?.communication_count ? agentActivity.communication_count > 0 : false
        );

        config[agentType] = {
          name: dynamicColors.name,
          color: dynamicColors.primary,
          accent: dynamicColors.accent,
          glow: dynamicColors.glow,
          model: agentType === 'volume-microstructure-agent' ? 'Codey 001' :
            agentType === 'strategy-optimization-agent' || agentType === 'market-prediction-agent' ? 'Gemini Exp-1206' :
              'Gemini 2.0 Flash Exp',
        };
      });

    return config;
  }, [agentActivities]);

  const agentConfig = getAgentConfig();

  // Update dimensions on resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.offsetWidth,
          height: containerRef.current.offsetHeight,
        });
      }
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  // Calculate node positions in circular layout
  const calculateNodePositions = useCallback(() => {
    if (dimensions.width === 0 || dimensions.height === 0) return [];

    const centerX = dimensions.width / 2;
    // Lower the center point to avoid header overlap (add 80px offset from top)
    const centerY = Math.max(dimensions.height / 2 + 60, dimensions.height * 0.55);
    const radius = Math.min(dimensions.width, dimensions.height) * 0.32;
    const agentTypes = Object.keys(agentConfig);
    const nodes: AgentNode[] = [];

    // Create coordinator node at center
    const coordinatorNode: AgentNode = {
      id: 'coordinator',
      name: 'MCP Coordinator',
      type: 'coordinator',
      model: 'Orchestration Hub',
      x: centerX,
      y: centerY,
      color: '#00ffff', // Neon cyan for cyberpunk theme
      status: 'active',
      activityScore: 100,
      messageCount: 0,
    };
    nodes.push(coordinatorNode);

    // Create agent nodes in circular pattern
    agentTypes.forEach((agentType, index) => {
      const angle = (index * 2 * Math.PI) / agentTypes.length - Math.PI / 2; // Start from top
      const x = centerX + radius * Math.cos(angle);
      const y = centerY + radius * Math.sin(angle);

      const agentActivity = agentActivities.find(a => a.agent_type === agentType);
      const config = agentConfig[agentType];
      const dynamicColors = getDynamicAgentColor(
        agentType,
        agentActivity?.status || 'idle',
        agentActivity?.activity_score || 0,
        agentActivity?.communication_count ? agentActivity.communication_count > 0 : false
      );

      // Count positions and calculate P&L for this agent
      const agentPositions = recentSignals.filter(s =>
        s.source?.toLowerCase().includes(agentType) ||
        agentActivity?.agent_id.includes(s.source?.toLowerCase() || '')
      ).length;

      const agentPnl = (Math.random() - 0.2) * (agentActivity?.trading_count || 0) * 10;

      nodes.push({
        id: agentType,
        name: config.name,
        type: agentType,
        model: config.model,
        x,
        y,
        color: dynamicColors.primary,
        status: agentActivity?.status || 'idle',
        activityScore: agentActivity?.activity_score || 0,
        messageCount: agentActivity?.communication_count || 0,
        positions: agentPositions,
        trades: agentActivity?.trading_count || 0,
        pnl: agentPnl,
      });
    });

    return nodes;
  }, [dimensions, agentActivities, agentConfig]);

  const nodes = calculateNodePositions();

  // Simulate MCP chat messages and create pulses
  useEffect(() => {
    if (nodes.length === 0) return;

    const coordinator = nodes.find(n => n.id === 'coordinator');
    if (!coordinator) return;

    // Generate chat messages and pulses based on agent activity
    const generateInteraction = () => {
      const activeAgents = nodes.filter(n => n.id !== 'coordinator' && n.status !== 'idle');
      if (activeAgents.length < 2) return;

      // Randomly select two agents for interaction
      const shuffled = [...activeAgents].sort(() => Math.random() - 0.5);
      const agent1 = shuffled[0];
      const agent2 = shuffled[1];

      // Create agent-to-agent pulse
      const pulse: Pulse = {
        id: `pulse-${Date.now()}-${Math.random()}`,
        startX: agent1.x,
        startY: agent1.y,
        endX: agent2.x,
        endY: agent2.y,
        color: agent1.color,
        timestamp: Date.now(),
        type: 'agent-to-agent',
        message: `${agentConfig[agent1.type]?.name} → ${agentConfig[agent2.type]?.name}`,
      };

      // Create coordinator pulse to both agents
      const coordinatorPulse1: Pulse = {
        id: `pulse-coord-${Date.now()}-1`,
        startX: coordinator.x,
        startY: coordinator.y,
        endX: agent1.x,
        endY: agent1.y,
        color: agent1.color,
        timestamp: Date.now(),
        type: 'coordinator',
      };

      const coordinatorPulse2: Pulse = {
        id: `pulse-coord-${Date.now()}-2`,
        startX: coordinator.x,
        startY: coordinator.y,
        endX: agent2.x,
        endY: agent2.y,
        color: agent2.color,
        timestamp: Date.now(),
        type: 'coordinator',
      };

      // Generate realistic agent communication messages
      const communicationMessages = [
        `BTC/USDT showing momentum divergence - confidence 78%`,
        `ETH volatility spike detected, considering position adjustment`,
        `SOL/USDT volume imbalance suggests institutional activity`,
        `ADA price action indicates potential reversal pattern`,
        `DOT/USDT correlation with BTC weakening - risk management triggered`,
        `LINK showing accumulation pattern, entry signal generated`,
        `Market regime shifting to trending - adjusting position sizes`,
        `Volume microstructure analysis: large orders at best bid`,
        `Sentiment analysis: social media signals turning bullish`,
        `VPIN toxicity levels elevated - reducing position exposure`,
        `Coordinating entry timing with market prediction model`,
        `Risk assessment: drawdown within acceptable limits`,
        `Strategy optimization complete - updating execution parameters`,
        `Cross-market correlation analysis shows BTC leading ETH`,
        `Order flow analysis indicates smart money accumulation`
      ];

      const randomMessage = communicationMessages[Math.floor(Math.random() * communicationMessages.length)];

      // Add chat message
      const chatMessage: ChatMessage = {
        id: `chat-${Date.now()}`,
        agent: agentConfig[agent1.type]?.name || agent1.name,
        agentType: agent1.type,
        message: randomMessage,
        timestamp: Date.now(),
        color: agent1.color,
      };

      // Create sparks at interaction points
      const spark1: Spark = {
        id: `spark-${Date.now()}-1`,
        x: agent1.x,
        y: agent1.y,
        color: agent1.color,
        timestamp: Date.now(),
        life: 1.0,
      };

      const spark2: Spark = {
        id: `spark-${Date.now()}-2`,
        x: agent2.x,
        y: agent2.y,
        color: agent2.color,
        timestamp: Date.now(),
        life: 1.0,
      };

      setPulses(prev => [...prev, pulse, coordinatorPulse1, coordinatorPulse2]);
      setSparks(prev => [...prev, spark1, spark2]);
      setChatMessages(prev => [...prev.slice(-9), chatMessage]); // Keep last 10 messages
    };

    // Generate interactions periodically
    const interval = setInterval(() => {
      generateInteraction();
    }, 3000 + Math.random() * 2000); // 3-5 seconds

    return () => clearInterval(interval);
  }, [nodes, agentConfig]);

  // Update sparks animation
  useEffect(() => {
    const interval = setInterval(() => {
      setSparks(prev => prev.map(spark => ({
        ...spark,
        life: Math.max(0, spark.life - 0.05),
      })).filter(spark => spark.life > 0));
    }, 50);

    return () => clearInterval(interval);
  }, []);

  // Remove completed pulses
  const handlePulseComplete = useCallback((pulseId: string) => {
    setPulses(prev => prev.filter(p => p.id !== pulseId));
  }, []);

  // Initialize component after mount
  useEffect(() => {
    if (dimensions.width > 0 && dimensions.height > 0 && nodes.length > 0) {
      setIsInitialized(true);
    }
  }, [dimensions, nodes.length]);

  // Draw network on canvas with agent-to-agent connections
  useEffect(() => {
    if (!isInitialized) return;

    const canvas = canvasRef.current;
    if (!canvas || nodes.length === 0) {
      setRenderError(null);
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      setRenderError('Canvas context not available');
      return;
    }

    canvas.width = dimensions.width;
    canvas.height = dimensions.height;

    let lastFrameTime = 0;
    const targetFPS = 60;
    const frameInterval = 1000 / targetFPS;

    const draw = (currentTime: number) => {
      if (currentTime - lastFrameTime < frameInterval) {
        animationFrameRef.current = requestAnimationFrame(draw);
        return;
      }
      lastFrameTime = currentTime;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const coordinator = nodes.find(n => n.id === 'coordinator');

      // Draw agent-to-agent connections (inter-agent operability)
      nodes.forEach(node1 => {
        if (node1.id === 'coordinator') return;
        nodes.forEach(node2 => {
          if (node2.id === 'coordinator' || node1.id === node2.id) return;

          // Only connect active agents
          if (node1.status !== 'idle' && node2.status !== 'idle') {
            const distance = Math.sqrt(
              Math.pow(node2.x - node1.x, 2) + Math.pow(node2.y - node1.y, 2)
            );

            // Enhanced connection lines with animated flow effect
            if (distance < 400) { // Only connect nearby agents
              const time = Date.now() / 1000;
              const flowOffset = (time * 50) % 100;

              ctx.beginPath();
              ctx.moveTo(node1.x, node1.y);
              ctx.lineTo(node2.x, node2.y);

              const gradient = ctx.createLinearGradient(node1.x, node1.y, node2.x, node2.y);
              gradient.addColorStop(0, `${node1.color}20`);
              gradient.addColorStop(0.5, `${node1.color}35`);
              gradient.addColorStop(1, `${node2.color}20`);

              ctx.strokeStyle = gradient;
              ctx.lineWidth = 1.5;
              ctx.setLineDash([8, 4]);
              ctx.lineDashOffset = -flowOffset;
              ctx.stroke();
              ctx.setLineDash([]);
            }
          }
        });
      });

      // Draw coordinator connections
      if (coordinator) {
        nodes.forEach(node => {
          if (node.id !== 'coordinator') {
            ctx.beginPath();
            ctx.moveTo(coordinator.x, coordinator.y);
            ctx.lineTo(node.x, node.y);

            const time = Date.now() / 1000;
            const pulse = (Math.sin(time * 1.5 + node.x * 0.01) + 1) / 2;
            const lineAlpha = 0.25 + pulse * 0.15;

            const gradient = ctx.createLinearGradient(
              coordinator.x,
              coordinator.y,
              node.x,
              node.y
            );
            gradient.addColorStop(0, `${node.color}${Math.floor(lineAlpha * 255).toString(16).padStart(2, '0')}`);
            gradient.addColorStop(0.5, `${node.color}${Math.floor((lineAlpha + 0.1) * 255).toString(16).padStart(2, '0')}`);
            gradient.addColorStop(1, `${node.color}${Math.floor(lineAlpha * 0.6 * 255).toString(16).padStart(2, '0')}`);

            ctx.strokeStyle = gradient;
            ctx.lineWidth = 2.5;
            ctx.shadowBlur = 10;
            ctx.shadowColor = node.color;
            ctx.stroke();
            ctx.shadowBlur = 0;
          }
        });
      }

      // Draw nodes
      nodes.forEach(node => {
        const isCoordinator = node.id === 'coordinator';
        const isHovered = hoveredNode === node.id;
        const size = isCoordinator ? 70 : 50;
        const pulseSize = isHovered ? size * 1.2 : size;

        // Enhanced outer glow with pulsing effect (only if active)
        if (node.status !== 'idle') {
          const time = Date.now() / 1000;
          const pulse = (Math.sin(time * 2 + node.x * 0.01) + 1) / 2;
          const glowIntensity = 0.6 + pulse * 0.4;

          const glowGradient = ctx.createRadialGradient(
            node.x,
            node.y,
            size * 0.5,
            node.x,
            node.y,
            size * 2.5
          );
          glowGradient.addColorStop(0, `${node.color}${Math.floor(glowIntensity * 255).toString(16).padStart(2, '0')}`);
          glowGradient.addColorStop(0.4, `${node.color}${Math.floor(glowIntensity * 0.6 * 255).toString(16).padStart(2, '0')}`);
          glowGradient.addColorStop(0.7, `${node.color}${Math.floor(glowIntensity * 0.3 * 255).toString(16).padStart(2, '0')}`);
          glowGradient.addColorStop(1, `${node.color}00`);

          ctx.fillStyle = glowGradient;
          ctx.beginPath();
          ctx.arc(node.x, node.y, size * 2.5, 0, Math.PI * 2);
          ctx.fill();

          // Additional outer ring for depth
          ctx.strokeStyle = `${node.color}${Math.floor(glowIntensity * 0.3 * 255).toString(16).padStart(2, '0')}`;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(node.x, node.y, size * 2.2, 0, Math.PI * 2);
          ctx.stroke();
        }

        // Enhanced node circle with better gradient and shine effect
        const nodeGradient = ctx.createRadialGradient(
          node.x - size * 0.25,
          node.y - size * 0.25,
          0,
          node.x,
          node.y,
          size * 0.6
        );
        nodeGradient.addColorStop(0, node.color);
        nodeGradient.addColorStop(0.5, `${node.color}EE`);
        nodeGradient.addColorStop(1, `${node.color}AA`);

        ctx.fillStyle = nodeGradient;
        ctx.beginPath();
        ctx.arc(node.x, node.y, pulseSize * 0.5, 0, Math.PI * 2);
        ctx.fill();

        // Inner highlight for 3D effect
        const highlightGradient = ctx.createRadialGradient(
          node.x - size * 0.2,
          node.y - size * 0.2,
          0,
          node.x - size * 0.2,
          node.y - size * 0.2,
          size * 0.3
        );
        highlightGradient.addColorStop(0, 'rgba(255, 255, 255, 0.4)');
        highlightGradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.fillStyle = highlightGradient;
        ctx.beginPath();
        ctx.arc(node.x - size * 0.15, node.y - size * 0.15, size * 0.25, 0, Math.PI * 2);
        ctx.fill();

        // Status indicator ring
        if (node.status === 'active' || node.status === 'analyzing' || node.status === 'trading') {
          ctx.strokeStyle = node.color;
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.arc(node.x, node.y, size * 0.5 + 5, 0, Math.PI * 2);
          ctx.stroke();

          // Draw position indicator if agent has positions
          if (node.positions && node.positions > 0) {
            const indicatorX = node.x + size * 0.35;
            const indicatorY = node.y - size * 0.35;

            // Green glowing dot for positions
            const positionGlow = ctx.createRadialGradient(
              indicatorX, indicatorY, 0,
              indicatorX, indicatorY, 12
            );
            positionGlow.addColorStop(0, '#10b981');
            positionGlow.addColorStop(0.5, '#10b98180');
            positionGlow.addColorStop(1, '#10b98100');

            ctx.fillStyle = positionGlow;
            ctx.beginPath();
            ctx.arc(indicatorX, indicatorY, 12, 0, Math.PI * 2);
            ctx.fill();

            ctx.fillStyle = '#10b981';
            ctx.beginPath();
            ctx.arc(indicatorX, indicatorY, 8, 0, Math.PI * 2);
            ctx.fill();

            // Position count text
            ctx.fillStyle = '#FFFFFF';
            ctx.font = 'bold 10px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(node.positions.toString(), indicatorX, indicatorY);
          }
        }
      });

      // Draw sparks
      sparks.forEach(spark => {
        const alpha = spark.life;
        const sparkSize = 8 * spark.life;

        ctx.fillStyle = `${spark.color}${Math.floor(alpha * 255).toString(16).padStart(2, '0')}`;
        ctx.beginPath();
        ctx.arc(spark.x, spark.y, sparkSize, 0, Math.PI * 2);
        ctx.fill();

        // Spark rays
        for (let i = 0; i < 6; i++) {
          const angle = (i * Math.PI * 2) / 6;
          const rayLength = sparkSize * 2 * spark.life;
          ctx.strokeStyle = `${spark.color}${Math.floor(alpha * 200).toString(16).padStart(2, '0')}`;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(spark.x, spark.y);
          ctx.lineTo(
            spark.x + Math.cos(angle) * rayLength,
            spark.y + Math.sin(angle) * rayLength
          );
          ctx.stroke();
        }
      });

      animationFrameRef.current = requestAnimationFrame(draw);
    };

    animationFrameRef.current = requestAnimationFrame(draw);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [nodes, dimensions, hoveredNode, sparks]);

  // Handle mouse move for hover detection
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    let closestNode: AgentNode | null = null;
    let minDistance = Infinity;

    nodes.forEach(node => {
      const distance = Math.sqrt(
        Math.pow(x - node.x, 2) + Math.pow(y - node.y, 2)
      );
      const threshold = node.id === 'coordinator' ? 50 : 40;
      if (distance < threshold && distance < minDistance) {
        minDistance = distance;
        closestNode = node;
      }
    });

    setHoveredNode(closestNode ? closestNode.id : null);
  }, [nodes]);

  return (
    <Box
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHoveredNode(null)}
      sx={{
        position: 'relative',
        width: '100%',
        height: '100vh',
        minHeight: '600px',
        // Simplified, professional dark background
        background: 'linear-gradient(180deg, #0a0a0f 0%, #0f1115 50%, #0a0a0f 100%)',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: '"Orbitron", "Rajdhani", "Inter", sans-serif',
      }}
    >
      {/* Import Google Fonts */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Rajdhani:wght@300;400;500;600;700&display=swap" rel="stylesheet" />

      {/* Beautiful, intricate background - organic and flowing */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: [
            'radial-gradient(ellipse at 20% 30%, rgba(14, 165, 233, 0.03) 0%, transparent 50%)',
            'radial-gradient(ellipse at 80% 70%, rgba(139, 92, 246, 0.03) 0%, transparent 50%)',
            'radial-gradient(ellipse at 50% 50%, rgba(6, 182, 212, 0.02) 0%, transparent 60%)',
          ].join(', '),
          pointerEvents: 'none',
        }}
      />

      {/* Subtle organic mesh pattern */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundImage: `
            radial-gradient(circle at 1px 1px, rgba(14, 165, 233, 0.015) 1px, transparent 0)
          `,
          backgroundSize: '40px 40px',
          pointerEvents: 'none',
          opacity: 0.6,
        }}
      />

      {/* Sapphire dust - more subtle */}
      <SapphireDust intensity={0.2} speed={0.2} size="small" enabled={true} />

      {/* Organic flowing glow at center */}
      <Box
        sx={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '1000px',
          height: '1000px',
          background: 'radial-gradient(circle, rgba(14, 165, 233, 0.04) 0%, rgba(139, 92, 246, 0.02) 40%, transparent 70%)',
          pointerEvents: 'none',
          animation: 'organicPulse 12s ease-in-out infinite',
          '@keyframes organicPulse': {
            '0%, 100%': { opacity: 0.4, transform: 'translate(-50%, -50%) scale(1) rotate(0deg)' },
            '33%': { opacity: 0.6, transform: 'translate(-50%, -50%) scale(1.1) rotate(120deg)' },
            '66%': { opacity: 0.5, transform: 'translate(-50%, -50%) scale(0.95) rotate(240deg)' },
          },
        }}
      />

      {/* Subtle diamond sparkles - less frequent */}
      <DiamondSparkle count={3} duration={5000} size={15} enabled={true} color="#0ea5e9" />

      {/* Canvas for network visualization */}
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
        }}
      />

      {/* Neural pulses */}
      {pulses.map(pulse => (
        <NeuralPulse
          key={pulse.id}
          startX={pulse.startX}
          startY={pulse.startY}
          endX={pulse.endX}
          endY={pulse.endY}
          color={pulse.color}
          duration={pulse.type === 'agent-to-agent' ? 1500 : 2000}
          onComplete={() => handlePulseComplete(pulse.id)}
        />
      ))}

      {/* Node labels with model information */}
      {nodes.map(node => {
        const config = agentConfig[node.type] || { name: node.name, color: node.color, emoji: '🤖', model: 'Unknown' };
        const isCoordinator = node.id === 'coordinator';
        const isHovered = hoveredNode === node.id;

        return (
          <Tooltip
            key={node.id}
            title={
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1, fontSize: '1.1rem', fontFamily: '"Orbitron", sans-serif' }}>
                  {isCoordinator ? 'MCP Coordinator' : config.name}
                </Typography>
                {!isCoordinator && (
                  <>
                    <Typography variant="body2" display="block" sx={{ color: '#FFFFFF', fontWeight: 700, mb: 0.75, fontSize: '1rem', backgroundColor: 'rgba(0, 0, 0, 0.6)', px: 1.5, py: 0.5, borderRadius: 1, border: '1px solid rgba(255, 255, 255, 0.2)' }}>
                      {config.model}
                    </Typography>
                    <Typography variant="body2" display="block" sx={{ fontSize: '0.9rem', mb: 0.5 }}>
                      Status: {node.status}
                    </Typography>
                    <Typography variant="body2" display="block" sx={{ fontSize: '0.9rem', mb: 0.5 }}>
                      Activity: {node.activityScore}
                    </Typography>
                    <Typography variant="body2" display="block" sx={{ fontSize: '0.9rem', mb: 0.5 }}>
                      Messages: {node.messageCount}
                    </Typography>
                    {node.positions !== undefined && node.positions > 0 && (
                      <Typography variant="body2" display="block" sx={{ fontSize: '0.9rem', color: '#10b981', fontWeight: 600, mb: 0.5 }}>
                        🟢 {node.positions} Active Position{node.positions !== 1 ? 's' : ''}
                      </Typography>
                    )}
                    {node.trades !== undefined && node.trades > 0 && (
                      <Typography variant="body2" display="block" sx={{ fontSize: '0.9rem', mb: 0.5 }}>
                        Trades: {node.trades}
                      </Typography>
                    )}
                    {node.pnl !== undefined && (
                      <Typography
                        variant="body2"
                        display="block"
                        sx={{
                          fontSize: '0.9rem',
                          color: node.pnl >= 0 ? '#10b981' : '#ef4444',
                          fontWeight: 600,
                        }}
                      >
                        P&L: {node.pnl >= 0 ? '+' : ''}${node.pnl.toFixed(2)}
                      </Typography>
                    )}
                    {node.status === 'trading' && (
                      <Typography variant="body2" display="block" sx={{ fontSize: '0.9rem', color: '#10b981', fontWeight: 600, mt: 0.5 }}>
                        ⚡ Trading
                      </Typography>
                    )}
                    {node.status === 'analyzing' && (
                      <Typography variant="body2" display="block" sx={{ fontSize: '0.9rem', color: '#f59e0b', fontWeight: 600, mt: 0.5 }}>
                        🔍 Analyzing
                      </Typography>
                    )}
                  </>
                )}
              </Box>
            }
            arrow
            placement={isCoordinator ? 'top' : node.y < dimensions.height / 2 ? 'bottom' : 'top'}
          >
            <Box
              sx={{
                position: 'absolute',
                left: `${node.x}px`,
                top: `${node.y}px`,
                cursor: 'pointer',
                transition: 'transform 0.2s ease',
                transform: isHovered ? 'translate(-50%, -50%) scale(1.15)' : 'translate(-50%, -50%)',
                zIndex: 5,
              }}
            >
              {/* Geometric icon instead of emoji */}
              <Box
                sx={{
                  width: isCoordinator ? 80 : 60,
                  height: isCoordinator ? 80 : 60,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  pointerEvents: 'none',
                  position: 'relative',
                }}
              >
                <AgentGeometricIcon
                  agentId={isCoordinator ? 'coordinator' : node.type}
                  size={isCoordinator ? 80 : 60}
                />
              </Box>
              {/* Always show labels with model info */}
              <Box
                sx={{
                  position: 'absolute',
                  top: isCoordinator ? -50 : -45,
                  left: '50%',
                  transform: 'translateX(-50%)',
                  whiteSpace: 'nowrap',
                  textAlign: 'center',
                  pointerEvents: 'none',
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    color: '#FFFFFF',
                    fontWeight: 700,
                    fontSize: isCoordinator ? '0.9rem' : '0.8rem',
                    textShadow: '0 0 12px rgba(0, 0, 0, 0.9), 0 2px 4px rgba(0, 0, 0, 0.7)',
                    fontFamily: '"Inter", sans-serif',
                    display: 'block',
                    mb: 0.5,
                    letterSpacing: '0.02em',
                    backgroundColor: 'rgba(0, 0, 0, 0.7)',
                    px: 1.5,
                    py: 0.5,
                    borderRadius: 1.5,
                    backdropFilter: 'blur(10px)',
                    border: `1px solid ${node.color}40`,
                    boxShadow: `0 0 20px ${node.color}30`,
                  }}
                >
                  {isCoordinator ? 'MCP Coordinator' : config.name}
                </Typography>
                {!isCoordinator && (
                  <Typography
                    variant="caption"
                    sx={{
                      color: '#FFFFFF',
                      fontWeight: 700,
                      fontSize: '0.7rem',
                      textShadow: '0 0 12px rgba(0, 0, 0, 0.8), 0 2px 4px rgba(0, 0, 0, 0.6)',
                      fontFamily: '"Inter", sans-serif',
                      display: 'block',
                      backgroundColor: 'rgba(0, 0, 0, 0.6)',
                      px: 1,
                      py: 0.25,
                      borderRadius: 1,
                      backdropFilter: 'blur(8px)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      mt: 0.5,
                    }}
                  >
                    {config.model}
                  </Typography>
                )}
              </Box>
            </Box>
          </Tooltip>
        );
      })}


      {/* Stats overlay - simplified and elegant */}
      <Box
        sx={{
          position: 'absolute',
          top: 20,
          left: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: 1,
          zIndex: 20,
        }}
      >
        <Box sx={{ position: 'relative' }}>
          <DiamondSparkle count={1} duration={3000} size={10} enabled={nodes.filter(n => n.id !== 'coordinator' && n.status !== 'idle').length > 0} color="#0ea5e9" />
          <Chip
            label={`${nodes.filter(n => n.id !== 'coordinator' && n.status !== 'idle').length} Active`}
            size="small"
            sx={{
              bgcolor: 'rgba(0, 0, 0, 0.6)',
              color: 'rgba(255, 255, 255, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              fontWeight: 500,
              fontFamily: '"Inter", sans-serif',
              fontSize: '0.75rem',
              backdropFilter: 'blur(10px)',
            }}
          />
          <Chip
            label={`${recentSignals.length} Signals`}
            size="small"
            sx={{
              bgcolor: 'rgba(0, 0, 0, 0.6)',
              color: 'rgba(255, 255, 255, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              fontWeight: 500,
              fontFamily: '"Inter", sans-serif',
              fontSize: '0.75rem',
              backdropFilter: 'blur(10px)',
            }}
          />
          <Chip
            label={`$${nodes
              .filter(n => n.id !== 'coordinator')
              .reduce((sum) => sum + 500, 0)
              .toLocaleString()}`}
            size="small"
            sx={{
              bgcolor: 'rgba(0, 0, 0, 0.6)',
              color: 'rgba(255, 255, 255, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              fontWeight: 500,
              fontFamily: '"Inter", sans-serif',
              fontSize: '0.75rem',
              backdropFilter: 'blur(10px)',
            }}
          />
        </Box>
      </Box>

      {/* Low-profile title - subtle and tasteful */}
      <Box
        sx={{
          position: 'absolute',
          top: { xs: 16, md: 20 },
          left: { xs: 16, md: 24 },
          zIndex: 20,
        }}
      >
        <Typography
          variant="h6"
          sx={{
            fontWeight: 600,
            fontFamily: '"Inter", sans-serif',
            color: 'rgba(255, 255, 255, 0.4)',
            fontSize: { xs: '0.85rem', md: '0.95rem' },
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
          }}
        >
          Sapphire AI
        </Typography>
      </Box>
    </Box>
  );
};

export default NeuralNetwork;
