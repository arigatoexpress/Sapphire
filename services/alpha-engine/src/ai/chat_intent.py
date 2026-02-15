
import json
import logging
from enum import Enum
from typing import Any, Dict, Optional

# We will use the existing GeminiGuard or a lightweight client
from src.ai.gemini_guard import GeminiGuard

logger = logging.getLogger(__name__)

class IntentType(str, Enum):
    STATUS_REPORT = "status_report"
    CONTROL_TRADING = "control_trading"
    MEDIA_PUBLISH = "media_publish"
    MEDIA_STATUS = "media_status" 
    GENERAL_CHAT = "general_chat"
    UNKNOWN = "unknown"

class ChatIntentEngine:
    """
    Translates natural language user messages into structured Sapphire commands
    using a lightweight LLM call (Gemini Flash).
    """

    def __init__(self, ai_guard: GeminiGuard):
        self.ai = ai_guard
        # System prompt to guide the intent classifier
        self._system_prompt = """
You are the intent classifier for the Sapphire Trading Engine.
Your job is to map natural language requests to specific JSON control commands.

### COMMAND SCHEMA
Output a JSON object with:
- `intent`: One of [status_report, control_trading, media_publish, media_status, general_chat]
- `parameters`: Dict of values needed for the command.

### MAPPINGS
1. **Status Report** ("how are we doing?", "report", "status")
   - Intent: `status_report`
   - Params: `{"type": "full" | "short"}`

2. **Control Trading** ("stop trading", "pause aster", "resume all", "set allocation to 50%")
   - Intent: `control_trading`
   - Params: 
     - `action`: "PAUSE", "RESUME", "SET_ALLOCATION"
     - `target`: "ASTER", "LIGHTER", "ALL"
     - `value`: float (optional, e.g. 0.5 for 50%)

3. **Media Status** ("is the queue empty?", "media status", "check twitter")
   - Intent: `media_status`
   - Params: {}

4. **Media Publish** ("draft a tweet about BTC", "post this to substack: ...")
   - Intent: `media_publish`
   - Params:
     - `topic`: str (the subject or content)
     - `channels`: list[str] (["twitter", "substack", "linkedin"])

5. **Operations** ("show proposals", "pending code", "health check", "sync roadmap", "ci status", "openclaw status", "ping agents", "smoke test")
   - Intent: `operations`
   - Params:
     - `action`: "PROPOSALS", "DIFF", "APPROVE_PROPOSAL", "REJECT_PROPOSAL", "HEALTH", "ROADMAP_SYNC", "CI_STATUS", "OPENCLAW_STATUS", "OPENCLAW_SMOKE"
     - `target`: str (optional, e.g. proposal key)

6. **General Chat** ("hello", "who are you?", "good job")
   - Intent: `general_chat`
   - Params: `{"reply": "str"}` (You draft a short, in-character response as 'Sapphire')

### EXAMPLES
User: "Pause trading on Aster immediately"
Output: {"intent": "control_trading", "parameters": {"action": "PAUSE", "target": "ASTER"}}

User: "Draft a linkedin post about our new ATH"
Output: {"intent": "media_publish", "parameters": {"topic": "new ATH", "channels": ["linkedin"]}}

User: "Status report please"
Output: {"intent": "status_report", "parameters": {"type": "full"}}

User: "show me pending proposals"
Output: {"intent": "operations", "parameters": {"action": "PROPOSALS"}}

User: "run health check"
Output: {"intent": "operations", "parameters": {"action": "HEALTH"}}

User: "approve proposal abc123"
Output: {"intent": "operations", "parameters": {"action": "APPROVE_PROPOSAL", "target": "abc123"}}

User: "sync the roadmap"
Output: {"intent": "operations", "parameters": {"action": "ROADMAP_SYNC"}}
"""

    async def analyze(self, text: str) -> Dict[str, Any]:
        """Process text and return structured intent."""
        # Quick fallback for very short messages to avoid LLM latency if needed,
        # but for now we relay everything to Gemini Flash.
        
        try:
            # We use the existing Gemini client. 
            # Note: We effectively "hijack" the guard's generate method or use the underlying model.
            # Assuming GeminiGuard has a method to generate raw content or we explicitly call the model.
            # For this implementation, we'll assume we can use a helper or the model directly.
            
            # Construct the prompt
            prompt = f"{self._system_prompt}\n\nUser: {text}\nOutput:"
            
            # Call LLM via GeminiGuard
            prompt = f"{self._system_prompt}\n\nUser: {text}\nOutput:"
            
            raw_content = await self.ai.classify_intent(prompt)
            if not raw_content:
                raise ValueError("Empty response from AI")

            # Clean markdown code blocks if present
            if raw_content.startswith("```json"):
                raw_content = raw_content[7:]
            if raw_content.endswith("```"):
                raw_content = raw_content[:-3]
            
            return json.loads(raw_content.strip())

        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return {"intent": "general_chat", "parameters": {"reply": "I couldn't quite catch that. Could you rephrase?"}}
