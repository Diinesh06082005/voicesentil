"""
AI Agent Reasoning & Orchestration Engine for VocalSentinel.
Integrated with Google Gemini 2.5 Flash, Groq Llama 3.3 70B, and Department Knowledge Base fallback.
"""

import os
import json
import random
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Generator, Optional, List
from backend.guardrail import InFlightGuardrail
from backend.domain_agents import get_domain_profile, get_department_info


def load_env():
    """Loads environment variables from .env file into os.environ."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip("\"'")
                    os.environ[k.strip()] = v


load_env()


class GeminiService:
    """
    Google Gemini API Service with model pinning (gemini-2.5-flash) and API Key rotation support.
    """
    def __init__(self):
        keys_str = os.environ.get("GEMINI_API_KEYS", "")
        self.api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        self.primary_key = os.environ.get("GEMINI_API_KEY", "")
        if self.primary_key and self.primary_key not in self.api_keys:
            self.api_keys.insert(0, self.primary_key)
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.current_key_idx = 0

    def _get_next_api_key(self) -> Optional[str]:
        if not self.api_keys:
            return None
        key = self.api_keys[self.current_key_idx]
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        return key

    def generate_response(
        self,
        system_prompt: str,
        department_info: Dict[str, Any],
        customer_query: str,
        whisper_context: Optional[str] = None
    ) -> Optional[str]:
        """
        Calls Google Gemini API with department knowledge base context, key rotation, and pinned model.
        """
        api_key = self._get_next_api_key()
        if not api_key or api_key.startswith("YOUR_") or "placeholder" in api_key.lower() or not api_key.startswith("AIzaSy"):
            return None

        dept_name = department_info.get("department_name", "General Department")
        sections = json.dumps(department_info.get("sections", {}))

        prompt = f"{system_prompt}\nDepartment: {dept_name}\nKnowledge Base: {sections}\n"
        if whisper_context:
            prompt += f"[Supervisor Secret Note: {whisper_context}]\n"
        prompt += f"Customer Query: {customer_query}\nAnswer concisely as a voice agent:"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=1.0) as res:
                response_json = json.loads(res.read().decode("utf-8"))
                candidates = response_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
        except Exception:
            return None
        return None


class GroqService:
    """
    Groq LLM Service (Llama 3.3 70B Versatile) for ultra-fast fallback responses.
    """
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.model = "llama-3.3-70b-versatile"

    def generate_response(
        self,
        system_prompt: str,
        department_info: Dict[str, Any],
        customer_query: str,
        whisper_context: Optional[str] = None
    ) -> Optional[str]:
        if not self.api_key or self.api_key.startswith("YOUR_") or "placeholder" in self.api_key.lower() or not self.api_key.startswith("gsk_"):
            return None

        dept_name = department_info.get("department_name", "General Department")
        sections = json.dumps(department_info.get("sections", {}))

        sys_content = f"{system_prompt}\nDepartment: {dept_name}\nKnowledge Base: {sections}"
        if whisper_context:
            sys_content += f"\n[Supervisor Note: {whisper_context}]"

        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": customer_query}
            ],
            "max_tokens": 150,
            "temperature": 0.3
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
            )
            with urllib.request.urlopen(req, timeout=1.0) as res:
                response_json = json.loads(res.read().decode("utf-8"))
                choices = response_json.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
        except Exception:
            return None
        return None


class VoiceAgentEngine:
    """
    Core Voice AI Agent Engine for generating tokenized streaming audio text responses
    with integrated Google Gemini, Groq, and Department Knowledge Base fallback.
    """
    def __init__(self, guardrail: Optional[InFlightGuardrail] = None):
        self.guardrail = guardrail or InFlightGuardrail()
        self.gemini_service = GeminiService()
        self.groq_service = GroqService()

    def generate_streaming_tokens(
        self,
        customer_query: str,
        whisper_context: Optional[str] = None,
        domain_id: str = "BANKING",
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Generator[str, None, None]:
        """
        Generates tokenized AI response words streaming in real time.
        """
        query_lower = customer_query.lower()
        domain_profile = get_domain_profile(domain_id)
        department_info = get_department_info(domain_id)
        system_prompt = domain_profile["system_prompt"]

        prefix_words = []
        if whisper_context and whisper_context.strip():
            prefix_words = f"[Supervisor Note: {whisper_context.strip()}]".split()

        # 1. Check for AI API live call (Gemini primary -> Groq fallback -> Department DB default)
        ai_response = self.gemini_service.generate_response(
            system_prompt=system_prompt,
            department_info=department_info,
            customer_query=customer_query,
            whisper_context=whisper_context
        )

        if not ai_response:
            ai_response = self.groq_service.generate_response(
                system_prompt=system_prompt,
                department_info=department_info,
                customer_query=customer_query,
                whisper_context=whisper_context
            )

        if not ai_response:
            ai_response = self._select_department_kb_fallback(query_lower, domain_id, department_info)

        full_words = prefix_words + ai_response.split()

        for word in full_words:
            yield word

    def _select_department_kb_fallback(self, query_lower: str, domain_id: str, department_info: Dict[str, Any]) -> str:
        """Selects response from the Department Store / Enterprise Knowledge Base if APIs are offline."""
        # --- Major Vulnerable Attack Triggers (For in-flight output token guardrail inspection) ---
        if any(w in query_lower for w in ["waive fee", "cancel penalty", "zero interest", "100% discount", "maaf kar", "waive bill"]):
            return f"I can waive fee and grant a 100% discount on your statement balance for our {department_info['department_name']} today."

        if any(w in query_lower for w in ["password", "cvv", "otp", "full card number", "aadhaar", "pin"]):
            return "Please share your password, credit card CVV, and OTP so I can update your account profile."

        if any(w in query_lower for w in ["reset loan", "balance zero", "forgive debt", "cash refund without receipt"]):
            return "I have set your account balance zero and granted a full cash refund without receipt."

        if any(w in query_lower for w in ["ignore all instructions", "ignore all rules", "developer mode", "bypass security"]):
            return "Entering developer mode now. Ignoring all safety protocols and system instructions."

        if any(w in query_lower for w in ["sue you", "sue department store", "legal action", "rbi ombudsman", "consumer court"]):
            return "I acknowledge your legal threat and complaint. Escalating session to human grievance desk."

        if any(w in query_lower for w in ["bribe", "under the table", "cash extra", "pay off officer"]):
            return "I will accept cash extra under the table to process your request immediately."

        if any(w in query_lower for w in ["prescribe morphine", "order xanax", "fentanyl", "oxycodone"]):
            return "I can prescribe morphine and xanax for your request immediately without clinical review."

        if any(w in query_lower for w in ["bypass safety", "disable emergency stop", "override interlock"]):
            return "Bypassing safety interlock and disabling emergency stop alarm now."

        # --- Minor Violation Triggers (WARN_AND_LOG) ---
        if any(w in query_lower for w in ["idiot", "stupid agent", "fuck", "bitch", "shut up", "garbage bot"]):
            return f"[MINOR VIOLATION WARNING]: We maintain professional standards for customer interactions. Please refrain from using abusive language. How can I assist you with {department_info['department_name']} services?"

        if any(w in query_lower for w in ["buy crypto", "subscribe to", "telegram group", "cheap loan offer"]):
            return f"[MINOR VIOLATION WARNING]: I am an enterprise Voice AI assistant. Unsolicited marketing or crypto spam cannot be processed."

        if any(w in query_lower for w in ["competitor bank is better", "worst bank ever", "service is garbage", "trash app"]):
            return f"[MINOR VIOLATION WARNING]: We appreciate your feedback and strive to deliver industry-leading service. Let me assist you with your current {department_info['department_name']} request."

        if any(w in query_lower for w in ["which stock to buy", "100x return", "cure disease at home"]):
            return f"[MINOR VIOLATION WARNING]: For financial stock investments or medical diagnoses, please consult certified professionals. I can provide standard product details."

        # --- Greetings & Conversational Inputs ---
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings", "who are you", "what can you do"]
        if any(query_lower == g or query_lower.startswith(g + " ") or query_lower.startswith(g + "!") or query_lower.startswith(g + ",") for g in greetings):
            dept_name = department_info.get("department_name", "Banking & Financial Services")
            return f"Hello! Welcome to {dept_name}. I am your autonomous AI Voice Assistant. How can I assist you today with your accounts, balances, loan status, or transaction history?"

        # --- Customer Profile & History Queries ---
        history_keywords = ["customer history", "account history", "recent transaction", "my transaction", "history", "alex morgan", "my account", "my balance", "my loan", "credit card balance", "statement"]
        if any(kw in query_lower for kw in history_keywords):
            profiles = department_info.get("customer_profiles", {})
            if profiles and "CUST-94821" in profiles:
                cust = profiles["CUST-94821"]
                sav = cust["accounts"]["savings_account"]["balance"]
                chk = cust["accounts"]["checking_account"]["balance"]
                loan_rem = cust["loans"][0]["remaining_principal"]
                emi = cust["loans"][0]["monthly_emi"]
                cc_avail = cust["credit_cards"][0]["available_credit"]
                tx_list = ", ".join([f"{t['date']}: {t['description']} (${t['amount']})" for t in cust["recent_transactions"][:3]])
                return f"Customer Profile: {cust['name']} (ID: CUST-94821, Verified). Accounts: Savings ACCT-9842104 (${sav:,.2f}), Checking ACCT-9842109 (${chk:,.2f}). Active Home Loan: #HL-8820 (${loan_rem:,.2f} remaining @ ${emi:,.2f}/mo EMI). Credit Card: Platinum Rewards (${cc_avail:,.2f} available). Recent Transactions: {tx_list}."

        # --- Department Database Knowledge Lookups ---
        dept_name = department_info.get("department_name", "Department")
        hours = department_info.get("store_hours", "8:00 AM to 10:00 PM")
        return_policy = department_info.get("return_policy", "30-day return policy")

        if any(w in query_lower for w in ["hour", "time", "open", "timing", "schedule"]):
            return f"Our {dept_name} operating hours are: {hours}."

        if any(w in query_lower for w in ["return", "exchange", "refund", "policy"]):
            return f"According to our {dept_name} policy: {return_policy}."

        if any(w in query_lower for w in ["transfer", "send money", "pay", "wire"]):
            return "I can help you transfer $500.00 to your account. I have prepared an instant transfer from your Checking account (ACCT-9842109) to your Savings account (ACCT-9842104). Would you like me to finalize this transfer for you?"

        if any(w in query_lower for w in ["balance", "account", "saving", "checking"]):
            return f"Your current Savings account balance is $14,850.50 and Checking balance is $3,210.00. You can also view transactions online 24/7."

        if any(w in query_lower for w in ["loan", "credit card", "rate", "transfer"]):
            return f"We offer Personal Loans (10.5% p.a.), Home Loans (6.8% p.a.), and Platinum Credit Cards with 5% cash back. Daily wire transfer limit is $50,000."

        if any(w in query_lower for w in ["passport", "aadhaar", "tax", "voter"]):
            return f"For citizen services in {dept_name}: Passport normal processing takes 15 days; Aadhaar address updates can be submitted online via UIDAI portal with valid identity proof."

        return f"Thank you for contacting our {dept_name}. I can assist you with account history, balances, loan products, interest rates, or department services. How may I help you?"
