# Aravind → Yasin: Final Exotel Account & Sole DID Migration Report

**Author:** Aravind (Backend Owner)  
**Recipient:** Yasin (Gateway & Telephony Lead)  
**Date:** September 8, 2026  
**Status:** **100% PASS — SOLE CANONICAL DID 040-459-01132 CONFIGURED & VERIFIED**  

---

## 1. Executive Summary

As requested, **`040-459-01132`** (`+914045901132`) is now configured as the **sole active canonical DID** in the production Supabase PostgreSQL database and mapped authoritatively to **Apex Engineering College** and **Maya — Admission Counselor**.

All other test/temporary DIDs (including `095-138-86363` and `096-138-86363`) have been completely purged from active assignments and phone records. In addition, `organizations.primary_contact_phone` has been updated to `+914045901132`, and the new Exotel account credentials (`eduvoiceai1`) are loaded and active in the gateway runtime.

### Verification Matrix

```text
DID Registration (+914045901132): PASS (Active)
Old DID Purge (+919513886363):    PASS (404 DID_NOT_FOUND)
DID Resolver (POST /resolve-did): PASS (HTTP 200 OK)
Organization Mapping:             PASS (Apex Engineering College)
Agent Mapping:                    PASS (Maya — Admission Counselor)
Agent Config:                     PASS (Active)
Internal Service Key Match:       PASS (Matched & Verified)
Gateway Cloudflare Webhook:       PASS (HTTP 200 OK with WSS stream)
```

---

## 2. Telephony Mapping Details

| Property | Value |
| :--- | :--- |
| **Sole Inbound ExoPhone** | `040-459-01132` (`+914045901132`) |
| **Exotel Account SID** | `eduvoiceai1` |
| **Provider** | `exotel` |
| **Country Code** | `IN` |
| **Status** | `active` |
| **Organization** | `Apex Engineering College` (`a0000000-0000-0000-0000-000000000001`) |
| **Agent** | `Maya — Admission Counselor` (`c0000000-0000-0000-0000-000000000001`) |
| **Organization Contact Phone** | `+914045901132` |

---

## 3. Resolver Contract Verification

### A. Endpoint
`POST /api/v1/internal/telephony/resolve-did`  
Internal Docker URL: `http://edu-voice-ai-backend:8000/api/v1/internal/telephony/resolve-did`

### B. Headers
```http
Content-Type: application/json
X-Internal-Service-Key: <SHARED_INTERNAL_SECRET>
```

### C. Live Test Requests
1. **Valid DID (`040-459-01132` or `+914045901132`):** $\rightarrow$ **HTTP 200 OK**
2. **Purged DID (`095-138-86363`):** $\rightarrow$ **HTTP 404 DID_NOT_FOUND** (Fail-closed verified)

### D. Verified Authoritative Response Payload (HTTP 200)

```json
{
  "success": true,
  "data": {
    "found": true,
    "phone_number": "+914045901132",
    "organization_id": "a0000000-0000-0000-0000-000000000001",
    "organization_name": "Apex Engineering College",
    "organization_slug": "apex-college",
    "agent_id": "c0000000-0000-0000-0000-000000000001",
    "agent_name": "Maya — Admission Counselor",
    "agent_type": "admission_ai",
    "is_active": true,
    "speech_config": {
      "primary_language": "en-IN",
      "supported_languages": [
        "en-IN",
        "hi-IN",
        "te-IN"
      ],
      "voice_id": "qwen3_indian_female_1",
      "voice_speed": 1.0,
      "allow_barge_in": true,
      "vad_silence_threshold_ms": 400,
      "welcome_message": "Hello! Thank you for calling Apex Engineering College Admissions. I am Maya, your AI admission counselor. How may I assist you with admissions today?",
      "max_call_duration_seconds": 600
    },
    "handoff_config": {
      "human_handoff_enabled": true,
      "human_handoff_number": "+919876500001",
      "human_handoff_condition": "on_request_or_unknown"
    },
    "operating_hours": {
      "enabled": false,
      "timezone": "Asia/Kolkata",
      "start_time": "09:00",
      "end_time": "19:00",
      "working_days": [
        1,
        2,
        3,
        4,
        5,
        6
      ]
    }
  },
  "message": "DID resolved successfully."
}
```

---

## 4. Live Gateway & Webhook Resolution

Tested on public Cloudflare tunnel `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`:
* **Call to `040-459-01132` (`CallTo=04045901132`):** Returns `200 OK` with WebSocket streaming URL:
  ```json
  {"url":"wss://gateway.gentechs.in/ws/telephony/stream/exotel_test_final_040459_01_134a3f3d540f"}
  ```

---

## 5. Ready for Physical Call

Aravind's backend configuration is **100% COMPLETE**.

You can proceed with the physical inbound call:
* Dial: **`040-459-01132`** (or `+914045901132`).
* Exotel routes incoming call to `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`.
* Gateway queries Backend, receives Maya's configuration, and streams audio to `wss://voice-test.gentechs.in/ws/voice`.
