import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Box, Typography, Tooltip, Chip, Paper } from '@mui/material';
import { useTrading } from '../contexts/TradingContext';
import { AGENT_COLORS } from '../constants/colors';

interface InfrastructureNode {
  id: string;
  name: string;
  type: 'cluster' | 'service' | 'agent' | 'database' | 'cache' | 'coordinator';
  x: number;
  y: number;
  color: string;
  status: 'healthy' | 'warning' | 'error' | 'idle';
  metrics?: {
    cpu?: number;
    memory?: number;
    requests?: number;
    latency?: number;
  };
}

const InfrastructureTopology: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { agentActivities } = useTrading();
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const animationFrameRef = useRef<number>();

  // Update dimensions
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.offsetWidth,
          height: Math.max(800, containerRef.current.offsetHeight),
        });
      }
    };
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  // Calculate infrastructure nodes organized by hierarchy and data flow
  const calculateNodes = useCallback((): InfrastructureNode[] => {
    if (dimensions.width === 0 || dimensions.height === 0) return [];

    const nodes: InfrastructureNode[] = [];
    const centerX = dimensions.width / 2;
    const sectionHeight = dimensions.height / 5; // Adjusted for better spacing

    // Layer Labels (Visual hierarchy indicators)
    nodes.push({
      id: 'layer-1-label',
      name: 'INFRASTRUCTURE LAYER',
      type: 'cluster',
      x: 80,
      y: sectionHeight * 0.8,
      color: '#0EA5E9',
      status: 'healthy',
    });

    nodes.push({
      id: 'layer-2-label',
      name: 'CORE SERVICES LAYER',
      type: 'service',
      x: 80,
      y: sectionHeight * 1.8,
      color: '#8B5CF6',
      status: 'healthy',
    });

    nodes.push({
      id: 'layer-3-label',
      name: 'AI AGENTS LAYER',
      type: 'agent',
      x: 80,
      y: sectionHeight * 2.8,
      color: '#10B981',
      status: 'healthy',
    });

    nodes.push({
      id: 'layer-4-label',
      name: 'EXTERNAL SERVICES LAYER',
      type: 'service',
      x: 80,
      y: sectionHeight * 4.2,
      color: '#F59E0B',
      status: 'healthy',
    });

    // Layer 1: Infrastructure (Top)
    nodes.push({
      id: 'gke-cluster',
      name: 'Google Kubernetes Engine',
      type: 'cluster',
      x: centerX,
      y: sectionHeight,
      color: '#0EA5E9',
      status: 'healthy',
      metrics: { cpu: 45, memory: 62 },
    });

    // Layer 2: Core Services (Middle-Top)
    const coreServices = [
      { id: 'redis', name: 'Redis Cache', type: 'cache' as const, color: '#EF4444', x: centerX - 280, y: sectionHeight * 2 },
      { id: 'cloud-trader', name: 'Cloud Trader API', type: 'service' as const, color: '#0EA5E9', x: centerX, y: sectionHeight * 2 },
      { id: 'mcp-coordinator', name: 'MCP Coordinator', type: 'coordinator' as const, color: '#8B5CF6', x: centerX + 280, y: sectionHeight * 2 },
    ];

    coreServices.forEach(service => {
      nodes.push({
        ...service,
        status: 'healthy',
        metrics: { cpu: Math.random() * 30 + 20, memory: Math.random() * 40 + 30, latency: Math.random() * 50 + 10 },
      });
    });

    // Layer 3: AI Agents (Middle-Bottom) - organized in clear functional groups
    const agentHierarchy = [
      // Analysis Layer (left side - data collection & processing)
      { id: 'volume-microstructure-agent', x: centerX - 350, y: sectionHeight * 2.8, group: 'analysis' },
      { id: 'trend-momentum-agent', x: centerX - 200, y: sectionHeight * 2.8, group: 'analysis' },
      { id: 'financial-sentiment-agent', x: centerX - 200, y: sectionHeight * 3.4, group: 'analysis' },

      // Strategy Layer (center - decision making)
      { id: 'strategy-optimization-agent', x: centerX, y: sectionHeight * 3.1, group: 'strategy' },
      { id: 'market-prediction-agent', x: centerX + 150, y: sectionHeight * 3.1, group: 'strategy' },

      // Execution Layer (right side - trade execution)
      { id: 'vpin-hft', x: centerX + 300, y: sectionHeight * 3.1, group: 'execution' },
    ];

    agentHierarchy.forEach(({ id: agentType, x, y, group }) => {
      const agentActivity = agentActivities.find(a => a.agent_type === agentType);
      const agentColor = AGENT_COLORS[agentType as keyof typeof AGENT_COLORS] || AGENT_COLORS.coordinator;

      nodes.push({
        id: agentType,
        name: agentColor.name,
        type: 'agent',
        x,
        y,
        color: agentColor.primary,
        status: agentActivity?.status === 'active' || agentActivity?.status === 'trading' ? 'healthy' :
                agentActivity?.status === 'analyzing' ? 'warning' : 'idle',
        metrics: {
          cpu: Math.random() * 40 + 15,
          memory: Math.random() * 30 + 20,
          requests: agentActivity?.communication_count || 0,
          latency: Math.random() * 100 + 50,
        },
      });
    });

    // Layer 4: External Services (Bottom)
    const externalServices = [
      { id: 'aster-dex', name: 'Aster DEX Exchange API', color: '#10B981', x: centerX - 250, y: sectionHeight * 4.4 },
      { id: 'vertex-ai', name: 'Google Vertex AI (Gemini)', color: '#F59E0B', x: centerX + 250, y: sectionHeight * 4.4 },
    ];

    externalServices.forEach(service => {
      nodes.push({
        ...service,
        type: 'service',
        status: 'healthy',
        metrics: { latency: service.id === 'aster-dex' ? 45 : 180, requests: service.id === 'aster-dex' ? 120 : 85 },
      });
    });

    return nodes;
  }, [dimensions, agentActivities]);

  const nodes = calculateNodes();

  // Draw infrastructure on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || nodes.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

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

      // Draw connections based on data flow hierarchy
      const drawConnection = (from: InfrastructureNode, to: InfrastructureNode, style: 'solid' | 'dashed' = 'solid', intensity = 0.3) => {
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.lineTo(to.x, to.y);

        const gradient = ctx.createLinearGradient(from.x, from.y, to.x, to.y);
        gradient.addColorStop(0, `${from.color}${Math.floor(intensity * 100).toString(16).padStart(2, '0')}`);
        gradient.addColorStop(1, `${to.color}${Math.floor(intensity * 50).toString(16).padStart(2, '0')}`);

        ctx.strokeStyle = gradient;
        ctx.lineWidth = 2;
        if (style === 'dashed') {
          ctx.setLineDash([8, 4]);
        }
        ctx.stroke();
        ctx.setLineDash([]); // Reset dash
      };

      // Data Flow Connections:
      // 1. Infrastructure → Core Services
      const gkeNode = nodes.find(n => n.id === 'gke-cluster');
      const coreServiceNodes = nodes.filter(n => ['cloud-trader', 'mcp-coordinator', 'redis'].includes(n.id));
      if (gkeNode) {
        coreServiceNodes.forEach(service => drawConnection(gkeNode, service, 'solid', 0.25));
      }

      // 2. External Data → Cloud Trader
      const asterNode = nodes.find(n => n.id === 'aster-dex');
      const traderNode = nodes.find(n => n.id === 'cloud-trader');
      if (asterNode && traderNode) {
        drawConnection(asterNode, traderNode, 'solid', 0.4);
      }

      // 3. Cloud Trader → MCP Coordinator
      const coordinatorNode = nodes.find(n => n.id === 'mcp-coordinator');
      if (traderNode && coordinatorNode) {
        drawConnection(traderNode, coordinatorNode, 'solid', 0.35);
      }

      // 4. MCP Coordinator → AI Agents (hierarchical flow)
      const agentNodes = nodes.filter(n => n.type === 'agent');
      if (coordinatorNode) {
        agentNodes.forEach(agent => drawConnection(coordinatorNode, agent, 'solid', 0.3));
      }

      // 5. AI Agents → Vertex AI (intelligence flow)
      const vertexNode = nodes.find(n => n.id === 'vertex-ai');
      if (vertexNode) {
        agentNodes.forEach(agent => drawConnection(agent, vertexNode, 'dashed', 0.25));
      }

      // 6. Redis ↔ All components (caching layer - bidirectional)
      const redisNode = nodes.find(n => n.id === 'redis');
      if (redisNode) {
        const allOtherNodes = nodes.filter(n => n.id !== 'redis');
        allOtherNodes.forEach(node => {
          ctx.beginPath();
          ctx.moveTo(redisNode.x, redisNode.y);
          ctx.lineTo(node.x, node.y);
          ctx.strokeStyle = `rgba(239, 68, 68, 0.15)`;
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 3]);
          ctx.stroke();
          ctx.setLineDash([]);
        });
      }

      // 7. Agent-to-Agent communication (MCP protocol)
      // Strategy agents communicate with execution agents
      const strategyAgents = agentNodes.filter(n => ['strategy-optimization-agent', 'market-prediction-agent'].includes(n.id));
      const executionAgents = agentNodes.filter(n => ['vpin-hft'].includes(n.id));
      strategyAgents.forEach(strategy => {
        executionAgents.forEach(execution => {
          ctx.beginPath();
          ctx.moveTo(strategy.x, strategy.y);
          ctx.lineTo(execution.x, execution.y);
          ctx.strokeStyle = `rgba(139, 92, 246, 0.2)`;
          ctx.lineWidth = 1.5;
          ctx.setLineDash([4, 2]);
          ctx.stroke();
          ctx.setLineDash([]);
        });
      });

      // Draw nodes
      nodes.forEach(node => {
        const isHovered = hoveredNode === node.id;
        const isLayerLabel = node.id.includes('layer-') && node.id.includes('-label');

        // Special handling for layer labels
        if (isLayerLabel) {
          // Draw layer label background
          ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
          ctx.fillRect(node.x - 120, node.y - 15, 240, 30);

          // Draw layer label text
          ctx.fillStyle = node.color;
          ctx.font = 'bold 14px "Inter", sans-serif';
          ctx.textAlign = 'left';
          ctx.fillText(node.name, node.x - 110, node.y + 5);
          return;
        }

        const size = node.type === 'cluster' ? 80 : node.type === 'coordinator' ? 60 : 50;
        const pulseSize = isHovered ? size * 1.2 : size;

        // Status-based glow
        if (node.status === 'healthy') {
          const glowGradient = ctx.createRadialGradient(
            node.x, node.y, size * 0.5,
            node.x, node.y, size * 2
          );
          glowGradient.addColorStop(0, `${node.color}60`);
          glowGradient.addColorStop(1, `${node.color}00`);
          ctx.fillStyle = glowGradient;
          ctx.beginPath();
          ctx.arc(node.x, node.y, size * 2, 0, Math.PI * 2);
          ctx.fill();
        }

        // Node circle
        const nodeGradient = ctx.createRadialGradient(
          node.x - size * 0.3, node.y - size * 0.3, 0,
          node.x, node.y, size * 0.6
        );
        nodeGradient.addColorStop(0, node.color);
        nodeGradient.addColorStop(1, `${node.color}CC`);
        ctx.fillStyle = nodeGradient;
        ctx.beginPath();
        ctx.arc(node.x, node.y, pulseSize * 0.5, 0, Math.PI * 2);
        ctx.fill();

        // Status ring
        ctx.strokeStyle = node.status === 'healthy' ? node.color : 
                         node.status === 'warning' ? '#F59E0B' : 
                         node.status === 'error' ? '#EF4444' : '#64748B';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(node.x, node.y, size * 0.5 + 5, 0, Math.PI * 2);
        ctx.stroke();
      });

      animationFrameRef.current = requestAnimationFrame(draw);
    };

    animationFrameRef.current = requestAnimationFrame(draw);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [nodes, dimensions, hoveredNode]);

  // Handle mouse move for hover
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    let closestNode: InfrastructureNode | null = null;
    let minDistance = Infinity;

    nodes.forEach(node => {
      const distance = Math.sqrt(Math.pow(x - node.x, 2) + Math.pow(y - node.y, 2));
      const threshold = node.type === 'cluster' ? 60 : 40;
      if (distance < threshold && distance < minDistance) {
        minDistance = distance;
        closestNode = node;
      }
    });

    setHoveredNode(closestNode ? closestNode.id : null);
  }, [nodes]);

  return (
    <Paper
      elevation={0}
      sx={{
        position: 'relative',
        width: '100%',
        minHeight: '800px',
        background: 'linear-gradient(180deg, #0a0a0f 0%, #0f1115 50%, #0a0a0f 100%)',
        border: '1px solid rgba(148, 163, 184, 0.1)',
        borderRadius: 3,
        overflow: 'hidden',
      }}
    >
      <Box
        ref={containerRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredNode(null)}
        sx={{ position: 'relative', width: '100%', height: '100%', minHeight: '800px' }}
      >
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

        {/* Node labels and tooltips */}
        {nodes.map(node => {
          const isHovered = hoveredNode === node.id;
          return (
            <Tooltip
              key={node.id}
              title={
                <Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1, fontSize: '1.1rem' }}>
                    {node.name}
                  </Typography>
                  <Typography variant="body2" sx={{ mb: 0.5, fontSize: '0.9rem' }}>
                    Type: {node.type}
                  </Typography>
                  <Typography variant="body2" sx={{ mb: 0.5, fontSize: '0.9rem' }}>
                    Status: {node.status}
                  </Typography>
                  {node.metrics && (
                    <>
                      {node.metrics.cpu && (
                        <Typography variant="body2" sx={{ fontSize: '0.9rem' }}>
                          CPU: {node.metrics.cpu.toFixed(1)}%
                        </Typography>
                      )}
                      {node.metrics.memory && (
                        <Typography variant="body2" sx={{ fontSize: '0.9rem' }}>
                          Memory: {node.metrics.memory.toFixed(1)}%
                        </Typography>
                      )}
                      {node.metrics.latency && (
                        <Typography variant="body2" sx={{ fontSize: '0.9rem' }}>
                          Latency: {node.metrics.latency.toFixed(0)}ms
                        </Typography>
                      )}
                      {node.metrics.requests && (
                        <Typography variant="body2" sx={{ fontSize: '0.9rem' }}>
                          Requests: {node.metrics.requests}
                        </Typography>
                      )}
                    </>
                  )}
                </Box>
              }
              arrow
              placement={node.y < dimensions.height / 2 ? 'bottom' : 'top'}
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
                <Box
                  sx={{
                    width: node.type === 'cluster' ? 80 : node.type === 'coordinator' ? 60 : 50,
                    height: node.type === 'cluster' ? 80 : node.type === 'coordinator' ? 60 : 50,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    pointerEvents: 'none',
                  }}
                />
                {/* Label */}
                <Box
                  sx={{
                    position: 'absolute',
                    top: node.type === 'cluster' ? -50 : -40,
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
                      color: node.type === 'agent' ? '#FFFFFF' : node.color,
                      fontWeight: 700,
                      fontSize: node.type === 'cluster' ? '0.9rem' : '0.75rem',
                      textShadow: node.type === 'agent' ? `0 0 8px ${node.color}60` : `0 0 10px ${node.color}40`,
                      display: 'block',
                      backgroundColor: node.type === 'agent' ? 'rgba(0,0,0,0.6)' : 'transparent',
                      padding: node.type === 'agent' ? '2px 6px' : '0px',
                      borderRadius: node.type === 'agent' ? '4px' : '0px',
                      border: node.type === 'agent' ? `1px solid ${node.color}40` : 'none',
                    }}
                  >
                    {node.name}
                  </Typography>
                  <Chip
                    label={node.status}
                    size="small"
                    sx={{
                      mt: 0.5,
                      bgcolor: node.status === 'healthy' ? 'rgba(16, 185, 129, 0.2)' :
                               node.status === 'warning' ? 'rgba(245, 158, 11, 0.2)' :
                               node.status === 'error' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(100, 116, 139, 0.2)',
                      color: node.status === 'healthy' ? '#10B981' :
                             node.status === 'warning' ? '#F59E0B' :
                             node.status === 'error' ? '#EF4444' : '#64748B',
                      fontSize: '0.7rem',
                      height: 20,
                    }}
                  />
                </Box>
              </Box>
            </Tooltip>
          );
        })}

        {/* Enhanced Legend */}
        <Paper
          elevation={0}
          sx={{
            position: 'absolute',
            bottom: 20,
            left: 20,
            p: 2,
            bgcolor: 'rgba(15, 23, 42, 0.95)',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(148, 163, 184, 0.2)',
            borderRadius: 2,
            zIndex: 10,
            maxWidth: '300px',
          }}
        >
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 2, fontSize: '1rem', color: '#FFFFFF' }}>
            Data Flow Architecture
          </Typography>

          {/* Component Types */}
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, fontSize: '0.85rem', color: '#E2E8F0' }}>
              Components
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
              {[
                { label: 'GKE Cluster', color: '#0EA5E9', shape: 'circle' },
                { label: 'Core Services', color: '#0EA5E9', shape: 'circle' },
                { label: 'MCP Coordinator', color: '#8B5CF6', shape: 'circle' },
                { label: 'AI Agents', color: '#06B6D4', shape: 'circle' },
                { label: 'Cache Layer', color: '#EF4444', shape: 'circle' },
              ].map((item) => (
                <Box key={item.label} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box
                    sx={{
                      width: 10,
                      height: 10,
                      borderRadius: item.shape === 'circle' ? '50%' : '2px',
                      bgcolor: item.color,
                      boxShadow: `0 0 6px ${item.color}60`,
                    }}
                  />
                  <Typography variant="body2" sx={{ fontSize: '0.8rem', color: '#CBD5E1' }}>
                    {item.label}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>

          {/* Connection Types */}
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, fontSize: '0.85rem', color: '#E2E8F0' }}>
              Data Flow
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
              {[
                { label: 'Infrastructure → Services', style: 'solid', color: '#0EA5E9' },
                { label: 'Market Data Flow', style: 'solid', color: '#10B981' },
                { label: 'AI Intelligence Flow', style: 'dashed', color: '#F59E0B' },
                { label: 'Agent Communication', style: 'dashed', color: '#8B5CF6' },
                { label: 'Cache Connections', style: 'dotted', color: '#EF4444' },
              ].map((item) => (
                <Box key={item.label} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box
                    sx={{
                      width: 20,
                      height: 2,
                      bgcolor: item.color,
                      opacity: 0.7,
                      borderStyle: item.style,
                      borderWidth: item.style === 'dashed' ? '1px 0' : item.style === 'dotted' ? '1px 0' : 'none',
                      borderColor: item.color,
                    }}
                  />
                  <Typography variant="body2" sx={{ fontSize: '0.75rem', color: '#94A3B8' }}>
                    {item.label}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Box>
        </Paper>
      </Box>
    </Paper>
  );
};

export default InfrastructureTopology;

