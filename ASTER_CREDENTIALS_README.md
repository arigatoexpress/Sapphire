# Aster DEX Credentials Management

## Current Credentials
- **API Key**: `[SECURE - Stored in .env.local and GCP Secret Manager]`
- **Secret Key**: `[SECURE - Stored in .env.local and GCP Secret Manager]`

## Storage Locations

### 1. Local Development (.env.local)
The credentials are stored in `.env.local` for local development:
```bash
ASTER_API_KEY=[YOUR_API_KEY_HERE]
ASTER_SECRET_KEY=[YOUR_SECRET_KEY_HERE]
```

### 2. Kubernetes Secrets (k8s-secrets.yaml)
Base64 encoded for Kubernetes deployments:
- ASTER_API_KEY: `YmIwZjg1Y2I2YjZmNmFhY2UwZTNkMmY4OTEzODY1YjdiYTQ0ZmEwZmRiNDMyM2QwY2Q2MTEyMzAwNzBkMGZhOA==`
- ASTER_SECRET_KEY: `M2Y5NTkyNTVmOTQzNmY0YzBhYmY0MTQ5ZjliMzcxZjUxYWZhOTg1ZTM1NzE3MzllM2NjMTBhYmUyNjliNDcxYw==`

### 3. Google Secret Manager
Stored in GCP project `sapphireinfinite`:
- Secret: `ASTER_API_KEY`
- Secret: `ASTER_SECRET_KEY`

## How Credentials Are Loaded

The application loads credentials in this priority order:
1. **Environment Variables** (from .env.local or deployment environment)
2. **GCP Secret Manager** (fallback for cloud deployments)
3. **Settings Configuration** (from config.py validation aliases)

## Updating Credentials

To update Aster credentials across all systems:

```bash
# Update all systems at once
scripts/update_aster_credentials.sh NEW_API_KEY NEW_SECRET_KEY [PROJECT_ID]

# Or update manually:
# 1. Update .env.local
# 2. Update k8s-secrets.yaml (base64 encode new values)
# 3. Update GCP Secret Manager
# 4. Redeploy services
```

## Verification

To verify credentials are working:

```bash
# Test environment variables
source .env.local && echo $ASTER_API_KEY

# Test Kubernetes secrets
kubectl get secret cloud-trader-secrets -n trading-system-clean -o yaml

# Test GCP Secret Manager
gcloud secrets versions access latest --secret=ASTER_API_KEY --project=sapphireinfinite
```

## Security Notes

- Never commit actual credential values to git
- Use the provided scripts for credential management
- Rotate credentials regularly
- Monitor access logs for unauthorized usage

## Files That Reference These Credentials

- `cloud_trader/config.py` - Settings configuration
- `cloud_trader/credentials.py` - Credential loading logic
- `risk-orchestrator/src/risk_orchestrator/config.py` - Risk orchestrator settings
- `k8s-secrets.yaml` - Kubernetes secrets
- `helm/sapphire-trading-system/templates/secrets.yaml` - Helm template
