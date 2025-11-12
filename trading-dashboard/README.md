# Sapphire Trading Dashboard

Real-time monitoring interface for the autonomous trading system.

## Features

- **Live Portfolio Tracking**: Real-time account balance and P&L monitoring
- **AI Agent Status**: Activity levels and performance metrics for all trading agents
- **Risk Management**: Position limits and drawdown controls
- **Performance Charts**: Historical portfolio value with multiple timeframes
- **System Health**: Service status and operational metrics

## Technology

- React 18 with TypeScript
- Material-UI component library
- Firebase Hosting for deployment
- Responsive design for mobile and desktop
- Real-time data updates

## Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Deploy to Firebase
npm run deploy
```

## Architecture

The dashboard connects to the trading backend API to display:
- Current portfolio positions and values
- AI agent activity and decision-making
- Trading signals and execution results
- System health and performance metrics

All data is updated in real-time with automatic error handling and connection recovery.
