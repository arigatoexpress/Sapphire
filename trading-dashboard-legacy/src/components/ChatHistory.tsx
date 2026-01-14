import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  Chip,
  TextField,
  Button,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  CircularProgress,
  Alert,
  AlertTitle,
  Divider,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import {
  History,
  Download,
  Refresh,
  FilterList,
  Close,
  Psychology,
  TrendingUp,
  Assessment,
  Security,
  Message,
} from '@mui/icons-material';
// useTrading is not used here, removing broken import

interface ChatMessage {
  id: string;
  timestamp: string;
  agent_id: string;
  agent_name: string;
  agent_type: string;
  message: string;
  message_type: string;
  confidence?: number;
  metadata?: Record<string, any>;
}

import { getApiUrl } from '../utils/apiConfig';

const ChatHistory: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    limit: 100,
    agent_type: 'all' as string,
    start_time: '',
    end_time: '',
  });
  const [statistics, setStatistics] = useState<any>(null);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState<'jsonl' | 'json'>('jsonl');

  const API_BASE_URL = getApiUrl();

  const fetchChatHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        limit: filters.limit.toString(),
      });

      if (filters.agent_type !== 'all') {
        params.append('agent_type', filters.agent_type);
      }
      if (filters.start_time) {
        params.append('start_time', filters.start_time);
      }
      if (filters.end_time) {
        params.append('end_time', filters.end_time);
      }

      const response = await fetch(`${API_BASE_URL}/chat/history?${params}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch chat history: ${response.statusText}`);
      }

      const data = await response.json();
      setMessages(data.messages || []);
    } catch (err) {
      const error = err as Error;
      setError(error.message);
      console.error('Failed to fetch chat history:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchStatistics = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.start_time) {
        params.append('start_time', filters.start_time);
      }
      if (filters.end_time) {
        params.append('end_time', filters.end_time);
      }

      const response = await fetch(`${API_BASE_URL}/chat/statistics?${params}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch statistics: ${response.statusText}`);
      }

      const data = await response.json();
      setStatistics(data);
    } catch (err) {
      console.error('Failed to fetch statistics:', err);
    }
  };

  useEffect(() => {
    fetchChatHistory();
    fetchStatistics();
  }, [filters.limit, filters.agent_type]);

  const handleExport = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/history?limit=10000&${new URLSearchParams({
        agent_type: filters.agent_type !== 'all' ? filters.agent_type : '',
        start_time: filters.start_time || '',
        end_time: filters.end_time || '',
      })}`);

      if (!response.ok) {
        throw new Error('Failed to export chat history');
      }

      const data = await response.json();
      const messages = data.messages || [];

      let content = '';
      let filename = '';
      let mimeType = '';

      if (exportFormat === 'jsonl') {
        content = messages.map((msg: ChatMessage) => JSON.stringify(msg)).join('\n');
        filename = `chat_history_${new Date().toISOString().split('T')[0]}.jsonl`;
        mimeType = 'application/jsonl';
      } else {
        content = JSON.stringify(messages, null, 2);
        filename = `chat_history_${new Date().toISOString().split('T')[0]}.json`;
        mimeType = 'application/json';
      }

      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);

      setExportDialogOpen(false);
    } catch (err) {
      console.error('Failed to export chat history:', err);
      alert('Failed to export chat history');
    }
  };

  const getAgentColor = (agentType: string) => {
    const colors: Record<string, string> = {
      'trend-momentum-agent': '#06b6d4',
      'strategy-optimization-agent': '#8b5cf6',
      'financial-sentiment-agent': '#ef4444',
      'market-prediction-agent': '#f59e0b',
      'volume-microstructure-agent': '#ec4899',
      'vpin-hft': '#06b6d4',
    };
    return colors[agentType] || '#8b5cf6';
  };

  const getMessageIcon = (type: string) => {
    switch (type) {
      case 'trade_idea': return <TrendingUp sx={{ fontSize: 16 }} />;
      case 'market_analysis': return <Assessment sx={{ fontSize: 16 }} />;
      case 'strategy_discussion': return <Psychology sx={{ fontSize: 16 }} />;
      case 'risk_update': return <Security sx={{ fontSize: 16 }} />;
      default: return <Message sx={{ fontSize: 16 }} />;
    }
  };

  return (
    <Paper
      elevation={0}
      sx={{
        background: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(24px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: 3,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 3,
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(236, 72, 153, 0.1))',
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Box
              sx={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 16px rgba(139, 92, 246, 0.3)',
              }}
            >
              <History sx={{ color: 'white', fontSize: 24 }} />
            </Box>
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 700, color: '#FFFFFF', mb: 0.5 }}>
                Agent Chat History
              </Typography>
              <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>
                Historical log of all agent communications
              </Typography>
            </Box>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={() => {
                fetchChatHistory();
                fetchStatistics();
              }}
              sx={{
                borderColor: 'rgba(139, 92, 246, 0.5)',
                color: '#8b5cf6',
                '&:hover': {
                  borderColor: '#8b5cf6',
                  bgcolor: 'rgba(139, 92, 246, 0.1)',
                },
              }}
            >
              Refresh
            </Button>
            <Button
              variant="contained"
              startIcon={<Download />}
              onClick={() => setExportDialogOpen(true)}
              sx={{
                bgcolor: 'rgba(139, 92, 246, 0.8)',
                '&:hover': {
                  bgcolor: '#8b5cf6',
                },
              }}
            >
              Export
            </Button>
          </Box>
        </Box>

        {/* Statistics */}
        {statistics && (
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Chip
              label={`Total: ${statistics.total_messages || 0} messages`}
              sx={{ bgcolor: 'rgba(6, 182, 212, 0.2)', color: '#06b6d4', fontWeight: 600 }}
            />
            {statistics.time_range && (
              <Chip
                label={`From: ${new Date(statistics.time_range.start).toLocaleDateString()}`}
                sx={{ bgcolor: 'rgba(16, 185, 129, 0.2)', color: '#10b981', fontWeight: 600 }}
              />
            )}
          </Box>
        )}

        {/* Filters */}
        <Box sx={{ display: 'flex', gap: 2, mt: 3, flexWrap: 'wrap' }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel sx={{ color: 'rgba(255, 255, 255, 0.7)' }}>Agent Type</InputLabel>
            <Select
              value={filters.agent_type}
              onChange={(e) => setFilters({ ...filters, agent_type: e.target.value })}
              label="Agent Type"
              sx={{
                color: '#FFFFFF',
                '& .MuiOutlinedInput-notchedOutline': {
                  borderColor: 'rgba(255, 255, 255, 0.2)',
                },
              }}
            >
              <MenuItem value="all">All Agents</MenuItem>
              <MenuItem value="trend-momentum-agent">Trend Momentum</MenuItem>
              <MenuItem value="strategy-optimization-agent">Strategy Optimization</MenuItem>
              <MenuItem value="financial-sentiment-agent">Financial Sentiment</MenuItem>
              <MenuItem value="market-prediction-agent">Market Prediction</MenuItem>
              <MenuItem value="volume-microstructure-agent">Volume Microstructure</MenuItem>
              <MenuItem value="vpin-hft">VPIN HFT</MenuItem>
            </Select>
          </FormControl>
          <TextField
            size="small"
            type="number"
            label="Limit"
            value={filters.limit}
            onChange={(e) => setFilters({ ...filters, limit: parseInt(e.target.value) || 100 })}
            sx={{ minWidth: 100 }}
          />
          <TextField
            size="small"
            type="datetime-local"
            label="Start Time"
            value={filters.start_time}
            onChange={(e) => setFilters({ ...filters, start_time: e.target.value })}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            size="small"
            type="datetime-local"
            label="End Time"
            value={filters.end_time}
            onChange={(e) => setFilters({ ...filters, end_time: e.target.value })}
            InputLabelProps={{ shrink: true }}
          />
        </Box>
      </Box>

      {/* Messages List */}
      <Box
        sx={{
          maxHeight: '600px',
          overflowY: 'auto',
          '&::-webkit-scrollbar': {
            width: '6px',
          },
          '&::-webkit-scrollbar-track': {
            background: 'rgba(139, 92, 246, 0.1)',
          },
          '&::-webkit-scrollbar-thumb': {
            background: 'rgba(139, 92, 246, 0.3)',
            borderRadius: '3px',
          },
        }}
      >
        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress />
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ m: 2 }}>
            <AlertTitle>Error</AlertTitle>
            {error}
          </Alert>
        )}

        {!loading && !error && messages.length === 0 && (
          <Box sx={{ p: 4, textAlign: 'center' }}>
            <History sx={{ fontSize: 48, color: 'rgba(255, 255, 255, 0.3)', mb: 2 }} />
            <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.6)' }}>
              No chat history found. Start trading to see agent communications!
            </Typography>
          </Box>
        )}

        {!loading && !error && messages.length > 0 && (
          <List sx={{ p: 0 }}>
            {messages.map((msg, index) => (
              <React.Fragment key={msg.id}>
                <ListItem
                  sx={{
                    p: 2,
                    background: index % 2 === 0 ? 'rgba(255, 255, 255, 0.02)' : 'transparent',
                    '&:hover': {
                      background: 'rgba(139, 92, 246, 0.1)',
                    },
                  }}
                >
                  <ListItemAvatar>
                    <Avatar
                      sx={{
                        bgcolor: `${getAgentColor(msg.agent_type)}20`,
                        border: `2px solid ${getAgentColor(msg.agent_type)}`,
                        width: 40,
                        height: 40,
                      }}
                    >
                      {msg.agent_type === 'trend-momentum-agent' ? '🎯' :
                        msg.agent_type === 'strategy-optimization-agent' ? '🧠' :
                          msg.agent_type === 'financial-sentiment-agent' ? '💭' :
                            msg.agent_type === 'market-prediction-agent' ? '🔮' :
                              msg.agent_type === 'volume-microstructure-agent' ? '📊' :
                                msg.agent_type === 'vpin-hft' ? '⚡' : '🤖'}
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                        <Typography
                          variant="subtitle2"
                          sx={{
                            fontWeight: 700,
                            color: getAgentColor(msg.agent_type),
                          }}
                        >
                          {msg.agent_name}
                        </Typography>
                        <Chip
                          icon={getMessageIcon(msg.message_type)}
                          label={msg.message_type.replace('_', ' ').toUpperCase()}
                          size="small"
                          sx={{
                            height: 20,
                            fontSize: '0.65rem',
                            bgcolor: `${getAgentColor(msg.message_type)}20`,
                            color: getAgentColor(msg.agent_type),
                            border: `1px solid ${getAgentColor(msg.agent_type)}40`,
                          }}
                        />
                        {msg.confidence && (
                          <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.6)' }}>
                            {(msg.confidence * 100).toFixed(0)}% confidence
                          </Typography>
                        )}
                      </Box>
                    }
                    secondary={
                      <Box>
                        <Typography variant="body2" sx={{ color: 'rgba(255, 255, 255, 0.9)', mb: 1, lineHeight: 1.5 }}>
                          {msg.message}
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'rgba(255, 255, 255, 0.5)' }}>
                          {new Date(msg.timestamp).toLocaleString()}
                        </Typography>
                      </Box>
                    }
                  />
                </ListItem>
                {index < messages.length - 1 && <Divider sx={{ borderColor: 'rgba(255, 255, 255, 0.05)' }} />}
              </React.Fragment>
            ))}
          </List>
        )}
      </Box>

      {/* Export Dialog */}
      <Dialog open={exportDialogOpen} onClose={() => setExportDialogOpen(false)}>
        <DialogTitle>Export Chat History</DialogTitle>
        <DialogContent>
          <FormControl fullWidth sx={{ mt: 2 }}>
            <InputLabel>Export Format</InputLabel>
            <Select
              value={exportFormat}
              onChange={(e) => setExportFormat(e.target.value as 'jsonl' | 'json')}
              label="Export Format"
            >
              <MenuItem value="jsonl">JSONL (one message per line)</MenuItem>
              <MenuItem value="json">JSON (formatted array)</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExportDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleExport} variant="contained">
            Export
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default ChatHistory;
