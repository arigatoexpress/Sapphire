<!-- 13323f0b-b3dd-4419-b391-b8d3a7d693ce 40c6f3d0-17c9-4b88-9dd6-cca2c0b78b4f -->
# SAPPHIRE 2.0 MLOps & VPIN HFT Integration Plan

## 🎯 Executive Summary for Cursor Agent

Execute the **SAPPHIRE 2.0** upgrade by migrating model training and serving to **Vertex AI** and integrating the new, low-latency **VPIN HFT Agent** on a dedicated GKE HFT node pool. The architecture requires synchronization between 5 independent agents via a central `RiskManager` and a robust **Rate Limiting/Fallback** mechanism.

## Phase 0: Setup & Initialization

**INSTRUCTION:** Create the necessary new directories and define the Pub/Sub topics required for inter-service communication.

| Action | File/Component | Details |

| :--- | :--- | :--- |

| **CREATE** | `mlops/pipelines/` | Directory for Kubeflow pipeline definitions |

| **CREATE** | `mlops/training_scripts/` | Directory for agent training scripts |

| **CREATE** | `cloud_trader/agents/` | Directory for agent implementations (if not exists) |

| **DEFINE** | Pub/Sub Topic: `sapphire-vpin-tick-data` | High-frequency stream from Aster DEX to VPIN Agent |

| **DEFINE** | Pub/Sub Topic: `sapphire-vpin-positions` | Low-latency position updates from VPIN Agent to RiskManager |

## Phase 1: Vertex AI MLOps Backbone

**GOAL:** Offload DeepSeek and FinGPT training and serving to Vertex AI for robust MLOps.

### 1.2 Define Vertex AI Training Pipeline

**File**: `mlops/pipelines/training_pipeline.py`

Create Kubeflow pipeline with 4 components:

1. **Data Prep Component**: Load market data from GCS (`gs://sapphireinfinite/training/*.jsonl`)
2. **Train Component**: Execute `mlops/training_scripts/train_agent.py` with agent name and hyperparameters
3. **Evaluate Component**: Evaluate model against holdout set, calculate Sharpe Ratio
4. **Register & Deploy Component**: If Sharpe > 2.0, register in Vertex AI Model Registry and deploy to Vertex AI Endpoint

**Key Implementation**:

- Use `kfp` (Kubeflow Pipelines SDK) to define pipeline
- Components run as containerized tasks
- Model artifacts stored in GCS
- Evaluation metrics logged to Vertex AI Experiments

### 1.3 Create Training Script

**File**: `mlops/training_scripts/train_agent.py`

Script accepts:

- `--agent_name` (deepseek or fingpt)
- `--data_path` (GCS path to training data)
- `--hyperparameters` (JSON string with model params)
- `--output_path` (GCS path for model artifacts)

Outputs trained model artifacts to GCS for registration.

### 1.4 Update Agent Code for Vertex AI Endpoints

**Files**:

- `cloud_trader/service.py` (lines 264-273)
- `cloud_trader/vertex_ai_client.py` (already exists, verify integration)

**Changes**:

- Ensure `TradingService` uses `VertexAIClient` for DeepSeek and FinGPT inference
- Replace any direct LLM endpoint calls with Vertex AI endpoint calls
- Add fallback logic if Vertex AI endpoint is unavailable

### 1.5 Create Endpoint Deployment Script

**File**: `infrastructure/deploy_vertex_endpoints.sh`

Script responsibilities:

- Deploy registered models from Model Registry to Vertex AI Endpoints
- Configure auto-scaling (min 1, max 10 replicas)
- Set up traffic splitting for A/B testing
- Configure endpoint monitoring and alerting

## Phase 2: VPIN HFT Agent Implementation

### 2.1 Create VPIN Core Logic

**File**: `cloud_trader/agents/vpin_hft_agent.py`

**Class Structure**:

```python
class VpinHFTAgent:
    def __init__(self, exchange_client, pubsub_topic, risk_manager_queue):
        # Initialize with exchange client, Pub/Sub topic, risk manager queue
        
    def calculate_vpin(self, tick_data_batch: list) -> float:
        """
        VPIN = (sum(|Vbuy - Vsell|) / sum(Vbuy + Vsell)) * sqrt(N)
    - Vbuy/Vsell determined by tick direction (price change sign)
    - Rolling window calculation for real-time processing
    - Returns VPIN value (0-1 scale, typically 0.1-0.5)
        """
        
    async def execute_trade(self, vpin_signal: float, symbol: str):
        """
        If VPIN > threshold (dynamic, typically 0.3-0.5):
    - Execute aggressive 30x leverage trade
    - Post non-blocking message to RiskManager via Pub/Sub
    - Include position details for portfolio coordination
        """
```

**VPIN Calculation Details**:

- Use rolling window of last 50-100 ticks
- Classify each tick as buy/sell based on price change direction
- Calculate volume imbalance: |Vbuy - Vsell|
- Normalize by total volume and apply sqrt(N) scaling factor

### 2.2 Create Low-Latency Data Streamer

**File**: `mlops/vpin_data_streamer.py`

**Requirements**:

- Subscribe to Aster DEX WebSocket tick stream (`wss://fstream.asterdex.com`)
- Batch ticks (50-100 ticks per batch) for VPIN calculation
- Use asyncio for non-blocking I/O
- Implement reconnection logic with exponential backoff
- Publish tick batches to VPIN agent via in-memory queue

**Integration Points**:

- Connect to `AsterClient` WebSocket interface (if exists) or create new WebSocket client
- Stream all available symbols or filter to high-volume symbols
- Handle WebSocket disconnections gracefully

### 2.3 Integrate VPIN with TradingService

**File**: `cloud_trader/service.py`

**Changes**:

- Add `VpinHFTAgent` to `AGENT_DEFINITIONS` (5th agent):
  ```python
  {
      "id": "vpin-hft",
      "name": "VPIN HFT Agent",
      "model": "VPIN Volatility",
      "emoji": "⚡",
      "symbols": [],  # All symbols
      "margin_allocation": 1000.0,
      "max_leverage_limit": 30.0,
      "specialization": "volatility_hft",
      ...
  }
  ```

- Initialize VPIN agent in `TradingService.__init__()`
- Add VPIN agent to `_agent_states` tracking
- Integrate VPIN trade signals into main trading loop

### 2.4 Update RiskManager for VPIN Integration

**File**: `cloud_trader/risk.py`

**Changes**:

- Add Pub/Sub subscription listener for VPIN position updates
- Update `update_portfolio_risk()` to include VPIN positions
- Adjust maximum loss calculation to $1,250 (25% of $5K total)
- Ensure VPIN's 30x leverage is correctly factored into portfolio margin utilization

## Phase 3: Infrastructure Refactoring

### 3.1 Update GKE Configuration

**File**: `k8s-deployment.yaml` (or create new `k8s-node-pools.yaml`)

**Changes**:

- Define two node pools:
        - `standard-pool`: General purpose (n1-standard-4), runs TradingService pod with 4 standard agents
        - `hft-pool`: High-CPU, network-optimized (n1-highcpu-8), runs VPIN agent pod

**Node Pool Configuration**:

```yaml
# Standard Pool
- name: standard-pool
  machineType: n1-standard-4
  diskSizeGb: 100
  minNodeCount: 2
  maxNodeCount: 5
  
# HFT Pool  
- name: hft-pool
  machineType: n1-highcpu-8
  diskSizeGb: 50
  minNodeCount: 1
  maxNodeCount: 3
  taints:
  - key: hft-workload
      value: "true"
      effect: NoSchedule
```

### 3.2 Create VPIN Pod Deployment

**File**: `k8s-deployment-vpin.yaml` (new file)

**Configuration**:

- Node affinity to `hft-pool` only
- Higher CPU/memory resources (4 CPU, 8Gi memory)
- Dedicated network policies for low latency
- Health checks and readiness probes

### 3.3 Update RiskManager for 5-Agent Ensemble

**File**: `cloud_trader/risk.py` (RiskManager class)

**Changes**:

- Update `__init__()` to track $5,000 total capital (was $4,000)
- Add VPIN position listener via Pub/Sub subscription
- Update `update_portfolio_risk()`:
        - Maximum loss: $1,250 (25% of $5K)
        - Include VPIN positions in total exposure calculation
        - Factor VPIN's 30x leverage into margin utilization

**Code Snippet**:

```python
def __init__(self, settings: Settings):
    self._total_capital = 5000.0  # Updated from 4000.0
    self._max_drawdown = settings.max_drawdown
    self._max_leverage = settings.max_portfolio_leverage
    # Initialize Pub/Sub listener for VPIN positions
    self._vpin_position_listener = None
    
def update_portfolio_risk(self, portfolio: PortfolioState, vpin_positions: Dict[str, Any]) -> None:
    # Include VPIN positions in total exposure
    vpin_exposure = sum(pos.get('notional', 0) * pos.get('leverage', 30) 
                       for pos in vpin_positions.values())
    total_exposure = portfolio.total_exposure + vpin_exposure
    # Check against $1,250 max loss limit
```

### 3.4 Update Agent Allocations

**File**: `risk-orchestrator/src/risk_orchestrator/risk_engine.py`

**Changes**:

- Update `AGENT_ALLOCATIONS` to include VPIN:
  ```python
  AGENT_ALLOCATIONS = {
      "deepseek-v3": 1000.0,
      "fingpt-alpha": 1000.0,
      "lagllama-degen": 1000.0,
      "profit-maximizer": 1000.0,
      "vpin-hft": 1000.0,  # New
  }
  ```


## Phase 4: API Rate Limiting & Intelligent Fallback

### 4.1 Create Rate Limit Manager

**File**: `cloud_trader/rate_limit_manager.py` (new file)

**Class**: `RateLimitManager`

**Responsibilities**:

- Track Aster API rate limits (requests per second/minute)
- Monitor API response headers for rate limit information
- Detect throttling (429 responses)
- Coordinate agent activity to respect limits

**Methods**:

- `check_rate_limit(agent_id: str) -> bool`: Check if agent can make request
- `record_request(agent_id: str, endpoint: str)`: Record API call
- `get_available_capacity() -> Dict[str, int]`: Get remaining API capacity
- `should_throttle_agent(agent_id: str) -> bool`: Determine if agent should be throttled

### 4.2 Implement Fallback Strategy Logic

**File**: `cloud_trader/service.py`

**Changes**:

- Integrate `RateLimitManager` into `TradingService`
- Modify `_tick()` method to check rate limits before agent execution
- Implement fallback priority:

        1. **VPIN HFT** (highest priority, requires real-time data) - throttle first if needed
        2. **Standard agents** (DeepSeek, FinGPT, Lag-Llama, Profit Maximizer) - can use less frequent data
        3. **Fallback mode**: Switch to lower-frequency strategies (e.g., 1-minute candles instead of ticks)

**Fallback Implementation**:

```python
async def _tick(self) -> None:
    # Check API rate limit status
    if self._rate_limit_manager.should_throttle_agent("vpin-hft"):
        # Throttle VPIN, allow standard agents to continue
        await self._execute_standard_agents_only()
    elif self._rate_limit_manager.is_rate_limited():
        # All agents throttled, switch to fallback mode
        await self._execute_fallback_strategies()  # Lower frequency, less API calls
    else:
        # Normal operation - all agents active
        await self._execute_all_agents()
```

### 4.3 Create Fallback Strategy Selector

**File**: `cloud_trader/fallback_strategies.py` (new file)

**Strategies**:

- **Low-frequency momentum**: Use 5-minute candles instead of 1-minute
- **Position holding**: Reduce new position opening, focus on managing existing positions
- **Reduced symbol scanning**: Focus on top 10-20 high-volume symbols only

## Phase 5: Testing & Verification

### 5.1 Unit Tests

- Test VPIN calculation with mock tick data
- Test rate limit manager with various API response scenarios
- Test fallback strategy selection logic

### 5.2 Integration Tests

- Test VPIN agent integration with TradingService
- Test Vertex AI endpoint calls from agents
- Test rate limit fallback behavior end-to-end

### 5.3 Deployment Verification

- Verify all 5 agents are deployed and running
- Verify VPIN agent is on HFT node pool
- Verify Vertex AI endpoints are accessible
- Verify rate limit management is working

## Critical Code Snippets

### VPIN Calculation (Step 2.1)

```python
def calculate_vpin(self, tick_data_batch: list) -> float:
    """Calculate VPIN from tick data batch."""
    if len(tick_data_batch) < 10:
        return 0.0
    
    buy_volume = 0.0
    sell_volume = 0.0
    total_volume = 0.0
    
    for tick in tick_data_batch:
        price_change = tick['price'] - tick.get('prev_price', tick['price'])
        volume = tick.get('volume', 0.0)
        total_volume += volume
        
        if price_change > 0:
            buy_volume += volume
        elif price_change < 0:
            sell_volume += volume
        else:
            # Neutral tick, split volume
            buy_volume += volume / 2
            sell_volume += volume / 2
    
    if total_volume == 0:
        return 0.0
    
    volume_imbalance = abs(buy_volume - sell_volume)
    vpin = (volume_imbalance / total_volume) * math.sqrt(len(tick_data_batch))
    
    return min(vpin, 1.0)  # Cap at 1.0
```

### RiskManager Update (Step 3.3)

```python
def __init__(self, settings: Settings):
    self._max_drawdown = settings.max_drawdown
    self._max_leverage = settings.max_portfolio_leverage
    self._total_capital = 5000.0  # Updated for 5 agents
    self._max_loss = 1250.0  # 25% of $5K
    # Initialize Pub/Sub client for VPIN positions
    self._pubsub_client = PubSubClient(settings)
    self._vpin_positions: Dict[str, Any] = {}
    
def update_portfolio_risk(self, portfolio: PortfolioState) -> None:
    # Include VPIN positions in exposure calculation
    vpin_exposure = sum(
        pos.get('notional', 0) * pos.get('leverage', 30)
        for pos in self._vpin_positions.values()
    )
    total_exposure = portfolio.total_exposure + vpin_exposure
    current_leverage = total_exposure / self._total_capital
    
    # Check maximum loss limit
    unrealized_pnl = portfolio.unrealized_pnl or 0.0
    if unrealized_pnl < -self._max_loss:
        # Emergency: reduce all positions
        return False, "Maximum loss limit exceeded"
    
    return True, ""
```

## Implementation Order

1. **Phase 1.1-1.3**: Set up MLOps infrastructure (pipelines, training scripts)
2. **Phase 2.1-2.2**: Implement VPIN agent and data streamer
3. **Phase 3.1-3.2**: Set up GKE node pools and VPIN deployment
4. **Phase 2.3-2.4**: Integrate VPIN with TradingService and RiskManager
5. **Phase 4.1-4.3**: Implement rate limiting and fallback strategies
6. **Phase 1.4-1.5**: Complete Vertex AI endpoint integration
7. **Phase 5**: Testing and verification