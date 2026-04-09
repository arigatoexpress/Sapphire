#!/bin/bash
# Sapphire OS — Automated backup to Windows E: drive via Tailscale
# Syncs all code repos + Sapphire data to E:\Sapphire\

WINDOWS_HOST="aribs@100.71.10.48"
REMOTE_BASE="/cygdrive/e/Sapphire"
LOG="$HOME/autonomy-status/logs/backup.log"

echo "$(date): Starting backup..." >> "$LOG"

# Sync each repo (git-aware, skip .git internals for speed)
for repo in Sapphire Project-Go-Forward cyber-threat-bot regional-intel-workbench Cointracker claw-code; do
    src="$HOME/Code/$repo/"
    dest="$WINDOWS_HOST:$REMOTE_BASE/Code/$repo/"
    echo "  Syncing $repo..." >> "$LOG"
    rsync -az --delete --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='__pycache__' \
        "$src" "$dest" 2>> "$LOG"
done

# Sync Sapphire data specifically (trading signals, threat intel, predictions)
rsync -az --delete "$HOME/Code/Sapphire/data/" "$WINDOWS_HOST:$REMOTE_BASE/data/" 2>> "$LOG"

echo "$(date): Backup complete" >> "$LOG"
