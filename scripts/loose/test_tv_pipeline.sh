#!/bin/bash
# Test TradingView Pipeline - Mac → Windows → Pub/Sub

echo "═══════════════════════════════════════════════════════════"
echo "  🧪 TESTING TRADINGVIEW PIPELINE"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Mac Bridge
echo "📡 Test 1: Mac Bridge (localhost:8083)"
RESP=$(curl -s --max-time 5 http://localhost:8083/status)
if [ -n "$RESP" ]; then
    echo -e "${GREEN}✅ Mac Bridge responding${NC}"
    echo "   Status: $(echo $RESP | grep -o '"running":true' || echo 'unknown')"
else
    echo -e "${RED}❌ Mac Bridge not responding${NC}"
fi
echo ""

# Test 2: Send test alert to Mac Bridge
echo "📡 Test 2: Send Test Alert → Mac Bridge"
TEST_ALERT='{"symbol":"BTCUSDT","action":"entry_long","price":87500.5,"size":0.001,"test":true}'
RESP=$(curl -s --max-time 10 -X POST http://localhost:8083/webhook \
    -H "Content-Type: application/json" \
    -d "$TEST_ALERT")
if [ -n "$RESP" ]; then
    echo -e "${GREEN}✅ Alert accepted${NC}"
    echo "   Response: $RESP"
else
    echo -e "${RED}❌ Alert failed${NC}"
fi
echo ""

# Test 3: TV Controller
echo "📡 Test 3: TV Controller (localhost:8082)"
RESP=$(curl -s --max-time 5 http://localhost:8082/status)
if [ -n "$RESP" ]; then
    echo -e "${GREEN}✅ TV Controller responding${NC}"
    CONNECTED=$(echo $RESP | grep -o '"connected":true')
    if [ -n "$CONNECTED" ]; then
        echo "   Browser: Connected to TradingView"
    fi
else
    echo -e "${YELLOW}⚠️  TV Controller starting...${NC}"
fi
echo ""

# Test 4: Windows Webhook
echo "📡 Test 4: Windows Webhook (100.71.10.48:9090)"
RESP=$(curl -s --max-time 5 http://100.71.10.48:9090/status)
if [ -n "$RESP" ]; then
    echo -e "${GREEN}✅ Windows Webhook responding${NC}"
    TOTAL=$(echo $RESP | grep -o '"total":[0-9]*' | cut -d: -f2)
    PUB=$(echo $RESP | grep -o '"published":[0-9]*' | cut -d: -f2)
    echo "   Stats: $TOTAL total, $PUB published"
else
    echo -e "${RED}❌ Windows Webhook not responding${NC}"
fi
echo ""

# Test 5: Full Pipeline
echo "📡 Test 5: Full Pipeline Test (Mac → Windows → Pub/Sub)"
RESP=$(curl -s --max-time 10 http://localhost:8083/test)
if [ -n "$RESP" ]; then
    FORWARDED=$(echo $RESP | grep -o '"forwarded":true')
    if [ -n "$FORWARDED" ]; then
        echo -e "${GREEN}✅ Full pipeline working!${NC}"
        echo "   Mac Bridge → Windows → Pub/Sub: SUCCESS"
    else
        echo -e "${YELLOW}⚠️  Pipeline test returned: $RESP${NC}"
    fi
else
    echo -e "${RED}❌ Pipeline test failed${NC}"
fi
echo ""

echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📋 NEXT STEPS:"
echo ""
echo "1. Import Pine Script to TradingView:"
echo "   Pine Editor → Open → ~/Sapphire_Strategy_Mac.pine"
echo ""
echo "2. Add to Chart"
echo ""
echo "3. Create Alert with webhook:"
echo "   URL: http://192.168.1.28:8083/webhook"
echo ""
echo "4. When strategy signals fire, trades execute on Pi bots!"
echo ""
echo "═══════════════════════════════════════════════════════════"
