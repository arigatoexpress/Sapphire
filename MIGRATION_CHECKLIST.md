# SAPPHIRE Project Migration Checklist

## ✅ Completed Migration Steps

### Infrastructure
- [x] GCP Project: `sapphireinfinite` (342943608894)
- [x] GKE Cluster: `hft-trading-cluster` in `sapphireinfinite`
- [x] Cloud Build: Using `sapphireinfinite` project
- [x] DNS: `api.sapphiretrade.xyz` pointing to new infrastructure
- [x] Load Balancer: Using static IP `34.144.213.188`
- [x] SSL Certificate: Provisioning (waiting for DNS)

### Code & Configuration
- [x] `cloudbuild.yaml`: Using `${PROJECT_ID}` (sapphireinfinite)
- [x] `cloud_trader/config.py`: Vertex AI endpoints updated to sapphireinfinite
- [x] `k8s-deployment.yaml`: Using sapphireinfinite artifact registry
- [x] `update-url-map.sh`: Updated to sapphireinfinite project

## ⚠️ Remaining References to Old Project

### Documentation Files (Historical - Can Keep)
- `docs/DEPLOYMENT_CHECKLIST.md` - Historical deployment notes
- `DEPLOYMENT_ISSUES_SUMMARY.md` - Historical issues
- `GEMINI_PROMPT_USAGE.md` - Example usage (may need update)
- `RUN_GEMINI_PROMPT.md` - Example script (may need update)

### Scripts Needing Update
- `final_status_check.sh` - Contains reference to old project deletion
- `.gcp/build-workflow.sh` - May contain old project references

### Configuration Files with Old Cloud Run URLs
These reference old project number `880429861698` in Cloud Run service URLs:

**Files to Review:**
1. `infra/llm_serving/model_router.py` - LLM endpoint defaults
2. `infra/llm_serving/cloudbuild-router.yaml` - Environment variables
3. `infra/dashboard/*.py` - Dashboard service URLs
4. `infra/dashboard/*.yaml` - Cloud Build configs
5. `cloud-trader-service.yaml` - Service account reference
6. `FIREBASE_DOMAIN_SETUP.md` - Example URLs
7. `FIREBASE_FRONTEND_README.md` - Example URLs

**Decision Needed:**
- Are these LLM services (`deepseek-trader-880429861698`, etc.) still needed?
- Should they be migrated to new project or replaced with `api.sapphiretrade.xyz`?
- If services are in old project, they may still be functional but should be migrated

## 🔍 Verification Steps

### 1. Check Active GCP Resources
```bash
# List all resources in new project
gcloud projects describe sapphireinfinite

# Check if old project still exists
gcloud projects describe sapphireinfinite

# List service accounts
gcloud iam service-accounts list --project=sapphireinfinite
```

### 2. Verify No Cross-Project Dependencies
```bash
# Check IAM bindings
gcloud projects get-iam-policy sapphireinfinite

# Check if any resources reference old project
grep -r "sapphireinfinite" --include="*.yaml" --include="*.py" --include="*.sh" .
```

### 3. Test All Endpoints
```bash
# Test API endpoint
curl https://api.sapphiretrade.xyz/healthz

# Test frontend
curl https://sapphiretrade.xyz

# Check SSL certificate
kubectl get managedcertificate -n trading cloud-trader-cert
```

### 4. Verify Service Accounts
```bash
# Current service account should be from new project
kubectl get deployment -n trading cloud-trader -o jsonpath='{.spec.template.spec.serviceAccountName}'

# Should show: 342943608894-compute@developer.gserviceaccount.com
```

## 🗑️ Cleanup Tasks (After Verification)

### Safe to Delete (After 30-day verification period)
1. Old GCP Project: `sapphireinfinite`
   ```bash
   # WARNING: Only after full verification
   # gcloud projects delete sapphireinfinite
   ```

2. Old Cloud Run Services (if migrated)
   - `cloud-trader-880429861698`
   - `deepseek-trader-880429861698`
   - `qwen-trader-880429861698`
   - `fingpt-trader-880429861698`
   - `phi3-trader-880429861698`
   - `model-router-880429861698`

3. Old Artifact Registry Images
   ```bash
   gcloud artifacts docker images list \
     --repository=cloud-run-source-deploy \
     --location=us-central1 \
     --project=sapphireinfinite
   ```

### Keep for Reference
- Historical documentation
- Old deployment scripts (archive, don't delete)
- Migration notes

## 📋 Final Verification Checklist

Before considering migration complete:

- [ ] All active services running in `sapphireinfinite`
- [ ] DNS pointing to new infrastructure
- [ ] SSL certificate active
- [ ] No errors in logs referencing old project
- [ ] All API endpoints responding correctly
- [ ] Frontend loading correctly
- [ ] Trading bots operational
- [ ] Monitoring and alerts configured for new project
- [ ] Backup/restore procedures tested
- [ ] Team notified of new project details

## 🚨 Critical: Service Account Migration

**Current Issue**: `cloud-trader-service.yaml` references old service account:
```
serviceAccountName: 880429861698-compute@developer.gserviceaccount.com
```

**Action Required**: Update Kubernetes deployments to use new service account:
```yaml
serviceAccountName: 342943608894-compute@developer.gserviceaccount.com
```

Or better yet, use a named service account:
```yaml
serviceAccountName: sapphire-trader-sa@sapphireinfinite.iam.gserviceaccount.com
```

## 📝 Notes

- Old project number `880429861698` may still appear in Cloud Run URLs if those services are still running
- These can be kept temporarily for backward compatibility
- Plan migration of LLM services to new project or replace with unified API endpoint
- Monitor for any errors referencing old project resources

