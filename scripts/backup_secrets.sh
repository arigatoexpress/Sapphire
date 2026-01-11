#!/bin/bash
# Sapphire Trading System - Secret Backup Script
# Usage: ./backup_secrets.sh
# Requires: gcloud CLI, GPG configured

set -e

# Configuration
BACKUP_DIR="/secure/sapphire-backups/$(date +%Y%m%d)"
PROJECT_ID="sapphire-479610"
GPG_RECIPIENT="your-gpg-key-id"  # UPDATE THIS

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔐 Sapphire Trading System - Secret Backup${NC}"
echo "Backup directory: $BACKUP_DIR"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"
cd "$BACKUP_DIR"

# 1. Export Secret Manager inventory
echo -e "${YELLOW}📋 Exporting Secret Manager inventory...${NC}"
gcloud secrets list --project=$PROJECT_ID --format=json > secrets-inventory.json
echo "✅ Inventory exported"

# 2. Export non-critical secrets (API keys)
echo -e "${YELLOW}🔑 Exporting API keys...${NC}"
for secret in ASTER_API_KEY SYMPHONY_API_KEY GEMINI_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID GROK_API_KEY vertex_api_key_v1; do
  echo " - Exporting $secret..."
  gcloud secrets versions access latest --secret=$secret --project=$PROJECT_ID > "${secret}.txt" 2>/dev/null || echo "⚠️  Failed to export $secret"
done
echo "✅ API keys exported"

# 3. Export CRITICAL private keys separately
echo -e "${RED}🔴 CRITICAL: Exporting private keys...${NC}"
echo "⚠️  These files contain funds-controlling credentials!"
for secret in HL_SECRET_KEY SOLANA_PRIVATE_KEY ASTER_SECRET_KEY; do
  echo " - Exporting $secret..."
  gcloud secrets versions access latest --secret=$secret --project=$PROJECT_ID > "CRITICAL-${secret}.txt" 2>/dev/null || echo "⚠️  Failed to export $secret"
done
echo "✅ Private keys exported"

# 4. Export Firestore data
echo -e "${YELLOW}💾 Exporting Firestore database...${NC}"
FIRESTORE_BACKUP="gs://sapphire-479610-backup/firestore-$(date +%Y%m%d-%H%M%S)"
gcloud firestore export "$FIRESTORE_BACKUP" --project=$PROJECT_ID > firestore-export.log 2>&1
if [ $? -eq 0 ]; then
  echo "✅ Firestore exported to: $FIRESTORE_BACKUP"
  echo "$FIRESTORE_BACKUP" > firestore-backup-location.txt
else
  echo "⚠️  Firestore export failed (check firestore-export.log)"
fi

# 5. Encrypt all secret files
echo -e "${YELLOW}🔒 Encrypting backup...${NC}"
if [ "$GPG_RECIPIENT" = "your-gpg-key-id" ]; then
  echo -e "${RED}ERROR: Please configure GPG_RECIPIENT in this script!${NC}"
  echo "Skipping encryption..."
else
  # Create tarball
  tar -czf secrets-backup.tar.gz *.txt *.json

  # Encrypt with GPG
  gpg --encrypt --recipient "$GPG_RECIPIENT" secrets-backup.tar.gz

  if [ -f "secrets-backup.tar.gz.gpg" ]; then
    echo "✅ Backup encrypted: secrets-backup.tar.gz.gpg"

    # Securely delete unencrypted files
    shred -u *.txt secrets-backup.tar.gz
    echo "✅ Unencrypted files securely deleted"
  else
    echo "⚠️  Encryption failed, keeping unencrypted files"
  fi
fi

# 6. Create README for recovery
cat > RECOVERY-INSTRUCTIONS.md <<EOF
# Sapphire Secret Recovery Instructions

**Backup Date**: $(date)
**Backup Location**: $BACKUP_DIR

## Quick Recovery Steps

### 1. Decrypt Backup
\`\`\`bash
gpg --decrypt secrets-backup.tar.gz.gpg > secrets-backup.tar.gz
tar -xzf secrets-backup.tar.gz
\`\`\`

### 2. Restore Secrets to GCP Secret Manager
\`\`\`bash
# For each secret file
for file in *.txt; do
  secret_name=\${file%.txt}
  gcloud secrets create \$secret_name --data-file=\$file --project=$PROJECT_ID || \
  gcloud secrets versions add \$secret_name --data-file=\$file --project=$PROJECT_ID
done
\`\`\`

### 3. Verify Services
\`\`\`bash
gcloud run services list --region us-central1 --project=$PROJECT_ID
\`\`\`

## Firestore Recovery
\`\`\`bash
# Get backup location
cat firestore-backup-location.txt

# Import (requires admin permissions)
gcloud firestore import \$(cat firestore-backup-location.txt) --project=$PROJECT_ID
\`\`\`

## Emergency Contacts
- GCP Enterprise Support: 1-877-355-5787
- Team Lead: [YOUR CONTACT]

## Critical Private Keys
🔴 **PRIORITY 1**: Restore these immediately if exchange wallets compromised
- HL_SECRET_KEY (Hyperliquid)
- SOLANA_PRIVATE_KEY (Drift Protocol)
- ASTER_SECRET_KEY (Aster DEX)

## Security Notes
- This backup contains CRITICAL CREDENTIALS
- Store in multiple secure locations (encrypted USB, password manager)
- NEVER upload unencrypted to cloud storage
- Shred/overwrite when destroying old backups
EOF

echo "✅ Recovery instructions created"

# 7. Summary
echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 Backup Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo "📁 Backup location: $BACKUP_DIR"
echo ""
echo "📦 Contents:"
ls -lh
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT:${NC}"
echo "1. Move this backup to secure offline storage (encrypted USB)"
echo "2. Also save to password manager (1Password, Bitwarden, etc.)"
echo "3. NEVER leave unencrypted on shared systems"
echo "4. Test recovery procedure periodically"
echo ""
echo -e "${RED}🔴 CRITICAL:${NC} This backup contains credentials controlling funds!"
echo ""

# Reminder to test recovery
echo "📋 Next steps:"
echo "  [ ] Move backup to encrypted USB drive"
echo "  [ ] Save copy in password manager"
echo "  [ ] Test recovery on non-prod account"
echo "  [ ] Schedule next backup (recommended: weekly)"
echo ""
