# Pre-Live Trading Checklist

This comprehensive checklist must be completed before enabling live trading with real funds. All items must be verified and checked off by authorized personnel.

## 1. Paper Trading Mode Verification

- [ ] Verify `ENABLE_PAPER_TRADING=false` for all 6 agents in Kubernetes deployments
- [ ] Check `cloud_trader/config.py` default is `False` for production
- [ ] Confirm no paper trading flags in environment variables
- [ ] Test that agents are connecting to live Aster DEX APIs (not testnet)

## 2. Capital Allocation Verification

- [ ] Verify each agent has exactly $500 trading capital allocated
- [ ] Check `risk-orchestrator/src/risk_orchestrator/risk_engine.py` AGENT_ALLOCATIONS matches: 6 agents × $500 = $3,000 total
- [ ] Verify risk limits: MAX_DRAWDOWN_PCT=10%, MAX_PER_TRADE_PCT=4%, MIN_MARGIN_BUFFER_USDT=100
- [ ] Confirm capital allocation is correctly distributed across all 6 agents

## 3. API Credentials and Connectivity

- [ ] Verify Aster DEX API credentials in Kubernetes secrets (`aster-dex-credentials`)
- [ ] Test API connectivity from all agent pods using real credentials
- [ ] Confirm IP whitelisting on Aster DEX for all GKE node IPs
- [ ] Verify SSL certificate handling is working correctly for all API calls

## 4. Kill Switch and Emergency Procedures

- [ ] Test Telegram kill switch command: `/kill_switch activate`
- [ ] Verify kill switch deactivation works: `/kill_switch deactivate`
- [ ] Confirm emergency stop procedures are documented and accessible
- [ ] Test circuit breakers and risk limit enforcement across all agents

## 5. Risk Management Settings

- [ ] Verify `safety-checks.yaml` limits: max_position_size=5%, max_portfolio_leverage=2.0, max_daily_loss=10%
- [ ] Check risk engine is enforcing per-agent allocation caps ($500 max per agent)
- [ ] Confirm drawdown monitoring is active and alerting correctly
- [ ] Verify margin buffer checks are working and blocking trades when insufficient

## 6. Monitoring and Alerting

- [ ] Verify Telegram notifications are working for all trade executions
- [ ] Check Prometheus metrics are being collected for all agents
- [ ] Confirm health check endpoints are responding for all services
- [ ] Test alerting for high error rates, service downtime, risk limit breaches

## 7. Frontend and Public Site

- [ ] Verify frontend shows only bot trading capital ($3,000), not account balances
- [ ] Confirm all sensitive information is properly delayed (1-minute lag for trades)
- [ ] Test site accessibility at `sapphiretrade.xyz`
- [ ] Verify no personal account information is exposed in any component

## 8. System Health and Stability

- [ ] Check all 6 agent pods are running and healthy (no CrashLoopBackOff)
- [ ] Verify MCP coordinator is operational and accepting registrations
- [ ] Confirm Redis connectivity and data persistence
- [ ] Test BigQuery streaming is working and data is being stored
- [ ] Verify no crash loops or OOMKilled pods in the cluster

## 9. Security and Access Control

- [ ] Verify API keys are in Kubernetes secrets, not in code or environment variables
- [ ] Check network policies are enforcing traffic isolation between namespaces
- [ ] Confirm RBAC permissions are correctly configured for service accounts
- [ ] Verify no hardcoded credentials in codebase (use `grep -r "api_key\|secret" cloud_trader/`)

## 10. Documentation and Runbooks

- [ ] Verify `OPERATIONAL_RUNBOOK.md` is up to date with current procedures
- [ ] Confirm emergency procedures are documented and easily accessible
- [ ] Check deployment procedures are documented in `DEPLOYMENT_GUIDE.md`
- [ ] Verify troubleshooting guides are available in `docs/guides/TROUBLESHOOTING_GUIDE.md`

## Verification Signatures

**Pre-Live Review Completed By:**
- [ ] Lead Developer: _______________________ Date: __________
- [ ] DevOps Engineer: _____________________ Date: __________
- [ ] Risk Officer: ________________________ Date: __________
- [ ] Security Officer: ____________________ Date: __________

**Final Approval for Live Trading:**
- [ ] CTO/Technical Lead: __________________ Date: __________

## Emergency Contacts

- **Primary On-Call:** [Name] - [Phone] - [Email]
- **Secondary On-Call:** [Name] - [Phone] - [Email]
- **Exchange Support:** Aster DEX - [Contact Info]
- **Infrastructure Support:** GCP Support - [Case Number]

## Rollback Procedures

If issues are detected after going live:

1. **Immediate Actions:**
   - Execute Telegram kill switch: `/kill_switch activate`
   - Scale down all trading agents: `kubectl scale deployment --all --replicas=0 -n trading-system`
   - Notify all stakeholders

2. **Investigation:**
   - Check agent logs for error patterns
   - Verify API connectivity and rate limits
   - Review risk management alerts

3. **Resolution:**
   - Fix identified issues in staging environment
   - Test fixes thoroughly before re-enabling
   - Gradually scale back up trading agents

## Post-Live Monitoring (First 24 Hours)

- [ ] Monitor trade execution success rate (>95%)
- [ ] Track API error rates (<1%)
- [ ] Verify capital allocation is respected
- [ ] Confirm risk limits are enforced
- [ ] Check system performance (latency <500ms)
- [ ] Validate all monitoring alerts are working

---

**IMPORTANT:** This checklist must be completed in full before any live trading with real funds. Any shortcuts or incomplete verification could result in significant financial losses.