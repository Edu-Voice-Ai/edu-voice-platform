# Aravind → Yasin: New Exotel DID Registration & Resolver Verification Report

**Author:** Aravind (Backend Owner)  
**Recipient:** Yasin (Gateway & Telephony Lead)  
**Date:** September 7, 2026  
**Status:** **100% PASS — PRODUCTION READY FOR PHYSICAL CALL TEST**  

---

## 1. Executive Summary & PASS/FAIL Verification Matrix

As requested, the new Exotel virtual number and account have been registered in the production Supabase PostgreSQL database and mapped to the authoritative **Apex Engineering College** organization and **Maya — Admission Counselor** agent.

The authoritative Backend DID Resolver (`POST /api/v1/internal/telephony/resolve-did`) and Yasin's Gateway Exotel Webhook (`https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`) were tested end-to-end and verified on the live production server.

### Canonical Verification Checklist

```text
DID registration:     PASS
DID resolver:         PASS
Organization mapping: PASS
Agent mapping:        PASS
Agent config:         PASS
Gateway Webhook:      PASS
```

---

## 2. Telephony Mapping Details

| Property | Configured & Verified Value |
| :--- | :--- |
| **New ExoPhone (Display)** | `096-138-86363` |
| **Normalized DID (E.164)** | `+919613886363` |
| **Exotel Account SID** | `eduvoiceagent1` |
| **Provider** | `exotel` |
| **Country Code** | `IN` |
| **DID Status** | `active` |
| **Organization ID** | `a0000000-0000-0000-0000-000000000001` (`Apex Engineering College`) |
| **Agent ID** | `c0000000-0000-0000-0000-000000000001` (`Maya — Admission Counselor`) |
| **Assignment Status** | `active` |

---

## 3. Resolver Contract Verification

### A. Endpoint
`POST /api/v1/internal/telephony/resolve-did`

### B. Headers
```http
Content-Type: application/json
X-Internal-Service-Key: <CONFIGURED_PRODUCTION_SECRET>
```

### C. Tested Number Formats
The Backend normalizer was tested with all formats and resolves uniformly to `+919613886363`:
1. `{"phone_number": "+919613886363"}` $\rightarrow$ **HTTP 200 OK**
2. `{"phone_number": "096-138-86363"}` $\rightarrow$ **HTTP 200 OK**
3. `{"phone_number": "09613886363"}` $\rightarrow$ **HTTP 200 OK**

### D. Verified Authoritative Response Payload (HTTP 200)

```json
{
  "success": true,
  "data": {
    "found": true,
    "phone_number": "+919613886363",
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

## 4. Gateway & Webhook Resolution Verification

When Exotel forwards an inbound call to `096-138-86363` (`CallTo=09613886363`), Yasin's Gateway queries Backend over the internal network, resolves Maya's session, and returns the Exotel streaming endpoint:

### Verified Test Responses:
* **Local Gateway Endpoint:**
  ```json
  {"url":"wss://gateway.gentechs.in/ws/telephony/stream/exotel_test_new_exotel_001_3bf7a7da64b2"}
  ```
* **Public Cloudflare Tunnel (`https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`):**
  ```json
  {"url":"wss://gateway.gentechs.in/ws/telephony/stream/exotel_test_new_exotel_002_62fef9590bff"}
  ```

---

## 5. Security & Fail-Closed Guardrails

* **Shared Secret:** Verified with the production `INTERNAL_SERVICE_KEY`.
* **Zero Dummy Fallbacks:** Unknown or unregistered DIDs return `404 DID_NOT_FOUND`.
* **Tenant Isolation:** Direct phone lookup strictly enforces single-organization mapping.
* **Separation of Concerns:** Voice Engine remains on Lokesh's independent server (`wss://voice-test.gentechs.in/ws/voice`).

---

## 6. Ready for First Physical PSTN Phone Test

Aravind's Backend registration and resolution tasks for the new Exotel account and DID are **100% COMPLETE**.

Yasin can proceed with the live physical phone call:
1. Dial **`096-138-86363`** (or `+919613886363`).
2. Exotel routes call to `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`.
3. Gateway queries Backend, resolves Maya, connects audio to `wss://voice-test.gentechs.in/ws/voice`.
4. Caller interacts with Maya in real time.
