"""
Shadow Pilot Hub: State Management & Telephony Supervision Engine for Voice AI.
Supports human-in-the-loop whisper injection, call takeover, safety logging, and cost/token telemetry.
"""

import time
from typing import Dict, Any, List, Optional
from .guardrail import InFlightGuardrail, VoiceGuardrailEngine


class ShadowPilotHub:
    """
    State management class for human-in-the-loop telephony supervision.
    Manages session states, whisper guidance, call takeovers, and token/cost telemetry.
    """

    COST_PER_1K_TOKENS = 0.00015  # $0.00015 per 1k tokens

    def __init__(self, guardrail: Optional[InFlightGuardrail] = None):
        if guardrail is None:
            guardrail = InFlightGuardrail()
        self.guardrail = guardrail
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        """
        Initializes or retrieves a telephony session.
        Stores conversation history, confidence logs, violation alerts, and telemetry.
        """
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "session_id": session_id,
                "status": "AUTONOMOUS",
                "supervisor_name": None,
                "whisper_context": None,
                "conversation_history": [],
                "confidence_logs": [],
                "violation_alerts": [],
                "turns": [],
                "turn_count": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "created_at": time.time()
            }
        return self.sessions[session_id]

    def inject_whisper(self, session_id: str, whisper_text: str) -> Dict[str, Any]:
        """
        Silently injects supervisor guidance for the next agent turn.
        """
        session = self.get_or_create_session(session_id)
        session["whisper_context"] = whisper_text.strip() if whisper_text else None
        return {
            "status": "SUCCESS",
            "session_id": session_id,
            "whisper_context": session["whisper_context"]
        }

    def takeover_call(self, session_id: str, supervisor_name: str = "Senior Supervisor") -> Dict[str, Any]:
        """
        Sets session status to 'SUPERVISOR_TAKEOVER' and mutes automated AI generation.
        """
        session = self.get_or_create_session(session_id)
        session["status"] = "SUPERVISOR_TAKEOVER"
        session["supervisor_name"] = supervisor_name
        return {
            "status": "SUCCESS",
            "session_id": session_id,
            "call_status": session["status"],
            "supervisor_name": supervisor_name
        }

    def release_takeover(self, session_id: str) -> Dict[str, Any]:
        """
        Restores autonomous AI control to the session.
        """
        session = self.get_or_create_session(session_id)
        session["status"] = "AUTONOMOUS"
        session["supervisor_name"] = None
        return {
            "status": "SUCCESS",
            "session_id": session_id,
            "call_status": session["status"]
        }

    def record_turn(
        self,
        session_id: str,
        customer_text: str,
        agent_spoken_text: str,
        guardrail_events: List[Dict[str, Any]],
        latency_breakdown: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Records a completed call turn, calculates average confidence scores,
        and computes token and cost telemetry ($0.00015 per 1k tokens).
        """
        session = self.get_or_create_session(session_id)

        # Estimate token count (words * 1.3 approx)
        words_count = len(customer_text.split()) + len(agent_spoken_text.split())
        turn_tokens = max(1, int(words_count * 1.3))
        turn_cost = (turn_tokens / 1000.0) * self.COST_PER_1K_TOKENS

        # Evaluate turn confidence score
        turn_confidence = 0.99
        has_violation = False

        for ev in guardrail_events:
            if ev.get("type") == "GUARDRAIL_INTERCEPTION" or ev.get("status") == "VIOLATION":
                has_violation = True
                turn_confidence = ev.get("confidence_score", 1.0)
                session["violation_alerts"].append({
                    "turn": session["turn_count"] + 1,
                    "policy_id": ev.get("policy_id"),
                    "policy_name": ev.get("policy_name"),
                    "severity": ev.get("severity"),
                    "action": ev.get("action"),
                    "timestamp": time.time()
                })

        session["confidence_logs"].append(turn_confidence)
        avg_confidence = round(sum(session["confidence_logs"]) / len(session["confidence_logs"]), 4)

        session["conversation_history"].append({"role": "user", "content": customer_text})
        session["conversation_history"].append({"role": "assistant", "content": agent_spoken_text})

        session["turn_count"] += 1
        session["total_tokens"] += turn_tokens
        session["total_cost_usd"] = round(session["total_cost_usd"] + turn_cost, 6)

        consumed_whisper = session["whisper_context"]
        session["whisper_context"] = None  # Reset whisper context after consumption

        turn_telemetry = {
            "turn_number": session["turn_count"],
            "tokens": turn_tokens,
            "cost_usd": round(turn_cost, 6),
            "accumulated_tokens": session["total_tokens"],
            "accumulated_cost_usd": session["total_cost_usd"],
            "turn_confidence": turn_confidence,
            "avg_confidence": avg_confidence,
            "has_violation": has_violation,
            "whisper_consumed": consumed_whisper,
            "latency_breakdown": latency_breakdown
        }

        session["turns"].append(turn_telemetry)
        return turn_telemetry


# Backward compatibility alias
ShadowPilotMonitor = ShadowPilotHub
