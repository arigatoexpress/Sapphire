#!/bin/bash
# Verify and fix frontend to ensure it's using new project

set -e

echo "🔍 Frontend Migration Verification & Fix"
echo "=========================================="
echo ""

cd "$(dirname "$0")/trading-dashboard" || exit 1

# 1. Verify Firebase project
echo "1️⃣ Checking Firebase Configuration..."
echo ""

CURRENT_PROJECT=$(firebase use 2>&1 | tail -1)
echo "Current Firebase project: $CURRENT_PROJECT"

if [ "$CURRENT_PROJECT" != "sapphireinfinite" ]; then
    echo "⚠️  WARNING: Wrong project! Setting to sapphireinfinite..."
    firebase use sapphireinfinite
else
    echo "✅ Correct project: sapphireinfinite"
fi
echo ""

# 2. Check .firebaserc
echo "2️⃣ Checking .firebaserc..."
if grep -q "sapphireinfinite" .firebaserc && ! grep -q "sapphireinfinite" .firebaserc; then
    echo "✅ .firebaserc correctly configured"
else
    echo "❌ .firebaserc needs update"
fi
echo ""

# 3. Check API endpoint in code
echo "3️⃣ Checking API endpoint configuration..."
API_REF=$(grep -r "api.sapphiretrade.xyz" src/ | wc -l | tr -d ' ')
OLD_REF=$(grep -r "342943608894\|quant-ai-trader" src/ 2>/dev/null | wc -l | tr -d ' ')

echo "References to api.sapphiretrade.xyz: $API_REF"
echo "References to old project: $OLD_REF"

if [ "$OLD_REF" -eq 0 ]; then
    echo "✅ No old project references in source code"
else
    echo "⚠️  Found old project references in source code"
    grep -r "342943608894\|quant-ai-trader" src/ 2>/dev/null || true
fi
echo ""

# 4. Check Firebase config
echo "4️⃣ Checking Firebase config..."
if grep -q "sapphireinfinite" src/lib/firebase.ts && grep -q "342943608894" src/lib/firebase.ts; then
    echo "✅ Firebase config uses new project"
else
    echo "❌ Firebase config needs update"
fi
echo ""

# 5. Check for built files with old references
echo "5️⃣ Checking built files..."
if [ -d "dist" ]; then
    OLD_BUILD_REF=$(grep -r "342943608894\|quant-ai-trader" dist/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$OLD_BUILD_REF" -eq 0 ]; then
        echo "✅ No old project references in build"
    else
        echo "⚠️  Found old project references in build - need to rebuild"
        echo "   Run: npm run build"
    fi
else
    echo "ℹ️  No dist/ directory - build needed"
fi
echo ""

# 6. Test current deployment
echo "6️⃣ Testing current deployment..."
echo ""

echo "Testing https://sapphiretrade.xyz..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://sapphiretrade.xyz 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Frontend is accessible"
else
    echo "⚠️  Frontend returned HTTP $HTTP_CODE"
fi

echo ""
echo "Testing API endpoint..."
API_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://api.sapphiretrade.xyz/healthz 2>/dev/null || echo "000")
if [ "$API_CODE" = "200" ]; then
    echo "✅ API endpoint is accessible"
else
    echo "⚠️  API returned HTTP $API_CODE"
fi
echo ""

# 7. Check CSP header
echo "7️⃣ Checking Content-Security-Policy header..."
CSP=$(curl -sI https://sapphiretrade.xyz 2>/dev/null | grep -i "content-security-policy" || echo "")
if echo "$CSP" | grep -q "342943608894"; then
    echo "   This needs to be fixed in Firebase hosting headers"
    echo "   Current CSP: $CSP"
else
    echo "✅ CSP header looks good (or not set)"
fi
echo ""

# 8. Recommendations
echo "8️⃣ Recommendations:"
echo ""

if [ "$OLD_BUILD_REF" -gt 0 ] || [ ! -d "dist" ]; then
    echo "📦 Rebuild frontend:"
    echo "   cd trading-dashboard"
    echo "   npm run build"
    echo ""
fi

if echo "$CSP" | grep -q "342943608894"; then
    echo "🔧 Fix CSP header in firebase.json:"
    echo "   Update headers section to remove old URLs"
    echo ""
fi

echo "🚀 Redeploy to Firebase:"
echo "   cd trading-dashboard"
echo "   firebase deploy --only hosting --project=sapphireinfinite"
echo ""

echo "✅ Verification complete!"

