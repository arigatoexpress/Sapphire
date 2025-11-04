#!/usr/bin/env python3
"""
Run Gemini AI analysis using Vertex AI Python SDK
"""
import os
import sys

try:
    from vertexai.generative_models import GenerativeModel
    import vertexai
except ImportError:
    print("ERROR: vertexai package not installed.")
    print("Install with: pip install google-cloud-aiplatform")
    sys.exit(1)

PROJECT_ID = "quant-ai-trader-credits"
REGION = "us-central1"
MODEL_NAME = "gemini-1.5-pro"

def main():
    # Read prompt file
    prompt_file = "gemini-prompt-for-fixes.txt"
    if not os.path.exists(prompt_file):
        print(f"ERROR: {prompt_file} not found")
        sys.exit(1)
    
    with open(prompt_file, 'r') as f:
        prompt = f.read()
    
    print("🚀 Running Gemini AI Analysis for ASTER AI Trading System Fixes")
    print("=" * 64)
    print("")
    
    try:
        # Initialize Vertex AI
        vertexai.init(project=PROJECT_ID, location=REGION)
        
        # Load model
        print(f"📝 Loading {MODEL_NAME}...")
        model = GenerativeModel(MODEL_NAME)
        
        # Generate content
        print("🤖 Sending prompt to Gemini...")
        print("")
        
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 8192,
            }
        )
        
        print("=" * 64)
        print("GEMINI RESPONSE:")
        print("=" * 64)
        print("")
        print(response.text)
        print("")
        print("=" * 64)
        print("✅ Analysis complete!")
        print("")
        print("Next steps:")
        print("1. Review the Gemini output above")
        print("2. Apply the recommended fixes step by step")
        print("3. Test each fix before moving to the next")
        print("4. Verify endpoints: curl https://api.sapphiretrade.xyz/healthz")
        
    except Exception as e:
        print(f"ERROR: {e}")
        print("")
        print("Troubleshooting:")
        print("1. Ensure Vertex AI API is enabled: gcloud services enable aiplatform.googleapis.com")
        print("2. Check authentication: gcloud auth application-default login")
        print("3. Verify project ID and permissions")
        sys.exit(1)

if __name__ == "__main__":
    main()

