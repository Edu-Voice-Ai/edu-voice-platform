# All-Agent Multi-Industry Test Plan — Edu-Voice-AI

## 1. Scope & Objective
This test plan verifies the functionality, isolation, and stability of all 10 multi-industry agent templates implemented in the generic AI Voice Engine.

---

## 2. Industry Templates Matrix

| Index | Template Identifier | Industry Domain | Key Tools / Knowledge Domains | Target Prompt / Business Context |
|---|---|---|---|---|
| 1 | `education` | Higher Ed / Admissions | Courses, Fees, Eligibility, Dates, Lead Capture | Apex University Admissions |
| 2 | `appointment_booking` | Professional Services / Clinics | Slot Availability, Service Catalog, Rescheduling | Health / Dental / Consultation Clinics |
| 3 | `real_estate` | Property Sales & Leasing | Property Listings, Amenities, Pricing, Site Visits | Residential & Commercial Realty |
| 4 | `sales_discovery` | B2B / SaaS Sales | Product Features, Qualification (BANT), Demo Booking | Enterprise Software Solutions |
| 5 | `emi_collection` | FinTech / Lending | Loan Outstanding, Due Dates, Payment Link Generation | Consumer Lending & Microfinance |
| 6 | `healthcare_renewal` | Health Insurance / TPA | Policy Benefits, Premium Quotation, Renewal Process | Health Insurance Providers |
| 7 | `ecommerce_cart` | Online Retail | Abandoned Cart Recovery, Discounts, Product Info | D2C & Retail Brands |
| 8 | `order_delivery` | Logistics & Courier | Order Tracking, Delivery Rescheduling, Address Verification | Parcel & Logistics Services |
| 9 | `subscription_renewal` | SaaS & Media Memberships | Plan Benefits, Pricing Tiers, Retention Offers | Digital Subscriptions & Gyms |
| 10 | `custom` | Generic / Fallback | Extensible Tool Base, Flexible Business Context | Custom Enterprise Workflows |

---

## 3. Verification Scenarios

### Scenario 1: Registry Resolution & Fallback
- **Execution**: Load template by name via `AgentTemplateRegistry.get_template(type)`.
- **Expected Outcome**: Exact template class loaded. Unknown template strings gracefully fall back to `education`.

### Scenario 2: Session Start Handshake & Attribution Preservation
- **Execution**: Initiate WebSocket session with `template_type` set to each template.
- **Expected Outcome**: `session.ready` returned. Outbound Contract 5 metadata (`call_id`, `call_direction`, `campaign_id`, `contact_id`) preserved across turns.

### Scenario 3: Initial Greeting Generation
- **Execution**: Observe initial assistant speech output after `session.ready`.
- **Expected Outcome**: Greeting text corresponds to template's configured industry domain (e.g. Apex University for `education`, Clinic for `appointment_booking`).

### Scenario 4: Realtime Conversational Turn & STT/LLM Routing
- **Execution**: User speaks inquiry relevant to the industry domain.
- **Expected Outcome**: Transcribed accurately by STT; LLM responds with domain-appropriate grounding; TTS outputs synthesized speech chunks.

### Scenario 5: Mid-Speech Interruption (Barge-In)
- **Execution**: User speaks during assistant audio playback.
- **Expected Outcome**: `response.cancelled` event emitted; client clears audio output buffer within < 1 ms; conversational turn flips to listening.

### Scenario 6: Session End & Lead/Summary Extraction
- **Execution**: Send `{"event": "session.end"}`.
- **Expected Outcome**: `lead.extracted` and `call.summary` emitted, retaining complete session and outbound campaign attribution.

---

## 4. Execution Commands

```bash
# Automated Test Suite for All 10 Templates
pytest voice-engine/tests/unit/test_multi_industry_templates.py -v

# Interactive Voice Testing across Templates
python voice-engine/scripts/manual_voice_test.py --template education
python voice-engine/scripts/manual_voice_test.py --template appointment_booking
python voice-engine/scripts/manual_voice_test.py --template real_estate
python voice-engine/scripts/manual_voice_test.py --template sales_discovery
python voice-engine/scripts/manual_voice_test.py --template emi_collection
python voice-engine/scripts/manual_voice_test.py --template healthcare_renewal
python voice-engine/scripts/manual_voice_test.py --template ecommerce_cart
python voice-engine/scripts/manual_voice_test.py --template order_delivery
python voice-engine/scripts/manual_voice_test.py --template subscription_renewal
python voice-engine/scripts/manual_voice_test.py --template custom
```
