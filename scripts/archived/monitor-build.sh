#!/bin/bash
# Monitor Cloud Build Progress

BUILD_ID="${1:-$(gcloud builds list --limit=1 --format='value(id)')}"

echo "🔍 Monitoring Cloud Build: $BUILD_ID"
echo ""

while true; do
    clear
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║      Sapphire V2 Microservices - Build Status            ║"
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo ""

    # Get build status
    STATUS=$(gcloud builds describe "$BUILD_ID" --format='value(status)' 2>/dev/null)

    echo "Build ID: $BUILD_ID"
    echo "Status: $STATUS"
    echo ""

    # Get step statuses
    echo "Build Steps:"
    gcloud builds describe "$BUILD_ID" --format='table(steps.name,steps.status,steps.id)' 2>/dev/null | head -20

    echo ""
    echo "═══════════════════════════════════════════════════════════"

    # Check if done
    if [ "$STATUS" = "SUCCESS" ]; then
        echo ""
        echo "✅ BUILD SUCCESSFUL!"
        echo ""
        echo "Next: Run verification script"
        echo "  ./scripts/verify-deployment.sh"
        break
    elif [ "$STATUS" = "FAILURE" ] || [ "$STATUS" = "TIMEOUT" ] || [ "$STATUS" = "CANCELLED" ]; then
        echo ""
        echo "❌ BUILD FAILED: $STATUS"
        echo ""
        echo "View full logs:"
        echo "  gcloud builds log $BUILD_ID"
        break
    fi

    echo ""
    echo "⏳ Build in progress... (refreshing in 15s, Ctrl+C to exit)"
    sleep 15
done
