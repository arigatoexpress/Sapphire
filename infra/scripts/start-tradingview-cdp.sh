#!/bin/bash
# Start TradingView Desktop with Chrome DevTools Protocol enabled.
# Used by the tradingview-mcp for live chart control + Pine script automation.

set -u

CDP_PORT="${CDP_PORT:-9222}"

pkill -9 -f "/Applications/TradingView.app/Contents/MacOS/TradingView" 2>/dev/null || true
sleep 2

open -a TradingView --args --remote-debugging-port="$CDP_PORT"

for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    sleep 2
    if curl -fs "http://localhost:$CDP_PORT/json/version" >/dev/null 2>&1; then
        echo "TradingView CDP ready on :$CDP_PORT (attempt $i)"
        exit 0
    fi
done

echo "TradingView CDP failed to come up on :$CDP_PORT" >&2
exit 1
