# Pre-Live Trading Checklist

**Critical verification items before going live with the AI trading system and sharing the site publicly.**

## 1. Paper Trading Mode Verification

- [ ] Verify `ENABLE_PAPER_TRADING=false` for all 6 agents in Kubernetes deployments
- [ ] Check `cloud_trader/config.py` default is `False` for production
- [ ] Confirm no paper trading flags in environment variables
- [ ] Test that live trading mode is actually enabled (verify trades execute on real exchange)

## 2. Capital Allocation Verification

- [ ] Verify each agent has exactly $500 trading capital allocated
- [ ] Check `risk-orchestrator/src/risk_orchestrator/risk_engine.py` AGENT_ALLOCATIONS matches: 6 agents × $500 = $3,000 total
- [ ] Verify risk limits: MAX_DRAWDOWN_PCT=10%, MAX_PER_TRADE_PCT=4%, MIN_MARGIN_BUFFER_USDT=100
- [ ] Confirm capital allocation is enforced and cannot be exceeded
- [ ] Test that agents cannot trade beyond their allocated capital

## 3. API Credentials and Connectivity

- [ ] Verify Aster DEX API credentials in Kubernetes secrets (`aster-dex-credentials`)
- [ ] Test API connectivity from all agent pods
- [ ] Confirm IP whitelisting on Aster DEX for all GKE node IPs:
  - Static IP: 34.144.213.188
  - Node IPs: 35.188.43.171, 104.154.90.215, 34.9.133.10
- [ ] Verify SSL certificate handling is working correctly
- [ ] Test order placement and cancellation on testnet/small amounts

## 4. Kill Switch and Emergency Procedures

- [ ] Test Telegram kill switch command: `/kill_switch activate`
- [ ] Verify kill switch deactivation works
- [ ] Confirm emergency stop procedures are documented
- [ ] Test circuit breakers and risk limit enforcement
- [ ] Verify kill switch stops all trading activity immediately
- [ ] Document kill switch procedure for team members

## 5. Risk Management Settings

- [ ] Verify `safety-checks.yaml` limits: max_position_size=5%, max_portfolio_leverage=2.0, max_daily_loss=10%
- [ ] Check risk engine is enforcing per-agent allocation caps
- [ ] Confirm drawdown monitoring is active
- [ ] Verify margin buffer checks are working
- [ ] Test that risk limits actually prevent trades when exceeded
- [ ] Verify position sizing calculations are correct

## 6. Monitoring and Alerting

- [ ] Verify Telegram notifications are working for trades
- [ ] Check Prometheus metrics are being collected
- [ ] Confirm health check endpoints are responding (`/healthz`)
- [ ] Test alerting for high error rates, service downtime, risk limit breaches
- [ ] Verify all 6 agent pods are reporting metrics
- [ ] Test alert notifications are received in real-time

## 7. Frontend and Public Site

- [ ] Verify frontend shows only bot trading capital ($3,000), not account balances
- [ ] Confirm all sensitive information is properly delayed (1-minute lag for trades)
- [ ] Test site accessibility at `sapphiretrade.xyz`
- [ ] Verify no personal account information is exposed
- [ ] Check that neural network visualization is working correctly
- [ ] Verify all pages load without errors
- [ ] Test responsive design on mobile devices

## 8. System Health and Stability

- [ ] Check all 6 agent pods are running and healthy
- [ ] Verify MCP coordinator is operational
- [ ] Confirm Redis connectivity
- [ ] Test BigQuery streaming is working
- [ ] Verify no crash loops or OOMKilled pods
- [ ] Check all services have proper resource limits
- [ ] Verify auto-scaling is configured correctly
- [ ] Test system recovery after pod restarts

## 9. Security and Access Control

- [ ] Verify API keys are in Kubernetes secrets, not in code
- [ ] Check network policies are enforcing traffic isolation
- [ ] Confirm RBAC permissions are correctly configured
- [ ] Verify no hardcoded credentials in codebase
- [ ] Test that secrets are properly mounted in pods
- [ ] Verify HTTPS is enabled for all external endpoints
- [ ] Check that admin API token is properly secured

## 10. Documentation and Runbooks

- [ ] Verify `OPERATIONAL_RUNBOOK.md` is up to date
- [ ] Confirm emergency procedures are documented
- [ ] Check deployment procedures are documented
- [ ] Verify troubleshooting guides are available
- [ ] Document all environment variables and their purposes
- [ ] Create quick reference guide for common operations
- [ ] Document rollback procedures

---

## Additional Pre-Launch Checks

### Performance Testing
- [ ] Test system under normal load
- [ ] Verify response times are acceptable
- [ ] Check memory and CPU usage are within limits
- [ ] Test concurrent agent operations

### Data Integrity
- [ ] Verify trade data is being logged correctly
- [ ] Check that portfolio calculations are accurate
- [ ] Confirm historical data is being stored properly
- [ ] Test data backup and recovery procedures

### User Experience
- [ ] Test all navigation links work correctly
- [ ] Verify charts and visualizations render properly
- [ ] Check that real-time updates are working
- [ ] Test error messages are user-friendly
- [ ] Verify loading states are displayed appropriately

---

**Last Updated:** [Date]
**Reviewed By:** [Name]
**Status:** ⚠️ Pre-Launch - Not Yet Live

