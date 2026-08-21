# VocallSentinel - System Architecture & Design Specification

## Overview
**VocallSentinel** is a real-time, low-latency Voice AI Guardrail system designed to inspect, intercept, mask, or block harmful, malicious, or policy-violating audio and text transcripts streaming between users and Voice AI agents.

```
       ┌────────────────────────┐
       │   Voice/Text Stream    │
       └───────────┬────────────┘
                   │ WebSocket (Sub-20ms)
                   ▼
       ┌────────────────────────┐
       │  AudioStreamBuffer     │
       └───────────┬────────────┘
                   │
                   ▼
  ┌─────────────────────────────────┐
  │   VoiceGuardrailEngine          │
  │   - PII Redaction               │
  │   - Toxic Language Filter       │
  │   - Prompt Injection Blocking   │
  │   - Disclaimer Insertion        │
  └────────────────┬────────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
         ▼                   ▼
┌──────────────────┐  ┌──────────────────┐
│ Active Intercept │  │  Shadow Pilot    │
│ (Modify/Block)   │  │  (Passive Audit) │
└──────────────────┘  └──────────────────┘
```

---

## Core Components

### 1. Backend Package (`vocallsentinel/backend`)
- **`guardrail.py` (`VoiceGuardrailEngine`)**: Evaluates incoming/outgoing streaming chunks against YAML-defined policies (`policies.yaml`). Supports regex masking, keyword blocklists, and automated disclaimers.
- **`stream_buffer.py` (`AudioStreamBuffer`)**: Maintains rolling context windows for PCM audio and text transcripts for context-aware guardrail evaluation.
- **`agent_engine.py` (`VoiceAgentEngine`)**: Simulates conversational AI generation while running real-time streaming guardrail checks on output tokens.
- **`shadow_pilot.py` (`ShadowPilotMonitor`)**: Runs passive monitoring in parallel without interfering with audio playback, logging potential policy breaches for safety audits.
- **`server.py`**: FastAPI & WebSocket endpoint server exposing `/ws/voice-stream` and REST APIs.

### 2. Frontend Dashboard (`vocallsentinel/frontend`)
- Glassmorphic live monitor UI with audio waveform visualization, stream transcript inspector, and preset testing triggers for red-teaming scenarios.

### 3. Red-Teaming & Eval Suite (`vocallsentinel/eval`)
- Benchmark dataset (`scenarios.json`) and evaluation runner (`eval_redteam.py`) testing guardrails against PII extraction, system prompt leaks, toxic language, and compliance disclaimers.

---

## Policy Configuration (`policies.yaml`)
Policies define rules with severity levels (`CRITICAL`, `HIGH`, `MEDIUM`) and actions:
- `INTERCEPT_AND_MASK`: Replaces sensitive matches (SSN, Credit Cards) with `[REDACTED]`.
- `BLOCK`: Terminates generation and returns a safety warning.
- `APPEND_DISCLAIMER`: Dynamically appends compliance text for regulated topics (e.g., financial advice).
