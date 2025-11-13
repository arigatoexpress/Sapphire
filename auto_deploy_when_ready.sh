#!/bin/bash
# Auto-deploy script that waits for project to sync, then deploys

PROJECT_ID="sapphire-22470816"
MAX_ATTEMPTS=20
ATTEMPT=0
WAIT_TIME=30  # seconds between checks

echo "🔄 Auto-Deploy Script"
echo "===================="
echo "Project: $PROJECT_ID"
echo "Checking every $WAIT_TIME seconds..."
echo ""

cd /Users/aribs/AIAster/trading-dashboard || exit 1

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    echo "[Attempt $ATTEMPT/$MAX_ATTEMPTS] Checking if project is available..."
    
    # Check if project appears in list
    if firebase projects:list 2>/dev/null | grep -q "$PROJECT_ID"; then
        echo "✅ Project found! Switching to it..."
        firebase use "$PROJECT_ID" 2>&1
        
        if [ $? -eq 0 ]; then
            echo "✅ Switched to project. Deploying..."
            firebase deploy --only hosting 2>&1
            
            if [ $? -eq 0 ]; then
                echo ""
                echo "🎉 DEPLOYMENT SUCCESSFUL!"
                echo "Site URL: https://$PROJECT_ID.web.app"
                exit 0
            else
                echo "❌ Deployment failed. Check errors above."
                exit 1
            fi
        fi
    else
        echo "⏳ Project not available yet. Waiting $WAIT_TIME seconds..."
        sleep $WAIT_TIME
    fi
done

echo ""
echo "⏰ Timeout: Project didn't sync after $((MAX_ATTEMPTS * WAIT_TIME / 60)) minutes"
echo "💡 Try using Console method instead:"
echo "   https://studio.firebase.google.com/$PROJECT_ID/hosting"
exit 1

