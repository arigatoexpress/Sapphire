# Sapphire OS - Command Deck v2.0

A tactical, Fallout-terminal-inspired dashboard for monitoring and controlling the Sapphire autonomous trading infrastructure.

![Command Deck Preview](docs/preview.png)

## Design Philosophy

### From First Principles

1. **Beauty through Function** - Every visual element serves a purpose
2. **Tactical Aesthetic** - Military/terminal-inspired design creates urgency and focus
3. **Privacy First** - No external trackers, self-hosted, minimal dependencies
4. **Information Density** - Maximum data visibility without clutter

### Key Design Decisions

| Element | Old Dashboard | Vue Dashboard | Command Deck v2 |
|---------|--------------|---------------|-----------------|
| **Theme** | Cyan/Purple Gradient | Green Phosphor | Terminal Green |
| **Layout** | Sidebar + Cards | Top Nav + Views | CSS Grid |
| **Topology** | List View | None | Interactive SVG |
| **Typography** | Inter + JetBrains | JetBrains Mono | JetBrains Mono |
| **Effects** | Glassmorphism | CRT Scanlines | CRT + Glow |

## Features

### 🌐 Network Topology Visualization
- **Interactive SVG diagram** of all infrastructure nodes
- **Real-time status indicators** (online/warning/offline)
- **Animated signal flow** showing data movement
- **Hover interactions** for node details

### 📊 Live Metrics Panel
- **4 key metrics** with sparkline visualizations:
  - 24h PnL with trend indicator
  - Active Signals count
  - Win Rate percentage
  - System Latency
- **Auto-refresh** every 10 seconds
- **Color-coded** values (green/red)

### 📝 Structured Logs
- **Real-time log streaming** from Firestore
- **Filter by level** (All/Signal/Trade/Error)
- **Compact format** with metadata
- **Auto-scroll** with 50-entry buffer

### 💻 Interactive Terminal
- **Command interface** for quick operations
- **Keyboard shortcuts** (Ctrl+K for focus)
- **Built-in commands**:
  - `status` - System overview
  - `nodes` - Network topology
  - `signals` - Active signals
  - `logs` - Log summary
  - `metrics` - Trading metrics
  - `help` - Command list
  - `clear` - Clear terminal

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  HEADER: Brand | UTC Time | Uptime | Signals | Status  │
├──────────────────┬──────────────────┬───────────────────┤
│                  │                  │                   │
│   TOPOLOGY       │    METRICS       │      LOGS         │
│   (Interactive   │   (Sparklines    │   (Structured     │
│    SVG Graph)    │    + Values)     │    Events)        │
│                  │                  │                   │
│  TradingView ──► │  PnL: +2.4% ▲   │  22:45:30 OK      │
│  Windows_PC ───► │  Signals: 12 ▲   │  Signal published │
│  Pub/Sub ─────►  │  Win: 78.5% ▲    │  ETHBTC | abc123  │
│  RARI1/RARI2 ──► │  Latency: 45ms ▼ │                   │
│  Exchanges ◄───  │                  │                   │
│                  │                  │                   │
├──────────────────┴──────────────────┴───────────────────┤
│  TERMINAL: sapphire@command-deck:~$ [input cursor]      │
└─────────────────────────────────────────────────────────┘
```

## Technology Stack

- **Backend**: Flask + Python 3.11
- **Frontend**: Vanilla HTML5 + CSS3 + JavaScript
- **Database**: Firestore (logs + metrics)
- **Deployment**: Cloud Run / Docker
- **Auth**: HTTP Basic Auth

## Deployment

### Local Development

```bash
cd services/workbench/command_deck
pip install -r requirements.txt
python app.py
# Open http://localhost:8082
# Default credentials: sapphire / alpha2024
```

### Cloud Run Deployment

```bash
./scripts/deploy_command_deck.sh
```

Or manually:

```bash
gcloud builds submit --tag gcr.io/sapphire-479610/command-deck
gcloud run deploy command-deck \
    --image gcr.io/sapphire-479610/command-deck \
    --region us-central1 \
    --set-env-vars GCP_PROJECT=sapphire-479610,AUTH_USERNAME=sapphire,AUTH_PASSWORD=yourpassword
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main dashboard |
| `GET /api/status` | Node status overview |
| `GET /api/topology` | Topology data for SVG |
| `GET /api/metrics` | Trading metrics |
| `GET /api/metrics/history` | Historical sparkline data |
| `GET /api/logs` | Structured logs |
| `GET /api/logs/stream` | SSE log stream |
| `POST /api/terminal` | Execute commands |
| `GET /api/dashboard` | Consolidated data |

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl + K` | Focus terminal input |
| `Ctrl + R` | Refresh metrics + topology |
| `Enter` | Execute terminal command |
| `Up/Down` | Terminal history (TODO) |

## Theming

### Color Palette

```css
--terminal: #20C20E;           /* Primary green */
--terminal-bright: #39ff14;    /* Bright green */
--terminal-dim: rgba(32,194,14,0.6);  /* Dimmed */
--terminal-faint: rgba(32,194,14,0.25); /* Background */
--bg-deep: #050805;            /* Deep black-green */
```

### Typography

- **Font**: JetBrains Mono
- **Base size**: 14px
- **Weights**: 300 (light), 400 (normal), 500 (medium), 600 (semibold), 700 (bold)

## Future Enhancements

- [ ] WebSocket for real-time updates
- [ ] Dark/Light theme toggle
- [ ] Mobile-responsive layout
- [ ] Custom alert thresholds
- [ ] Trade execution from UI
- [ ] Historical signal playback
- [ ] Node detail modals
- [ ] Export logs/metrics

## Privacy & Security

- ✅ No external analytics or tracking
- ✅ Self-hosted on Cloud Run
- ✅ Basic authentication
- ✅ No cookies for tracking
- ✅ All data stays in GCP project

---

**Sapphire OS** - Autonomous Trading Infrastructure v2.0
