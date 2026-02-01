# Sapphire V2.3 Deployment Verification Checklist

## 🎯 High-Level System Verification

### Phase 1: Infrastructure Health
- [ ] Cloud Run service deployed to asia-southeast1
- [ ] Service is responding to health checks
- [ ] Min 1 instance running
- [ ] No startup errors in logs
- [ ] Memory usage < 6GB (of 8GB allocated)
- [ ] CPU usage normal

**Verification:**
```bash
./monitor_production.sh
```

---

### Phase 2: Platform Connectivity
Verify ALL 5 platforms can connect from Singapore:

- [ ] **Drift (Solana Perps)**
  - Connection established
  - API key valid
  - Can fetch positions
  - Latency < 100ms

- [ ] **Hyperliquid (L1 Perps)**
  - Connection established
  - Wallet authenticated
  - Can query user state
  - Latency < 100ms

- [ ] **Aster (CEX)**
  - ✅ Not geo-blocked from Singapore!
  - Connection established
  - API key valid
  - Can fetch balances
  - Latency < 50ms

- [ ] **Symphony (Monad Treasury)**
  - Connection established
  - Agent manager initialized
  - Can query agents
  - Latency < 200ms

- [ ] **Lighter (Eth L2)**
  - Connection established
  - Can query orderbook
  - Latency < 150ms

**Verification:**
```bash
curl https://sapphire-backend-xxx.run.app/api/platform-router/health | jq
```

---

### Phase 3: Autonomous Learning Agents
Verify all 5 agents initialized:

- [ ] **drift-learner**
  - Agent created
  - Gemini 2.0 Flash model loaded
  - Episodic memory initialized
  - Pattern discovery enabled
  - Exploration rate: 25%

- [ ] **hyperliquid-learner**
  - Agent created
  - Model loaded
  - Learning enabled
  - Exploration rate: 25%

- [ ] **aster-learner**
  - Agent created
  - Model loaded
  - Learning enabled
  - Exploration rate: 30% (more exploration for HFT)

- [ ] **symphony-learner**
  - Agent created
  - Model loaded
  - Learning enabled
  - Exploration rate: 20%

- [ ] **lighter-learner**
  - Agent created
  - Model loaded
  - Learning enabled
  - Exploration rate: 25%

**Verification:**
```bash
curl https://sapphire-backend-xxx.run.app/api/agents/list | jq
```

---

### Phase 4: Trading Functionality
- [ ] Agents can analyze market data
- [ ] Signal generation working
- [ ] Independent execution (no consensus delays)
- [ ] Trades routing to correct platforms
- [ ] Position tracking working
- [ ] Execution speed < 100ms

**Verification:**
```bash
# Check recent activity
curl https://sapphire-backend-xxx.run.app/api/positions | jq

# Check execution metrics
curl https://sapphire-backend-xxx.run.app/api/platform-router/metrics | jq
```

---

### Phase 5: Learning System
- [ ] Trade experiences being recorded
- [ ] Pattern discovery running
- [ ] Win rate tracking enabled
- [ ] Strategy evolution active
- [ ] Memory persistence working

**Verification:**
```bash
curl https://sapphire-backend-xxx.run.app/api/agents/metrics | jq '.[] | {agent, trades, win_rate, patterns}'
```

---

### Phase 6: Performance Targets

**Speed:**
- [ ] Drift decisions: < 100ms
- [ ] Hyperliquid decisions: < 100ms
- [ ] Aster decisions: < 50ms
- [ ] Symphony decisions: < 200ms
- [ ] Lighter decisions: < 150ms

**Learning:**
- [ ] Agents improving from trades
- [ ] Patterns being discovered
- [ ] Win rate trending upward
- [ ] Strategy evolution visible

**Cost:**
- [ ] Cloud Run costs within $55-88/month target
- [ ] No unexpected egress charges
- [ ] Gemini API costs reasonable

---

### Phase 7: Security & Access
- [ ] All secrets in Secret Manager
- [ ] No API keys in logs
- [ ] Circuit breakers functional
- [ ] Rate limiting active
- [ ] Error recovery working

---

### Phase 8: Monitoring & Alerts
- [ ] Cloud Logging enabled
- [ ] Error tracking active
- [ ] Performance metrics collected
- [ ] Telegram notifications working (if enabled)

---

## 🚨 Critical Checks

### Must Be GREEN:
1. ✅ **Aster Trading**: Works from Singapore (not blocked)
2. ✅ **All 5 Platforms**: Connected and operational
3. ✅ **Autonomous Learning**: Agents discovering patterns
4. ✅ **Independent Execution**: < 100ms decisions (no consensus)
5. ✅ **Cost Efficiency**: Singapore pricing competitive

### Red Flags to Watch:
- ❌ Aster connection errors (geo-block)
- ❌ Container startup timeouts
- ❌ Out of memory errors
- ❌ Consensus delays (should be 0 - removed!)
- ❌ API key errors
- ❌ Learning not progressing

---

## 📊 Success Metrics

**Day 1:**
- All platforms connected ✅
- Agents initialized ✅
- First trades executed ✅
- Learning started ✅

**Week 1:**
- 50+ trades per platform
- Patterns discovered (3+ each agent)
- Win rate > 50%
- No major errors

**Month 1:**
- Win rate > 60%
- Consistent profitability
- Strategies evolved
- Cost within budget

---

## 🔧 Troubleshooting

### If Aster is blocked:
```bash
# Verify Singapore deployment
gcloud run services describe sapphire-backend --region=asia-southeast1

# Check egress IP
curl https://sapphire-backend-xxx.run.app/api/debug/ip
```

### If learning not working:
```bash
# Check Gemini API
gcloud logging read "resource.type=cloud_run_revision" --filter="gemini" --limit=20

# Verify model
curl https://sapphire-backend-xxx.run.app/api/agents/list | jq '.[].model'
```

### If trades failing:
```bash
# Check platform router
curl https://sapphire-backend-xxx.run.app/api/platform-router/status | jq

# Check circuit breakers
gcloud logging read "circuit_breaker" --limit=10
```

---

## ✅ Final Verification

```bash
# Run full monitoring
./monitor_production.sh

# Expected output:
# ✅ Service URL active
# ✅ Health check passing
# ✅ 5 platforms connected
# ✅ 5 agents learning
# ✅ Trades executing
# ✅ Patterns discovered
```

**Status: READY FOR PRODUCTION 24/7 AUTONOMOUS TRADING**
