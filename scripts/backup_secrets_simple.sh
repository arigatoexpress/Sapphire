#!/bin/bash
# Sapphire Trading System - Secret Backup Script (No GPG Required)
# Usage: ./backup_secrets_simple.sh
# Requires: gcloud CLI

set -e

# Configuration
BACKUP_DIR="$HOME/.sapphire-backups/$(date +%Y%m%d-%H%M%S)"
PROJECT_ID="sapphire-479610"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

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
for secret in HL_SECRET_KEY SOLANA_PRIVATE_KEY ASTER_SECRET_KEY HL_ACCOUNT_ADDRESS; do
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

# 5. Create secure archive with password
echo -e "${YELLOW}🔒 Creating password-protected archive...${NC}"
echo ""
echo "Creating encrypted ZIP file..."
echo "You will be prompted to set a password."
echo ""

# Create password-protected zip (macOS native)
zip -e -r secrets-backup.zip *.txt *.json 2>/dev/null

if [ -f "secrets-backup.zip" ]; then
  echo "✅ Password-protected archive created: secrets-backup.zip"

  # Securely delete unencrypted files
  echo "Securely deleting unencrypted files..."
  rm -P *.txt 2>/dev/null
  echo "✅ Unencrypted files deleted"
else
  echo "⚠️  Zip creation failed, keeping unencrypted files for manual handling"
fi

# 6. Create README for recovery
cat > RECOVERY-INSTRUCTIONS.md <<EOF
# Sapphire Secret Recovery Instructions

**Backup Date**: $(date)
**Backup Location**: $BACKUP_DIR

## Quick Recovery Steps

### 1. Extract Backup
\`\`\`bash
cd $BACKUP_DIR
unzip secrets-backup.zip
# Enter the password you set during backup
\`\`\`

### 2. Restore Secrets to GCP Secret Manager
\`\`\`bash
# For each secret file
for file in *.txt; do
  secret_name=\${file%.txt}
  # Remove CRITICAL- prefix if present
  secret_name=\${secret_name#CRITICAL-}

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

## Import to Password Manager (1Password/Bitwarden)

1. Extract secrets-backup.zip
2. Open each .txt file and copy to password manager
3. Create secure note with:
   - Title: "Sapphire Trading - [SECRET_NAME]"
   - Content: Paste secret value
   - Tags: crypto, trading, api-keys
4. Delete extracted files when done

## Emergency Contacts
- GCP Enterprise Support: 1-877-355-5787

## Critical Private Keys (HIGHEST PRIORITY)
🔴 Restore these immediately if exchange wallets compromised:
- HL_SECRET_KEY (Hyperliquid - controls funds)
- SOLANA_PRIVATE_KEY (Drift Protocol - controls funds)
- ASTER_SECRET_KEY (Aster DEX - controls funds)

## Security Notes
- This backup contains CRITICAL CREDENTIALS
- Store encrypted zip in password manager
- Also keep copy on encrypted USB drive
- NEVER upload unencrypted to cloud storage
- Securely delete when creating new backups
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
echo -e "${YELLOW}⚠️  IMPORTANT - Next Steps:${NC}"
echo "1. Import secrets-backup.zip to password manager (1Password/Bitwarden)"
echo "   - Create secure note for each secret"
echo "   - Tag appropriately (crypto, trading, etc.)"
echo ""
echo "2. Copy secrets-backup.zip to encrypted USB drive"
echo "   - Use macOS encrypted disk image or BitLocker"
echo "   - Label drive clearly and store securely"
echo ""
echo "3. Test recovery procedure on non-production account"
echo ""
echo "4. Schedule next backup (recommended: weekly)"
echo ""
echo -e "${RED}🔴 CRITICAL:${NC} This backup contains credentials controlling funds!"
echo "Keep the password safe and separate from the backup!"
echo ""
