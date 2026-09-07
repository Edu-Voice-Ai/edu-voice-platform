export type UserRole = "admin" | "counsellor" | "staff";

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatarUrl?: string;
  organizationId: string;
}

export interface Organization {
  id: string;
  name: string;
  type: "college" | "university" | "coaching" | "training" | "school";
  tagline: string;
  website: string;
  city: string;
  state: string;
  phone: string;
  email: string;
  logoUrl?: string;
  onboardingCompleted: boolean;
}

export type SupportedLanguage = "en" | "hi" | "te";

export interface AdmissionAgent {
  id: string;
  organizationId: string;
  name: string;
  status: "active" | "inactive" | "training";
  defaultLanguage: SupportedLanguage;
  supportedLanguages: SupportedLanguage[];
  voiceId: string;
  voiceGender: "female" | "male";
  voiceSpeed: number;
  greetingMessage: string;
  fallbackMessage: string;
  confidenceThreshold: number; // 0.0 - 1.0
  humanHandoffNumber: string;
  handoffTriggers: {
    callerRequested: boolean;
    lowConfidence: boolean;
    feeNegotiation: boolean;
    urgentDeadline: boolean;
  };
  businessHours: {
    enabled: boolean;
    startTime: string;
    endTime: string;
    timezone: string;
    days: string[];
    afterHoursAction: "take_voicemail" | "ai_only" | "reject";
  };
  lastUpdated: string;
}

export type KnowledgeCategory =
  | "courses"
  | "fees"
  | "eligibility"
  | "admission_dates"
  | "documents"
  | "hostel"
  | "campus"
  | "timings"
  | "faqs"
  | "contact";

export interface KnowledgeDocument {
  id: string;
  organizationId: string;
  title: string;
  category: KnowledgeCategory;
  fileType: "pdf" | "docx" | "txt" | "csv";
  fileSizeBytes: number;
  status: "indexed" | "processing" | "error";
  chunkCount: number;
  uploadedAt: string;
  lastIndexedAt?: string;
  errorMessage?: string;
}

export interface FAQItem {
  id: string;
  organizationId: string;
  category: KnowledgeCategory;
  question: string;
  answer: string;
  verified: boolean;
  updatedAt: string;
}

export interface CourseItem {
  id: string;
  organizationId: string;
  name: string;
  code: string;
  degree: "B.Tech" | "M.Tech" | "MBA" | "BBA" | "B.Sc" | "Diploma";
  durationYears: number;
  annualFeeINR: number;
  eligibility: string;
  totalSeats: number;
  availableSeats: number;
  applicationDeadline: string;
}

export type CallStatus = "completed" | "transferred" | "missed" | "in_progress";

export interface TranscriptMessage {
  speaker: "caller" | "ai" | "human";
  speakerName?: string;
  text: string;
  timestamp: string; // e.g. "00:15"
  language?: SupportedLanguage;
  confidence?: number;
}

export interface CallRecord {
  id: string;
  organizationId: string;
  callerNumber: string;
  callerName?: string;
  startedAt: string;
  durationSeconds: number;
  status: CallStatus;
  primaryLanguage: SupportedLanguage | "mixed";
  agentId: string;
  agentName: string;
  transcript: TranscriptMessage[];
  aiSummary: string;
  leadId?: string;
  leadStatus?: LeadStatus;
  transferredTo?: string;
  transferReason?: string;
  keyTopicsDiscussed: string[];
  audioRecordingUrl?: string;
}

export type LeadStatus =
  | "New"
  | "Interested"
  | "Highly Interested"
  | "Follow-up Required"
  | "Not Interested"
  | "Callback Requested"
  | "Converted"
  | "Lost";

export interface LeadRecord {
  id: string;
  organizationId: string;
  studentName: string;
  phone: string;
  email?: string;
  courseInterested: string;
  currentQualification: string;
  status: LeadStatus;
  callbackRequested: boolean;
  preferredCallbackTime?: string;
  assignedCounsellor?: string;
  notes: Array<{
    id: string;
    author: string;
    content: string;
    createdAt: string;
  }>;
  callIds: string[];
  createdAt: string;
  lastContactedAt: string;
}

export interface FollowUpItem {
  id: string;
  organizationId: string;
  leadId: string;
  studentName: string;
  phone: string;
  courseInterested: string;
  scheduledFor: string;
  status: "pending" | "completed" | "overdue" | "cancelled";
  priority: "high" | "medium" | "low";
  assignedTo: string;
  notes: string;
  createdAt: string;
}

export type PhoneNumberStatus =
  | "available"
  | "reserved"
  | "assigned"
  | "active"
  | "suspended";

export interface PhoneNumberRecord {
  id: string;
  organizationId: string;
  number: string;
  formattedNumber: string;
  provider: "Exotel (Planned)" | "Virtual Cloud";
  status: PhoneNumberStatus;
  assignedAgentName: string;
  fallbackNumber: string;
  monthlyRentalINR: number;
  totalCallsHandled: number;
  activatedAt: string;
}

export interface SubscriptionPlan {
  id: "basic" | "pro" | "enterprise";
  name: string;
  tagline: string;
  priceMonthlyINR: number;
  voiceMinutesIncluded: number;
  voiceMinutesUsed: number;
  phoneNumbersIncluded: number;
  phoneNumbersUsed: number;
  whatsappEnabled: boolean;
  knowledgeDocsLimit: number;
  knowledgeDocsUsed: number;
  maxStaffUsers: number;
  features: string[];
}

export interface AnalyticsSummary {
  totalCalls: number;
  answeredCalls: number;
  aiHandledPercentage: number;
  humanTransfers: number;
  totalLeadsCaptured: number;
  highlyInterestedLeads: number;
  conversions: number;
  avgCallDurationSeconds: number;
  callTrends: Array<{ date: string; calls: number; leads: number; transfers: number }>;
  languageBreakdown: Array<{ language: string; percentage: number; count: number }>;
  topCourses: Array<{ name: string; enquiries: number; leads: number }>;
  hourlyVolume: Array<{ hour: string; calls: number }>;
}
