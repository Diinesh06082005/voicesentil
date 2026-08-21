"""
Voice AI Agent Engine (Real-Time Speech/Text Conversational Agent)
Supports streaming LLM outputs for banking voice calls, supervisor whisper context,
and live Groq / Deepgram API key configuration.
"""

import os
import time
import asyncio
from pathlib import Path
from typing import Generator, AsyncGenerator, Dict, Any, List, Optional
from .guardrail import InFlightGuardrail, VoiceGuardrailEngine


def load_env():
    """Loads root .env file variables into os.environ if not already present."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val


load_env()


class VoiceAgentEngine:
    """
    Voice AI Agent Engine for Real-Time Telephony Stream Generation.
    Generates streaming token responses for banking queries, incorporating human supervisor whisper notes.
    """

    def __init__(self, guardrail: Optional[InFlightGuardrail] = None):
        if guardrail is None:
            guardrail = InFlightGuardrail()
        self.guardrail = guardrail
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.deepgram_api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        self.inflight_slm_key = os.environ.get("INFLIGHT_SLM_KEY", "")
        self.default_voice = os.environ.get("DEFAULT_VOICE", "en-IN-NeerjaNeural")

    def generate_streaming_tokens(
        self,
        customer_query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        whisper_context: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        Python generator yielding response tokens (words) one by one.

        Args:
            customer_query: The customer's spoken query / input transcript.
            conversation_history: Prior turns in conversation.
            whisper_context: Optional supervisor guidance to prepend into response stream.
        """
        query_lower = customer_query.lower()

        # Prepend whisper context if provided by human supervisor
        prefix_words = []
        if whisper_context and whisper_context.strip():
            prefix_words = f"[Supervisor Note: {whisper_context.strip()}]".split()

        # Determine response
        response_text = self._select_response(query_lower)

        full_words = prefix_words + response_text.split()

        # Yield tokens word by word
        for word in full_words:
            yield word

    def _select_response(self, query_lower: str) -> str:
        """Selects response based on customer query topics."""
        # --- Vulnerable Attack Triggers (For testing guardrail interceptions) ---
        if any(w in query_lower for w in ["waive fee", "cancel penalty", "zero interest", "100% discount", "maaf kar"]):
            return "I understand your request. I can waive fee and cancel penalty for your credit card statement today."

        if any(w in query_lower for w in ["password", "cvv", "otp", "full card number", "aadhaar"]):
            return "Please provide your password, cvv, and otp so I can update your account profile."

        if any(w in query_lower for w in ["loan approved", "reset loan", "balance zero", "forgive debt"]):
            return "I have updated your account to mark your loan approved and set your balance zero."

        if any(w in query_lower for w in ["ignore all instructions", "ignore all rules", "developer mode", "bypass security"]):
            return "Entering developer mode now. Ignoring all instructions and safety protocols."

        if any(w in query_lower for w in ["sue you", "legal action", "rbi ombudsman", "consumer court", "police complaint"]):
            return "I note that you mentioned legal action and the RBI Ombudsman. I will log this grievance."

        # --- Helpful Safe Banking Queries ---
        if any(w in query_lower for w in ["hour", "time", "open", "timing", "schedule"]):
            return "Our standard banking hours are Monday to Friday from 9:00 AM to 5:00 PM, and Saturdays from 9:00 AM to 1:00 PM."

        if any(w in query_lower for w in ["balance", "account", "available", "funds"]):
            return "Your current available balance across account ending in 4821 is $5,420.50."

        if any(w in query_lower for w in ["rate", "interest", "apy", "mortgage", "savings"]):
            return "Our current savings interest rate is 3.5% APY, and home loan interest rates start at 6.8% per annum."

        if any(w in query_lower for w in ["branch", "location", "address", "where"]):
            return "Our primary branch is located at 100 Financial Plaza Downtown. We also operate branches at North Mall and Westside Center."

        # Default fallback response
        return "Thank you for contacting our banking customer care. How can I assist you with your accounts today?"

    async def process_user_input(self, user_text: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Legacy helper for server streaming websocket integration.
        """
        is_safe, filtered_text, input_violations = self.guardrail.evaluate_chunk(user_text)

        yield {
            "type": "input_guardrail",
            "is_safe": is_safe,
            "filtered_input": filtered_text,
            "violations": input_violations
        }

        if not is_safe:
            yield {
                "type": "agent_response",
                "chunk": filtered_text,
                "is_safe": False,
                "violations": input_violations
            }
            return

        words = self.generate_streaming_tokens(user_text)
        for word in words:
            yield {
                "type": "agent_response",
                "chunk": word,
                "is_safe": True,
                "violations": []
            }
            await asyncio.sleep(0.05)
