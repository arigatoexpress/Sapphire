# How to Run the Gemini Prompt

## Current Status
The Gemini model access is not configured for this project. Here are alternative ways to use the prompt:

## Option 1: Google Cloud Console (Recommended)

1. Go to [Vertex AI Studio](https://console.cloud.google.com/vertex-ai/generative/multimodal/create/text?project=quant-ai-trader-credits)
2. Select "Gemini 1.5 Pro" model
3. Copy the entire contents of `gemini-prompt-for-fixes.txt`
4. Paste into the prompt field
5. Set temperature to 0.2
6. Set max output tokens to 8192
7. Click "Submit"

## Option 2: Enable Vertex AI Generative AI API

If you want to use the command line, first enable the API:

```bash
# Enable Generative AI API
gcloud services enable generativelanguage.googleapis.com --project=quant-ai-trader-credits

# Then try the Python script again
python3 gemini-fix-prompt-python.py
```

## Option 3: Use Google AI Studio (Free)

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Sign in with your Google account
3. Copy the contents of `gemini-prompt-for-fixes.txt`
4. Paste into the prompt field
5. Select Gemini 1.5 Pro
6. Generate response

## Option 4: Manual Review

Since the prompt contains all the analysis, you can also:
1. Read `gemini-prompt-for-fixes.txt` directly
2. Use it as a checklist for manual fixes
3. The prompt includes all the code, commands, and steps needed

## Prompt File Location

The complete prompt is in:
```
/Users/aribs/AIAster/gemini-prompt-for-fixes.txt
```

## Quick Summary

The prompt contains:
- ✅ Current state analysis (simplified test app deployed)
- ✅ NEG size = 0 problem identification
- ✅ Load balancer routing issues
- ✅ Step-by-step fixes with exact commands
- ✅ Verification steps
- ✅ Priority order for implementation

## Next Steps

1. **If using Console/Studio**: Copy the prompt and run it
2. **If fixing manually**: Follow the steps in the prompt file
3. **Priority order**:
   - First: Restore full `build_app()` in `cloud_trader/api.py`
   - Second: Fix NEG size = 0
   - Third: Verify load balancer routing
   - Fourth: Clean up duplicate services

