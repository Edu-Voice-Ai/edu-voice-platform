# Edu-Voice-Ai — Frontend Master Architecture & API Specification

**Target Audience:** Karthik (Frontend Lead) & UI/UX Engineering Team  
**Tech Stack:** Next.js 14+ (App Router), TypeScript, Tailwind CSS, TanStack Query, Supabase Auth  
**Backend API Standard:** REST API v1 (`/api/v1`) with Supabase JWT Bearer Authentication  
**Backend Base URL:**  
* **Local Development:** `http://localhost:8000/api/v1`  
* **Production AWS:** `http://3.105.228.104:8001/api/v1` (or via Cloudflare domain `/api/v1`)  

---

## 1. System Architecture & Multi-Tenant Paradigm

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                      Next.js Frontend (Client/SSR)                      │
│                                                                         │
│   ┌──────────────────────┐  ┌───────────────────┐  ┌────────────────┐   │
│   │   Supabase Auth Client│  │ Org Context (Slug)│  │ React Query    │   │
│   │   (JWT Token Provider)│  │ (Tenant Scoping)  │  │ (API Client)   │   │
│   └──────────┬───────────┘  └─────────┬─────────┘  └───────┬────────┘   │
└──────────────┼────────────────────────┼────────────────────┼────────────┘
               │ Bearer <JWT>           │ X-Org-ID / Path    │
               ▼                        ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Multi-Tenant Backend                        │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ JWT Auth Middleware ──> Validates Token & Injects User ID       │   │
│   │ Tenant Middleware   ──> Validates (User ID, Org ID) Membership  │   │
│   │ RBAC Evaluator      ──> Checks 'admin' | 'staff' | 'member'     │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Tenant Context Resolution
1. The authenticated user logs in via Supabase Auth.
2. The user queries `GET /api/v1/organizations` to fetch all institutions they have access to.
3. The frontend stores the currently selected `currentOrganization` (UUID `organization_id` & `slug`) in React Context / LocalStorage.
4. All scoped API requests use `/api/v1/organizations/{organization_id}/...`.

---

## 2. API Response & Error Standards

Every endpoint returns a consistent JSON envelope:

### 2.1 Single Resource (`SuccessResponse<T>`)
```typescript
interface SuccessResponse<T> {
  success: true;
  data: T;
  message?: string;
}
```

### 2.2 Paginated Resource (`PaginatedResponse<T>`)
```typescript
interface PaginatedResponse<T> {
  success: true;
  data: T[];
  meta: {
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  };
}
```

### 2.3 Error Response (`ErrorResponse`)
```typescript
interface ErrorResponse {
  success: false;
  error: {
    code: string;       // e.g. "TENANT_ACCESS_DENIED", "RESOURCE_NOT_FOUND"
    message: string;    // Human-readable error description
    details?: Record<string, any>;
  };
}
```

---

## 3. Complete Endpoints Reference

### 3.1 Authentication & Profile (`/api/v1/auth`, `/api/v1/me`)

#### `GET /api/v1/me`
* **Description:** Retrieves the authenticated user profile and list of organization memberships.
* **Headers:** `Authorization: Bearer <supabase_jwt>`
* **Response (HTTP 200):**
```json
{
  "success": true,
  "data": {
    "id": "u0000000-0000-0000-0000-000000000001",
    "email": "director@apexcollege.edu.in",
    "full_name": "Director Admissions",
    "phone_number": "+919876543210",
    "organizations": [
      {
        "id": "a0000000-0000-0000-0000-000000000001",
        "name": "Apex Engineering College",
        "slug": "apex-college",
        "role": "admin"
      }
    ]
  }
}
```

---

### 3.2 Organizations (`/api/v1/organizations`)

#### `GET /api/v1/organizations`
* **Description:** Returns all institutions the caller is a member of.
* **Response (HTTP 200):** Array of organizations with caller's role.

#### `POST /api/v1/organizations`
* **Description:** Creates a new institution/organization.
* **Body:**
```json
{
  "name": "Stanford Global Academy",
  "slug": "stanford-global",
  "institution_type": "college",
  "website_url": "https://stanfordglobal.edu",
  "timezone": "Asia/Kolkata",
  "primary_contact_name": "Dr. Ramesh Sharma",
  "primary_contact_phone": "+919876543210",
  "primary_contact_email": "admissions@stanfordglobal.edu",
  "address": {
    "city": "Bengaluru",
    "state": "Karnataka",
    "country": "India",
    "pincode": "560100"
  }
}
```

#### `GET /api/v1/organizations/{org_id}`
* **Description:** Detailed institution profile.

#### `PATCH /api/v1/organizations/{org_id}`
* **Description:** Updates institution profile, contact info, or timezone.

#### `GET /api/v1/organizations/{org_id}/members`
* **Description:** List team members and their roles (`admin`, `staff`, `viewer`).

---

### 3.3 AI Agents & Voice Studio (`/api/v1/organizations/{org_id}/agents`)

#### `GET /api/v1/organizations/{org_id}/agents`
* **Description:** Lists all AI admission counselors in the institution.
* **Response (HTTP 200):**
```json
{
  "success": true,
  "data": [
    {
      "id": "c0000000-0000-0000-0000-000000000001",
      "organization_id": "a0000000-0000-0000-0000-000000000001",
      "name": "Maya — Admission Counselor",
      "agent_type": "admission_ai",
      "description": "Primary voice agent handling 2026 admissions inquiries.",
      "is_active": true,
      "assigned_phone_number": "+914045901132",
      "created_at": "2026-09-07T12:00:00Z"
    }
  ]
}
```

#### `POST /api/v1/organizations/{org_id}/agents`
* **Description:** Creates a new AI agent with default prompt and voice settings.

#### `GET /api/v1/organizations/{org_id}/agents/{agent_id}`
* **Description:** Retrieves agent details including speech configuration, prompt, and handoff settings.
* **Response (HTTP 200):**
```json
{
  "success": true,
  "data": {
    "id": "c0000000-0000-0000-0000-000000000001",
    "name": "Maya — Admission Counselor",
    "agent_type": "admission_ai",
    "is_active": true,
    "speech_config": {
      "primary_language": "en-IN",
      "supported_languages": ["en-IN", "hi-IN", "te-IN"],
      "voice_id": "qwen3_indian_female_1",
      "voice_speed": 1.0,
      "allow_barge_in": true,
      "vad_silence_threshold_ms": 400,
      "welcome_message": "Hello! Thank you for calling Apex Engineering College Admissions. I am Maya, your AI admission counselor. How may I assist you with admissions today?",
      "max_call_duration_seconds": 600
    },
    "system_prompt": "You are Maya, an authoritative admissions counselor at Apex Engineering College...",
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
      "working_days": [1, 2, 3, 4, 5, 6]
    }
  }
}
```

#### `PATCH /api/v1/organizations/{org_id}/agents/{agent_id}/config`
* **Description:** Updates agent prompt, voice ID, speed, languages, and SIP human transfer number.

---

### 3.4 Telephony & DID Numbers (`/api/v1/organizations/{org_id}/phone-numbers`)

#### `GET /api/v1/organizations/{org_id}/phone-numbers`
* **Description:** Lists all provisioned virtual DID numbers and assigned agents.
* **Response (HTTP 200):**
```json
{
  "success": true,
  "data": [
    {
      "id": "b0000000-0000-0000-0000-000000000001",
      "phone_number": "+914045901132",
      "display_number": "040-459-01132",
      "provider": "exotel",
      "provider_sid": "eduvoiceai1",
      "status": "active",
      "assigned_agent": {
        "id": "c0000000-0000-0000-0000-000000000001",
        "name": "Maya — Admission Counselor"
      }
    }
  ]
}
```

#### `POST /api/v1/organizations/{org_id}/phone-numbers/{phone_id}/assign`
* **Description:** Assigns or reassigns an Exotel virtual number to a specific agent.
* **Body:**
```json
{
  "agent_id": "c0000000-0000-0000-0000-000000000001"
}
```

---

### 3.5 Calls & Live Telephony Intelligence (`/api/v1/organizations/{org_id}/calls`)

#### `GET /api/v1/organizations/{org_id}/calls`
* **Description:** Paginated call logs with filtering by agent, lead, status, outcome, and date range.
* **Query Params:**
  * `page` (default `1`)
  * `page_size` (default `20`)
  * `agent_id` (UUID, optional)
  * `lead_id` (UUID, optional)
  * `status` (`completed`, `in_progress`, `failed`, `transferred`, optional)
  * `outcome` (`admission_inquiry`, `campus_visit_scheduled`, `fee_query`, `general_inquiry`, optional)
  * `date_from` (ISO8601, optional)
  * `date_to` (ISO8601, optional)
* **Response (HTTP 200):**
```json
{
  "success": true,
  "data": [
    {
      "id": "e0000000-0000-0000-0000-000000000001",
      "caller_number": "+919876543210",
      "agent_name": "Maya — Admission Counselor",
      "duration_seconds": 184,
      "call_status": "completed",
      "call_outcome": "campus_visit_scheduled",
      "lead_name": "Rahul Verma",
      "sentiment": "positive",
      "started_at": "2026-09-08T10:14:00Z",
      "ended_at": "2026-09-08T10:17:04Z",
      "has_recording": true
    }
  ],
  "meta": {
    "total": 124,
    "page": 1,
    "page_size": 20,
    "total_pages": 7
  }
}
```

#### `GET /api/v1/organizations/{org_id}/calls/{call_id}`
* **Description:** Detailed call summary, lead data extracted, sentiment, and notes.

#### `GET /api/v1/organizations/{org_id}/calls/{call_id}/transcript`
* **Description:** Turn-by-turn conversational transcript with speaker labels (`agent` / `user`), timestamps, sentiment, and detected intent.
* **Response (HTTP 200):**
```json
{
  "success": true,
  "data": {
    "call_id": "e0000000-0000-0000-0000-000000000001",
    "turns": [
      {
        "turn_number": 1,
        "speaker": "agent",
        "text": "Hello! Thank you for calling Apex Engineering College Admissions. I am Maya, your AI admission counselor. How may I assist you with admissions today?",
        "timestamp_seconds": 0.5
      },
      {
        "turn_number": 2,
        "speaker": "user",
        "text": "Hi, I want to know about B.Tech Computer Science eligibility and fees.",
        "timestamp_seconds": 5.2,
        "intent": "fee_and_eligibility_inquiry"
      }
    ]
  }
}
```

#### `GET /api/v1/organizations/{org_id}/calls/{call_id}/recording`
* **Description:** Generates an authorized audio streaming URL / S3 presigned URL for playback in the UI.

---

### 3.6 Leads CRM (`/api/v1/organizations/{org_id}/leads`)

#### `GET /api/v1/organizations/{org_id}/leads`
* **Description:** Paginated leads captured by AI phone calls.
* **Query Params:** `page`, `page_size`, `status` (`new`, `contacted`, `qualified`, `admitted`, `lost`), `interest_level` (`high`, `medium`, `low`), `course_interested`.
* **Response (HTTP 200):**
```json
{
  "success": true,
  "data": [
    {
      "id": "f0000000-0000-0000-0000-000000000001",
      "full_name": "Rahul Verma",
      "phone_number": "+919876543210",
      "email": "rahul.v@gmail.com",
      "course_interested": "B.Tech Computer Science",
      "academic_year": "2026-2027",
      "status": "qualified",
      "interest_level": "high",
      "total_calls": 2,
      "last_call_at": "2026-09-08T10:17:04Z",
      "notes": "Candidate scored 92% in 12th PCM. Interested in hostel facility."
    }
  ],
  "meta": {
    "total": 48,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
  }
}
```

#### `PATCH /api/v1/organizations/{org_id}/leads/{lead_id}`
* **Description:** Updates lead status, stage, notes, or assigned staff counselor.

---

### 3.7 Knowledge Base & Document RAG (`/api/v1/organizations/{org_id}/knowledge`)

#### `GET /api/v1/organizations/{org_id}/knowledge`
* **Description:** Lists all uploaded documents (Fee Brochures, Syllabus, FAQs, Admission Guidelines).

#### `POST /api/v1/organizations/{org_id}/knowledge/upload`
* **Description:** Multi-part file upload (`.pdf`, `.docx`, `.txt`) for vector chunking and embedding.
* **Form-data:**
  * `file`: Binary file
  * `title`: "2026-2027 B.Tech Fee Structure"
  * `category`: `fees` | `eligibility` | `syllabus` | `faq`

#### `DELETE /api/v1/organizations/{org_id}/knowledge/{doc_id}`
* **Description:** Deletes document and cleans vector embeddings from database.

#### `POST /api/v1/organizations/{org_id}/knowledge/search`
* **Description:** Tests semantic similarity search against the RAG knowledge base.
* **Body:**
```json
{
  "query": "What is the scholarship discount for students with >90% marks?",
  "top_k": 3
}
```

---

### 3.8 Analytics & Usage Metrics (`/api/v1/organizations/{org_id}/usage`)

#### `GET /api/v1/organizations/{org_id}/usage/summary`
* **Description:** Dashboard KPI metrics.
* **Response (HTTP 200):**
```json
{
  "success": true,
  "data": {
    "total_calls": 842,
    "total_minutes": 2680,
    "total_leads_captured": 412,
    "lead_conversion_rate": 48.9,
    "average_call_duration_seconds": 191,
    "human_handoff_count": 28,
    "human_handoff_percentage": 3.3
  }
}
```

#### `GET /api/v1/organizations/{org_id}/usage/analytics`
* **Description:** Time-series data for call volume charts, hourly heatmaps, and sentiment breakdown.

---

## 4. Complete TypeScript Type Definitions (`src/types/api.ts`)

Karthik can copy-paste this file directly into the Next.js project:

```typescript
// =============================================================================
// Edu-Voice-Ai — Frontend Type Definitions
// =============================================================================

export type UserRole = 'admin' | 'staff' | 'member';
export type CallStatus = 'in_progress' | 'completed' | 'failed' | 'transferred' | 'busy';
export type CallOutcome = 'admission_inquiry' | 'campus_visit_scheduled' | 'fee_query' | 'general_inquiry' | 'dropped';
export type LeadStatus = 'new' | 'contacted' | 'qualified' | 'admitted' | 'lost';
export type InterestLevel = 'high' | 'medium' | 'low';
export type FollowupChannel = 'call' | 'whatsapp' | 'email' | 'sms';

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  phone_number?: string;
  organizations: Array<{
    id: string;
    name: string;
    slug: string;
    role: UserRole;
  }>;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  institution_type: 'college' | 'university' | 'school' | 'coaching';
  website_url?: string;
  timezone: string;
  primary_contact_name?: string;
  primary_contact_phone?: string;
  primary_contact_email?: string;
  address?: {
    city: string;
    state: string;
    country: string;
    pincode: string;
  };
  is_active: boolean;
  created_at: string;
}

export interface SpeechConfig {
  primary_language: string;
  supported_languages: string[];
  voice_id: string;
  voice_speed: number;
  allow_barge_in: boolean;
  vad_silence_threshold_ms: number;
  welcome_message: string;
  max_call_duration_seconds: number;
}

export interface HandoffConfig {
  human_handoff_enabled: boolean;
  human_handoff_number: string;
  human_handoff_condition: 'on_request_or_unknown' | 'always' | 'never';
}

export interface OperatingHours {
  enabled: boolean;
  timezone: string;
  start_time: string;
  end_time: string;
  working_days: number[];
}

export interface Agent {
  id: string;
  organization_id: string;
  name: string;
  agent_type: string;
  description?: string;
  is_active: boolean;
  speech_config: SpeechConfig;
  system_prompt?: string;
  handoff_config: HandoffConfig;
  operating_hours: OperatingHours;
  assigned_phone_number?: string;
  created_at: string;
}

export interface PhoneNumber {
  id: string;
  phone_number: string;
  display_number: string;
  provider: string;
  provider_sid?: string;
  status: 'active' | 'inactive' | 'pending';
  assigned_agent?: {
    id: string;
    name: string;
  };
}

export interface Call {
  id: string;
  organization_id: string;
  phone_number_id?: string;
  caller_number: string;
  agent_name: string;
  duration_seconds: number;
  call_status: CallStatus;
  call_outcome: CallOutcome;
  lead_id?: string;
  lead_name?: string;
  sentiment?: 'positive' | 'neutral' | 'negative';
  started_at: string;
  ended_at: string;
  has_recording: boolean;
}

export interface TranscriptTurn {
  turn_number: number;
  speaker: 'agent' | 'user';
  text: string;
  timestamp_seconds: number;
  intent?: string;
}

export interface CallDetail extends Call {
  summary?: string;
  extracted_data?: Record<string, any>;
  transferred_to_phone?: string;
  handoff_reason?: string;
  recording_url?: string;
}

export interface Lead {
  id: string;
  organization_id: string;
  full_name: string;
  phone_number: string;
  email?: string;
  course_interested?: string;
  academic_year?: string;
  status: LeadStatus;
  interest_level: InterestLevel;
  total_calls: number;
  last_call_at?: string;
  notes?: string;
  created_at: string;
}

export interface KnowledgeDocument {
  id: string;
  organization_id: string;
  title: string;
  category: string;
  file_type: string;
  file_size_bytes: number;
  chunks_count: number;
  status: 'processing' | 'ready' | 'failed';
  created_at: string;
}

export interface UsageSummary {
  total_calls: number;
  total_minutes: number;
  total_leads_captured: number;
  lead_conversion_rate: number;
  average_call_duration_seconds: number;
  human_handoff_count: number;
  human_handoff_percentage: number;
}
```

---

## 5. Frontend UI Page Architecture Blueprint

```text
src/
├── app/
│   ├── (auth)/
│   │   ├── login/page.tsx               <-- Supabase Email/Password + OAuth
│   │   └── register/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx                   <-- Sidebar, Header, Org Selector
│   │   ├── [orgSlug]/
│   │   │   ├── page.tsx                 <-- Executive KPI Dashboard
│   │   │   ├── calls/
│   │   │   │   ├── page.tsx             <-- Live Calls Table & Audio Player
│   │   │   │   └── [callId]/page.tsx    <-- Turn-by-Turn Transcript & Sentiment
│   │   │   ├── leads/
│   │   │   │   ├── page.tsx             <-- Leads CRM Kanban & Table
│   │   │   │   └── [leadId]/page.tsx    <-- Lead Profile & Call History
│   │   │   ├── agents/
│   │   │   │   ├── page.tsx             <-- AI Agent Studio (Maya)
│   │   │   │   └── [agentId]/config/page.tsx <-- Voice, Prompt & SIP Handoff
│   │   │   ├── knowledge/
│   │   │   │   └── page.tsx             <-- PDF/Doc Uploader & RAG Inspector
│   │   │   ├── telephony/
│   │   │   │   └── page.tsx             <-- Exotel Virtual DID Mapping (040-459-01132)
│   │   │   └── settings/
│   │   │       └── page.tsx             <-- Team Roles, Webhooks & Institution Profile
├── components/
│   ├── audio/AudioPlayerWaveform.tsx    <-- Call playback component
│   ├── calls/TranscriptViewer.tsx       <-- Animated chat bubble transcript
│   ├── agents/VoiceSelectorModal.tsx    <-- Voice sample player & selector
│   └── ui/                              <-- Buttons, Badges, Modals, Inputs
├── lib/
│   ├── api-client.ts                    <-- Axios instance with Supabase JWT interceptor
│   └── supabase-browser.ts              <-- createBrowserClient()
└── hooks/
    ├── useCurrentOrg.ts                 <-- Tenant state hook
    └── useCalls.ts                      <-- React Query call fetcher
```

---

## 6. Recommended Next Steps for Karthik

1. **Configure Environment (`frontend/.env.local`):**
   ```env
   NEXT_PUBLIC_SUPABASE_URL=https://ccydagfljcdnkkobyhwx.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_8lvXhuJamTZ2xmlwCulnTw_N8q2mdLq
   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
   ```
2. **Setup Axios Client with JWT Token:**
   Attach the Supabase JWT access token on every outgoing request automatically.
3. **Connect to Seeded Production Data:**
   - Institution: `Apex Engineering College` (`apex-college`)
   - AI Agent: `Maya — Admission Counselor`
   - Active Phone DID: `040-459-01132` (`+914045901132`)
