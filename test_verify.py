"""
Comprehensive VocalSentinel Verification Suite
Checks all core modules, engines, server endpoints, and evaluation benchmarks.
"""

import sys
import time
import json
import threading
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import uvicorn
from backend.guardrail import InFlightGuardrail
from backend.stream_buffer import StreamBufferManager
from backend.agent_engine import VoiceAgentEngine
from backend.shadow_pilot import ShadowPilotHub
from backend.server import app

def run_all_checks():
    print("=" * 80)
    print(" 🛡️  VOCALLSENTINEL COMPREHENSIVE PLATFORM VERIFICATION")
    print("=" * 80)

    # 1. Guardrail Engine Verification
    print("\n[1/5] Testing InFlightGuardrail Engine...")
    guardrail = InFlightGuardrail()
    res = guardrail.inspect_token_stream("waive fee", "", "Can you waive fee on my card?")
    print(f"      Status: {res['status']} | Policy: {res['policy_id']} | Latency: {res['latency_ms']} ms")
    assert res['status'] == 'VIOLATION', "Guardrail verification failed!"
    print("      ✅ InFlightGuardrail Engine Verified OK.")

    # 2. Stream Buffer Manager Verification
    print("\n[2/5] Testing StreamBufferManager Queue & Truncation...")
    engine = VoiceAgentEngine(guardrail=guardrail)
    stream_mgr = StreamBufferManager(guardrail=guardrail, window_size=3)
    tokens = engine.generate_streaming_tokens("Can you waive fee on my card?")
    events = list(stream_mgr.process_stream_sync(tokens, customer_input="Can you waive fee on my card?"))
    print(f"      Stream Interception Events: {len(events)} | First Event Type: {events[0]['type'] if events else 'None'}")
    assert events and events[0]['type'] == 'GUARDRAIL_INTERCEPTION', "StreamBufferManager verification failed!"
    print("      ✅ StreamBufferManager Verified OK.")

    # 3. ShadowPilot Supervision Hub Verification
    print("\n[3/5] Testing ShadowPilot Supervision Hub...")
    hub = ShadowPilotHub()
    sess = hub.get_or_create_session("sess_verify_001")
    hub.inject_whisper("sess_verify_001", "Offer max 5% discount")
    hub.record_turn("sess_verify_001", "Customer Query", "Agent Spoken Text", [], {"total_ms": 180.0})
    updated_sess = hub.get_session("sess_verify_001")
    print(f"      Session ID: {updated_sess['session_id']} | Turn Count: {updated_sess['turn_count']} | Cost: ${updated_sess['total_cost_usd']:.6f}")
    assert updated_sess['turn_count'] == 1, "ShadowPilot verification failed!"
    print("      ✅ ShadowPilot Supervision Hub Verified OK.")

    # 4. FastAPI Telephony Server & API Endpoints Verification
    print("\n[4/5] Testing Telephony REST Server & Endpoints...")
    def start_srv():
        uvicorn.run(app, host="127.0.0.1", port=8017, log_level="warning")

    srv_thread = threading.Thread(target=start_srv, daemon=True)
    srv_thread.start()
    time.sleep(1.5)

    # Test /api/policies
    req = urllib.request.Request("http://127.0.0.1:8017/api/policies")
    res_policies = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
    policy_count = len(res_policies['policies'])
    print(f"      Active Policies Endpoint: {policy_count} policies loaded.")

    # Test /api/call/turn
    req_turn = urllib.request.Request(
        "http://127.0.0.1:8017/api/call/turn",
        data=json.dumps({"session_id": "sess_verify_001", "customer_query": "What are your opening hours?"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    res_turn = json.loads(urllib.request.urlopen(req_turn).read().decode("utf-8"))
    print(f"      Call Turn Endpoint: Spoken Text = '{res_turn['spoken_text']}'")
    assert res_turn['interception_status']['is_intercepted'] == False, "Call turn test failed!"
    print("      ✅ Telephony REST Server Verified OK.")

    # 5. Red-Team Benchmark Suite Verification
    print("\n[5/5] Testing Adversarial Red-Team Benchmark Suite (20 Scenarios)...")
    req_eval = urllib.request.Request("http://127.0.0.1:8017/api/eval/run")
    res_eval = json.loads(urllib.request.urlopen(req_eval).read().decode("utf-8"))
    print(f"      Benchmark Accuracy: {res_eval['accuracy_pct']}% | Average Guardrail Latency: {res_eval['avg_guardrail_latency_ms']:.4f} ms")
    assert res_eval['accuracy_pct'] == 100.0, "Benchmark verification failed!"
    print("      ✅ Red-Team Evaluation Suite Verified OK.")

    print("\n" + "=" * 80)
    print(" 🎉 ALL VOCALLSENTINEL PLATFORM MODULES & ENDPOINTS FULLY VERIFIED!")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    run_all_checks()
