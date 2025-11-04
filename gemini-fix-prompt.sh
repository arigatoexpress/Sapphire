#!/bin/bash
# Script to run Gemini AI analysis and fixes for ASTER AI Trading System
# Usage: ./gemini-fix-prompt.sh

PROJECT_ID="quant-ai-trader-credits"
PROMPT_FILE="gemini-prompt-for-fixes.txt"

echo "🚀 Running Gemini AI Analysis for ASTER AI Trading System Fixes"
echo "================================================================"
echo ""

# Read the prompt file
PROMPT=$(cat "$PROMPT_FILE")

# Run Gemini with the prompt
echo "📝 Sending prompt to Gemini 1.5 Pro..."
echo ""

gcloud ai generate-content \
  --model=gemini-1.5-pro \
  --project="$PROJECT_ID" \
  --prompt="$PROMPT" \
  --temperature=0.2 \
  --max-output-tokens=8192

echo ""
echo "✅ Analysis complete!"
echo ""
echo "Next steps:"
echo "1. Review the Gemini output above"
echo "2. Apply the recommended fixes step by step"
echo "3. Test each fix before moving to the next"
echo "4. Verify endpoints are working: curl https://api.sapphiretrade.xyz/healthz"

