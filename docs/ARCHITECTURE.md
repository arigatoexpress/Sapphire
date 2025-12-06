# 🏗️ Agent Symphony Architecture

## Table of Contents
- [System Overview](#system-overview)
- [Component Deep Dive](#component-deep-dive)
- [Data Flow](#data-flow)
- [Trading Loop](#trading-loop)
- [Agent System](#agent-system)
- [Infrastructure](#infrastructure)

---

## System Overview

Agent Symphony is a distributed trading system built on a **Conductor-Orchestra** pattern:

```mermaid
C4Context
    title System Context Diagram
    
    Person(trader, "Trader", "Human operator monitoring system")
    System(symphony, "Agent Symphony", "AI-powered multi-agent trading system")
    System_Ext(aster, "Aster Exchange", "Primary trading venue")
    System_Ext(hyperliquid, "Hyperliquid", "HFT venue")
    System_Ext(gemini, "Gemini AI", "Market analysis")
    System_Ext(telegram, "Telegram", "Notifications")
    
    Rel(trader, symphony, "Monitors via Dashboard")
    Rel(symphony, aster, "Trades via API")
    Rel(symphony, hyperliquid, "Trades via API")
    Rel(symphony, gemini, "Analyzes market")
    Rel(symphony, telegram, "Sends alerts")
```

---

## Component Deep Dive

### 1. Symphony Conductor (`symphony_conductor/`)

**Purpose**: Central AI brain that analyzes market conditions and publishes regime signals.

```mermaid
flowchart LR
    subgraph Conductor
        MD[Market Data] --> GA[Gemini Analysis]
        GA --> RC[Regime Classification]
        RC --> PS[Publish to Pub/Sub]
    end
    
    PS --> Topic[symphony-strategy topic]
```

**Key Files**:
- `conductor.py` - Main service loop
- `Dockerfile` - Container configuration

**Market Regimes**:
| Regime | Description | Agent Behavior |
|--------|-------------|----------------|
| `BULL_TRENDING` | Strong uptrend | Aggressive longs |
| `BULL_VOLATILE` | Bullish with swings | Momentum plays |
| `BEAR_TRENDING` | Downtrend | Short positions |
| `BEAR_VOLATILE` | Bearish with swings | Quick exits |
| `RANGE_BOUND` | Sideways market | Mean reversion |

---

### 2. Cloud Trader (`cloud_trader/`)

**Purpose**: Main trading engine managing multiple AI agents on Aster Exchange.

```mermaid
classDiagram
    class MinimalTradingService {
        -_agent_states: Dict
        -_open_positions: Dict
        -_exchange_client: AsterClient
        -_telegram: EnhancedTelegramService
        +start()
        +_run_trading_loop()
        +_execute_agent_trading()
    }
    
    class AgentState {
        +id: str
        +name: str
        +emoji: str
        +active: bool
        +symbols: List
        +daily_loss_breached: bool
    }
    
    class AsterClient {
        +place_order()
        +close_position()
        +get_ticker()
        +position_risk()
    }
    
    MinimalTradingService --> AgentState
    MinimalTradingService --> AsterClient
```

**Key Files**:
| File | Purpose |
|------|---------|
| `trading_service.py` | Core trading loop, agent coordination |
| `position_manager.py` | Position tracking and sync |
| `market_data.py` | Exchange data fetching |
| `enhanced_telegram.py` | AI-powered notifications |
| `client.py` | Aster exchange API client |
| `config.py` | Settings and symbol config |

---

### 3. Trading Dashboard (`trading-dashboard/`)

**Purpose**: Real-time visualization of system performance.

```mermaid
flowchart TB
    subgraph Frontend
        App[React App] --> WS[useWebSocket Hook]
        WS --> State[Dashboard State]
        State --> Charts[Recharts Visualization]
        State --> Grid[Position Grid]
    end
    
    subgraph Backend
        API[FastAPI] --> WSM[WebSocket Manager]
    end
    
    WSM <-->|JSON Updates| WS
```

**Key Features**:
- Real-time P&L tracking
- Agent performance cards
- Position management grid
- Market regime indicator
- Trade history

---

### 4. Symphony Lib (`symphony_lib/`)

**Purpose**: Shared data models and Pub/Sub utilities.

```python
@dataclass
class MarketRegime:
    regime: str              # BULL_TRENDING, BEAR_VOLATILE, etc.
    confidence: float        # 0.0 - 1.0
    trend_strength: float
    volatility_level: float
    timestamp_us: int
```

---

## Data Flow

### Market Regime Flow

```mermaid
sequenceDiagram
    participant C as Conductor
    participant PS as Pub/Sub
    participant CT as Cloud Trader
    participant HT as Hyperliquid Trader
    
    loop Every 5 minutes
        C->>C: Fetch market data
        C->>C: Gemini AI analysis
        C->>PS: Publish MarketRegime
    end
    
    PS-->>CT: Regime update
    PS-->>HT: Regime update
    
    Note over CT: Adjusts agent aggressiveness
    Note over HT: Adjusts position sizing
```

### Trade Execution Flow

```mermaid
sequenceDiagram
    participant TL as Trading Loop
    participant Agent as AI Agent
    participant AI as Gemini AI
    participant EX as Exchange
    participant TG as Telegram
    participant WS as WebSocket
    
    TL->>Agent: Select random agent
    Agent->>Agent: Pick symbol to analyze
    Agent->>AI: Analyze market for signal
    AI-->>Agent: BUY/SELL/HOLD + confidence
    
    alt confidence >= 0.65
        Agent->>EX: Place order
        EX-->>Agent: Order confirmation
        Agent->>TG: Send notification
        Agent->>WS: Broadcast update
    else confidence < 0.65
        Agent->>Agent: Skip trade
    end
```

---

## Trading Loop

The main trading loop runs every 5 seconds:

```mermaid
stateDiagram-v2
    [*] --> UpdateAgentActivity
    UpdateAgentActivity --> CheckPendingOrders
    CheckPendingOrders --> MonitorPositions
    MonitorPositions --> SyncExchange
    SyncExchange --> FetchMarketData
    FetchMarketData --> CheckLiquidationRisk
    CheckLiquidationRisk --> ExecuteNewTrades
    ExecuteNewTrades --> Sleep5s
    Sleep5s --> UpdateAgentActivity
```

### Execute Agent Trading Logic

```mermaid
flowchart TD
    START[Start] --> SELECT[Select Active Agent]
    SELECT --> SYMBOL[Pick Symbol]
    SYMBOL --> CHECK{Has Open Position?}
    
    CHECK -->|Yes| MANAGE[Manage Position]
    MANAGE --> PROFIT{Hit TP/SL?}
    PROFIT -->|Yes| CLOSE[Close Position]
    PROFIT -->|No| HOLD[Hold Position]
    
    CHECK -->|No| ANALYZE[Analyze Market]
    ANALYZE --> SIGNAL{Strong Signal?}
    SIGNAL -->|Yes, conf >= 0.65| OPEN[Open New Trade]
    SIGNAL -->|No| SKIP[Skip]
    
    CLOSE --> END[End Tick]
    HOLD --> END
    OPEN --> END
    SKIP --> END
```

---

## Agent System

### Agent Definitions

```mermaid
graph TB
    subgraph Bull Agents
        A1[🐂 Momentum Hunter<br/>Trend following]
        A2[⚡ Breakout Sniper<br/>Key level breaks]
        A3[🏄 Trend Surfer<br/>Ride extended moves]
    end
    
    subgraph Bear Agents
        B1[🌊 Volatility Harvester<br/>Vol spikes]
        B2[📊 Mean Reversion<br/>Oversold bounces]
    end
    
    subgraph Special Agents
        S1[🧠 Grok Alpha<br/>Advanced reasoning]
        S2[🐋 Whale Tracker<br/>Large player mimicry]
    end
```

### Agent State Machine

```mermaid
stateDiagram-v2
    [*] --> Active
    Active --> DailyLossBreached: Loss limit hit
    DailyLossBreached --> Active: New day
    Active --> Paused: Manual pause
    Paused --> Active: Resume
```

---

## Infrastructure

### Google Cloud Architecture

```mermaid
flowchart TB
    subgraph "Google Cloud Project: sapphire-479610"
        subgraph "Cloud Run Services"
            CR1[cloud-trader<br/>northamerica-northeast1]
            CR2[hyperliquid-trader<br/>northamerica-northeast1]
            CR3[symphony-conductor<br/>northamerica-northeast1]
        end
        
        subgraph "Data Services"
            PS[(Pub/Sub<br/>symphony-strategy)]
            REDIS[(Memorystore Redis)]
            PG[(Cloud SQL PostgreSQL)]
        end
        
        subgraph "Security"
            SM[Secret Manager]
            VPC[VPC Connector<br/>sapphire-conn]
            NAT[Cloud NAT<br/>Static IP]
        end
        
        subgraph "Frontend"
            FB[Firebase Hosting<br/>sapphiretrade.xyz]
        end
    end
    
    CR1 --> PS
    CR2 --> PS
    CR3 --> PS
    CR1 --> REDIS
    CR1 --> PG
    VPC --> CR1
    NAT --> VPC
    SM --> CR1
    SM --> CR2
    SM --> CR3
```

### Deployment Pipeline

```mermaid
flowchart LR
    DEV[Developer] -->|git push| GH[GitHub]
    GH -->|trigger| CB[Cloud Build]
    CB -->|build| GCR[Container Registry]
    GCR -->|deploy| CR[Cloud Run]
```

---

## Security Model

```mermaid
flowchart TB
    subgraph "External"
        USER[User]
        EXCHANGE[Exchange APIs]
    end
    
    subgraph "Google Cloud"
        IAM[IAM Policies]
        SM[Secret Manager]
        VPC[VPC Network]
        
        subgraph "Cloud Run"
            SERVICE[Trading Service]
        end
    end
    
    USER -->|HTTPS| SERVICE
    SERVICE -->|Fetch secrets| SM
    SERVICE -->|VPC Connector| VPC
    VPC -->|Static IP| EXCHANGE
    IAM -->|Authorize| SERVICE
```

---

## Scaling Considerations

| Component | Current | Scalable To |
|-----------|---------|-------------|
| Cloud Trader Instances | 1 | 10+ (stateless) |
| Redis | 1GB | 300GB (Memorystore) |
| PostgreSQL | 10GB | 10TB (Cloud SQL) |
| Pub/Sub | Unlimited | Unlimited |

---

## Monitoring Stack

```mermaid
flowchart LR
    LOGS[Cloud Logging] --> ALERT[Alert Policies]
    METRICS[Prometheus] --> GRAFANA[Grafana Dashboards]
    TRACES[Cloud Trace] --> DEBUG[Debugging]
    TG[Telegram] --> NOTIFY[User Notifications]
```

---

<div align="center">
<sub>Architecture documentation last updated: December 2025</sub>
</div>
