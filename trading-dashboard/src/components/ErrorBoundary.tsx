import { Component, ErrorInfo, ReactNode } from 'react';
import { getApiUrl } from '../utils/apiConfig';
import { Box, Typography, Button, Paper, Alert, Chip, Collapse, IconButton } from '@mui/material';
import { ErrorOutline, Refresh, ExpandMore, ContentCopy, Home } from '@mui/icons-material';

/**
 * Enhanced Error Boundary Component
 *
 * First Principle: Errors should be actionable, not just displayed.
 *
 * This component:
 * 1. Catches all React rendering errors
 * 2. Categorizes errors to provide specific recovery suggestions
 * 3. Logs errors to console (and optionally backend)
 * 4. Provides multiple recovery actions
 */

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  showDetails: boolean;
  copied: boolean;
}

// Error categories for better recovery suggestions
type ErrorCategory = 'network' | 'auth' | 'data' | 'render' | 'unknown';

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
    showDetails: false,
    copied: false,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('🔴 ErrorBoundary caught error:', error, errorInfo);
    this.setState({ error, errorInfo });

    // Log to backend (if available)
    this.logErrorToBackend(error, errorInfo);
  }

  private logErrorToBackend = async (error: Error, errorInfo: ErrorInfo) => {
    try {
      const apiUrl = getApiUrl();
      await fetch(`${apiUrl}/api/log-client-error`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: error.message,
          stack: error.stack,
          componentStack: errorInfo.componentStack,
          url: window.location.href,
          timestamp: new Date().toISOString(),
        }),
      }).catch(() => { }); // Silently fail - we don't want error logging to cause more errors
    } catch {
      // Ignore logging failures
    }
  };

  private categorizeError = (): ErrorCategory => {
    const message = this.state.error?.message?.toLowerCase() || '';
    const stack = this.state.error?.stack?.toLowerCase() || '';

    if (message.includes('network') || message.includes('fetch') || message.includes('failed to fetch')) {
      return 'network';
    }
    if (message.includes('auth') || message.includes('token') || message.includes('unauthorized')) {
      return 'auth';
    }
    if (message.includes('undefined') || message.includes('null') || message.includes('cannot read')) {
      return 'data';
    }
    if (stack.includes('render') || stack.includes('component')) {
      return 'render';
    }
    return 'unknown';
  };

  private getRecoverySuggestion = (category: ErrorCategory): { title: string; steps: string[] } => {
    switch (category) {
      case 'network':
        return {
          title: 'Network Connection Issue',
          steps: [
            'Check your internet connection',
            'The backend server may be temporarily unavailable',
            'Try refreshing the page in a few seconds',
          ],
        };
      case 'auth':
        return {
          title: 'Authentication Issue',
          steps: [
            'Your session may have expired',
            'Try logging out and logging back in',
            'Clear browser cookies if the issue persists',
          ],
        };
      case 'data':
        return {
          title: 'Data Loading Issue',
          steps: [
            'Some data failed to load correctly',
            'This may be a temporary issue',
            'Try refreshing the page',
          ],
        };
      case 'render':
        return {
          title: 'Display Issue',
          steps: [
            'A component failed to render',
            'This may be a temporary glitch',
            'Click "Try Again" or refresh the page',
          ],
        };
      default:
        return {
          title: 'Unexpected Error',
          steps: [
            'An unexpected error occurred',
            'Try refreshing the page',
            'If the issue persists, contact support',
          ],
        };
    }
  };

  private handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null, showDetails: false });
  };

  private handleCopyError = () => {
    const errorText = `Error: ${this.state.error?.message}\n\nStack: ${this.state.error?.stack}`;
    navigator.clipboard.writeText(errorText).then(() => {
      this.setState({ copied: true });
      setTimeout(() => this.setState({ copied: false }), 2000);
    });
  };

  private toggleDetails = () => {
    this.setState(prev => ({ showDetails: !prev.showDetails }));
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const category = this.categorizeError();
      const suggestion = this.getRecoverySuggestion(category);

      return (
        <Box
          display="flex"
          flexDirection="column"
          alignItems="center"
          justifyContent="center"
          minHeight="400px"
          p={3}
          sx={{ background: 'linear-gradient(135deg, #0a0b10 0%, #1a1b26 100%)' }}
        >
          <Paper
            elevation={3}
            sx={{
              p: 4,
              maxWidth: 600,
              width: '100%',
              textAlign: 'center',
              background: 'rgba(26, 27, 38, 0.95)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255,255,255,0.1)',
            }}
          >
            <ErrorOutline sx={{ fontSize: 64, color: '#f87171', mb: 2 }} />

            <Typography variant="h5" gutterBottom sx={{ color: '#f87171' }}>
              {suggestion.title}
            </Typography>

            <Chip
              label={category.toUpperCase()}
              size="small"
              sx={{ mb: 2, bgcolor: 'rgba(248,113,113,0.2)', color: '#f87171' }}
            />

            <Alert
              severity="info"
              sx={{
                mb: 3,
                textAlign: 'left',
                bgcolor: 'rgba(59,130,246,0.1)',
                '& .MuiAlert-icon': { color: '#60a5fa' }
              }}
            >
              <Typography variant="body2" component="div">
                <strong>Recovery Steps:</strong>
                <ol style={{ margin: '8px 0 0 0', paddingLeft: 20 }}>
                  {suggestion.steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </Typography>
            </Alert>

            <Box display="flex" gap={2} justifyContent="center" flexWrap="wrap">
              <Button
                variant="contained"
                startIcon={<Refresh />}
                onClick={this.handleRetry}
                sx={{
                  bgcolor: '#3b82f6',
                  '&:hover': { bgcolor: '#2563eb' }
                }}
              >
                Try Again
              </Button>
              <Button
                variant="outlined"
                startIcon={<Home />}
                onClick={() => window.location.href = '/'}
                sx={{ borderColor: 'rgba(255,255,255,0.3)', color: '#94a3b8' }}
              >
                Go Home
              </Button>
              <Button
                variant="outlined"
                onClick={() => window.location.reload()}
                sx={{ borderColor: 'rgba(255,255,255,0.3)', color: '#94a3b8' }}
              >
                Reload Page
              </Button>
            </Box>

            {/* Technical Details (Collapsible) */}
            <Box mt={3}>
              <Button
                size="small"
                onClick={this.toggleDetails}
                endIcon={<ExpandMore sx={{
                  transform: this.state.showDetails ? 'rotate(180deg)' : 'none',
                  transition: 'transform 0.3s'
                }} />}
                sx={{ color: '#64748b' }}
              >
                Technical Details
              </Button>
              <Collapse in={this.state.showDetails}>
                <Paper
                  sx={{
                    mt: 2,
                    p: 2,
                    bgcolor: 'rgba(0,0,0,0.3)',
                    textAlign: 'left',
                    position: 'relative'
                  }}
                >
                  <IconButton
                    size="small"
                    onClick={this.handleCopyError}
                    sx={{ position: 'absolute', top: 8, right: 8, color: '#64748b' }}
                  >
                    <ContentCopy fontSize="small" />
                  </IconButton>
                  {this.state.copied && (
                    <Chip
                      label="Copied!"
                      size="small"
                      sx={{ position: 'absolute', top: 8, right: 48, bgcolor: '#22c55e' }}
                    />
                  )}
                  <Typography variant="caption" component="pre" sx={{
                    color: '#94a3b8',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    fontSize: '11px',
                    maxHeight: 200,
                    overflow: 'auto'
                  }}>
                    {this.state.error?.message}
                    {'\n\n'}
                    {this.state.error?.stack?.slice(0, 500)}
                  </Typography>
                </Paper>
              </Collapse>
            </Box>
          </Paper>
        </Box>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
