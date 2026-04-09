#!/bin/bash
# Sync all repos on Windows by pulling latest from GitHub
# Run from Mac via SSH to Windows

WINDOWS="aribs@100.71.10.48"
REPOS="Sapphire Project-Go-Forward cyber-threat-bot regional-intel-workbench Cointracker claw-code"

echo "$(date): Syncing Windows repos..."

for repo in $REPOS; do
    echo "  Pulling $repo..."
    ssh "$WINDOWS" "pushd E:\\Sapphire\\Code\\$repo && git pull 2>&1 && popd" 2>&1 | tail -2
done

echo "$(date): Sync complete"
