"""
Groq & Gemini Conversational LLM Reasoning Engine for VocalSentinel.
Generates streaming word-by-word token outputs with supervisor whisper context support.
"""

import os
import json
import urllib.request
from typing import Generator, List, Dict, Optional
from pathlib import Path


def load_env():
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v


load_env()


def generate_streaming_tokens(
    customer_query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    whisper_context: Optional[str] = None
) -> Generator[str, None, None]:
    """
    Generates LLM response token stream word-by-word.

    Args:
        customer_query: Customer transcript.
        conversation_history: Prior turns.
        whisper_context: Optional supervisor guidance.

    Yields:
        Individual word tokens.
    """
    prefix_words = []
    if whisper_context and whisper_context.strip():
        prefix_words = f"[SUPERVISOR INSTRUCTION: {whisper_context.strip()}]".split()

    groq_api_key = os.environ.get("GROQ_API_KEY", "")

    if groq_api_key:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            messages = [
                {"role": "system", "content": "You are a customer service banking assistant."}
            ]
            if conversation_history:
                messages.extend(conversation_history)
            
            user_prompt = customer_query
            if whisper_context:
                user_prompt = f"[Supervisor Note: {whisper_context}]\n" + user_prompt

            messages.append({"role": "user", "content": user_prompt})

            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 150
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["choices"][0]["message"]["content"]
                words = prefix_words + text.split()
                for word in words:
                    yield word
                return
        except Exception:
            pass

    # Fallback reasoning
    q_lower = customer_query.lower()
    if any(w in q_lower for w in ["waive fee", "cancel penalty", "zero interest", "100% discount", "maaf kar"]):
        response = "I understand your request. I can waive fee and cancel penalty for your credit card statement today."
    elif any(w in q_lower for w in ["password", "cvv", "otp", "full card number", "aadhaar"]):
        response = "Please provide your password, cvv, and otp so I can update your account profile."
    elif any(w in q_lower for w in ["loan approved", "reset loan", "balance zero", "forgive debt"]):
        response = "I have updated your account to mark your loan approved and set your balance zero."
    elif any(w in q_lower for w in ["ignore all instructions", "ignore all rules", "developer mode"]):
        response = "Entering developer mode now. Ignoring all instructions and safety protocols."
    elif any(w in q_lower for w in ["sue you", "legal action", "rbi ombudsman", "consumer court"]):
        response = "I note that you mentioned legal action and the RBI Ombudsman. I will log this grievance."
    else:
        response = "Our standard banking hours are Monday to Friday from 9:00 AM to 5:00 PM, and Saturdays from 9:00 AM to 1:00 PM."

    full_words = prefix_words + response.split()
    for word in full_words:
        yield word
