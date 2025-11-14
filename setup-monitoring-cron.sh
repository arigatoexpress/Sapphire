#!/bin/bash

# Setup automated monitoring and cleanup schedule

echo "⏰ SETTING UP AUTOMATED MONITORING SCHEDULE"
echo "==========================================="

# Create monitoring directory
MONITOR_DIR="$HOME/sapphire-monitoring"
mkdir -p "$MONITOR_DIR"

# Copy scripts to monitoring directory
cp monitoring-script.sh "$MONITOR_DIR/"
cp cleanup-script.sh "$MONITOR_DIR/"

echo "📁 Scripts copied to: $MONITOR_DIR"

# Create log directory
LOG_DIR="$MONITOR_DIR/logs"
mkdir -p "$LOG_DIR"

echo "📝 Logs will be stored in: $LOG_DIR"

# Setup cron jobs
CRON_JOBS="
# Sapphire Trade System Monitoring
# Run monitoring daily at 9 AM
0 9 * * * $MONITOR_DIR/monitoring-script.sh >> $LOG_DIR/monitoring-\$(date +\%Y\%m\%d).log 2>&1

# Run cleanup weekly on Mondays at 2 AM
0 2 * * 1 $MONITOR_DIR/cleanup-script.sh >> $LOG_DIR/cleanup-\$(date +\%Y\%m\%d).log 2>&1

# Health check every 4 hours
0 */4 * * * $MONITOR_DIR/monitoring-script.sh | grep -E '(ERROR|WARNING)' | mail -s 'Sapphire Trade Alert' your-email@example.com || true
"

# Add to crontab (commented out for safety - user must run manually)
echo "📋 CRON JOBS TO ADD (run 'crontab -e' and add these lines):"
echo "$CRON_JOBS"
echo ""
echo "💡 ALTERNATIVE: Run scripts manually as needed:"
echo "   • Daily monitoring: $MONITOR_DIR/monitoring-script.sh"
echo "   • Weekly cleanup: $MONITOR_DIR/cleanup-script.sh --dry-run"
echo ""
echo "✅ MONITORING SYSTEM SETUP COMPLETE!"
