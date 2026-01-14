# 📊 Trading Dashboard

Real-time visualization dashboard for Agent Symphony trading system.

## Overview

A modern React application providing:
- Real-time P&L tracking
- Agent performance monitoring
- Position management
- Market regime visualization
- Trade history

## Tech Stack

- **Framework**: React 18 + TypeScript
- **Styling**: Tailwind CSS + MUI
- **Charts**: Recharts
- **State**: React Hooks + WebSocket
- **Build**: Vite
- **Deployment**: Firebase Hosting

## Quick Start

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

## Project Structure

```
src/
├── components/          # UI components
│   ├── AgentCard.tsx    # Agent performance card
│   ├── PositionGrid.tsx # Position table
│   └── PnLChart.tsx     # P&L visualization
├── hooks/
│   └── useWebSocket.ts  # Real-time data hook
├── pages/
│   └── DualityDashboard.tsx  # Main dashboard
├── lib/
│   └── firebase.ts      # Firebase config
└── App.tsx              # Root component
```

## Environment Variables

Create `.env.local` for development:

```bash
VITE_API_URL=http://localhost:8080
VITE_FIREBASE_API_KEY=your_key
VITE_FIREBASE_PROJECT_ID=sapphire-479610
```

For production, create `.env.production`:

```bash
VITE_API_URL=https://cloud-trader-267358751314.europe-west1.run.app
VITE_FIREBASE_API_KEY=your_key
VITE_FIREBASE_PROJECT_ID=sapphire-479610
```

## WebSocket Connection

The dashboard connects to the backend via WebSocket:

```typescript
// Automatic connection via useWebSocket hook
const { data, connected, error } = useDashboardWebSocket();
```

## Deployment

### Firebase Hosting

```bash
npm run build
firebase deploy --only hosting --project sapphire-479610
```

### Custom Domain

The dashboard is accessible at:
- https://sapphiretrade.xyz (custom domain)
- https://sapphire-479610.web.app (Firebase default)

## Screenshots

_Dashboard showing real-time trading data and agent performance._
