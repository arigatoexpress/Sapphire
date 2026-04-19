#!/usr/bin/env bash
# setup-sops.sh — Configure SOPS (Secrets OPerationS) for Sapphire
# Encrypts secrets at rest using age (modern, no GPG dependency).
#
# Usage: bash infra/setup-sops.sh
set -euo pipefail

SAPPHIRE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOPS_DIR="$SAPPHIRE_ROOT/infra/sops"
SECRETS_SRC="$HOME/.config/sapphire-secrets"
AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"

echo "=== Sapphire SOPS Setup ==="

# 1. Check prerequisites
if ! command -v sops &>/dev/null; then
    echo "ERROR: sops not found. Install with: brew install sops"
    exit 1
fi

if ! command -v age-keygen &>/dev/null; then
    echo "Installing age..."
    brew install age
fi

# 2. Generate age key if missing
if [ ! -f "$AGE_KEY_FILE" ]; then
    echo "Generating new age key..."
    mkdir -p "$(dirname "$AGE_KEY_FILE")"
    age-keygen -o "$AGE_KEY_FILE" 2>&1
    chmod 600 "$AGE_KEY_FILE"
    echo "Key saved to $AGE_KEY_FILE"
else
    echo "Age key already exists at $AGE_KEY_FILE"
fi

# Extract public key
AGE_PUB=$(grep "public key:" "$AGE_KEY_FILE" | awk '{print $NF}')
echo "Public key: $AGE_PUB"

# 3. Create .sops.yaml config
mkdir -p "$SOPS_DIR"
cat > "$SAPPHIRE_ROOT/.sops.yaml" <<EOF
# SOPS config for Sapphire
# Encrypts all files under infra/sops/ with age
creation_rules:
  - path_regex: infra/sops/.*\.enc\..*
    age: >-
      ${AGE_PUB}
  - path_regex: \.env\.enc$
    age: >-
      ${AGE_PUB}
EOF

echo "Created .sops.yaml"

# 4. Encrypt existing secrets if sapphire-secrets dir exists
if [ -d "$SECRETS_SRC" ]; then
    echo ""
    echo "Found secrets at $SECRETS_SRC"
    for envfile in "$SECRETS_SRC"/.env.*; do
        [ -f "$envfile" ] || continue
        base=$(basename "$envfile")
        enc_file="$SOPS_DIR/${base}.enc.env"
        if [ -f "$enc_file" ]; then
            echo "  SKIP $base (already encrypted)"
        else
            echo "  Encrypting $base -> $enc_file"
            sops --encrypt --age "$AGE_PUB" --input-type dotenv --output-type dotenv "$envfile" > "$enc_file"
        fi
    done
else
    echo ""
    echo "No secrets found at $SECRETS_SRC — skipping encryption."
    echo "Place .env.* files there and re-run to encrypt."
fi

# 5. Ensure .gitignore excludes keys but includes encrypted files
GITIGNORE="$SAPPHIRE_ROOT/.gitignore"
if ! grep -q "keys.txt" "$GITIGNORE" 2>/dev/null; then
    echo "" >> "$GITIGNORE"
    echo "# SOPS age keys (NEVER commit)" >> "$GITIGNORE"
    echo "**/keys.txt" >> "$GITIGNORE"
fi

echo ""
echo "=== Done ==="
echo ""
echo "Usage:"
echo "  Encrypt:  sops --encrypt --age $AGE_PUB secrets.env > secrets.enc.env"
echo "  Decrypt:  sops --decrypt infra/sops/file.enc.env"
echo "  Edit:     sops infra/sops/file.enc.env"
echo ""
echo "IMPORTANT: Back up $AGE_KEY_FILE — losing it means losing access to all encrypted secrets."
