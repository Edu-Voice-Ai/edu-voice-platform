"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import {
  Organization,
  AdmissionAgent,
  KnowledgeDocument,
  FAQItem,
  CourseItem,
  CallRecord,
  LeadRecord,
  FollowUpItem,
  PhoneNumberRecord,
  SubscriptionPlan,
  AnalyticsSummary,
  LeadStatus,
} from "@/types";
import {
  mockOrganization,
  mockAgent,
  mockCourses,
  mockDocuments,
  mockFAQs,
  mockCalls,
  mockLeads,
  mockFollowUps,
  mockPhoneNumbers,
  mockPlans,
  mockAnalytics,
} from "@/services/mockData";

interface DataStoreContextType {
  organization: Organization;
  agent: AdmissionAgent;
  courses: CourseItem[];
  documents: KnowledgeDocument[];
  faqs: FAQItem[];
  calls: CallRecord[];
  leads: LeadRecord[];
  followUps: FollowUpItem[];
  phoneNumbers: PhoneNumberRecord[];
  plans: SubscriptionPlan[];
  analytics: AnalyticsSummary;

  // Actions
  updateOrganization: (org: Partial<Organization>) => void;
  updateAgent: (agent: Partial<AdmissionAgent>) => void;
  addCourse: (course: Omit<CourseItem, "id" | "organizationId">) => void;
  updateCourse: (id: string, course: Partial<CourseItem>) => void;
  deleteCourse: (id: string) => void;
  addDocument: (file: { name: string; size: number; category: KnowledgeDocument["category"] }) => void;
  deleteDocument: (id: string) => void;
  addFAQ: (faq: Omit<FAQItem, "id" | "organizationId" | "updatedAt">) => void;
  updateFAQ: (id: string, faq: Partial<FAQItem>) => void;
  deleteFAQ: (id: string) => void;
  updateLeadStatus: (id: string, status: LeadStatus) => void;
  addLeadNote: (leadId: string, author: string, content: string) => void;
  createLead: (lead: Omit<LeadRecord, "id" | "organizationId" | "callIds" | "createdAt" | "lastContactedAt">) => void;
  updateFollowUpStatus: (id: string, status: FollowUpItem["status"]) => void;
  addFollowUp: (followUp: Omit<FollowUpItem, "id" | "organizationId" | "createdAt">) => void;
  triggerSimulatedCall: (callerNumber: string, query: string, language: "en" | "hi" | "te") => Promise<CallRecord>;
}

const DataStoreContext = createContext<DataStoreContextType | undefined>(undefined);

export function DataStoreProvider({ children }: { children: React.ReactNode }) {
  const [organization, setOrganization] = useState<Organization>(mockOrganization);
  const [agent, setAgent] = useState<AdmissionAgent>(mockAgent);
  const [courses, setCourses] = useState<CourseItem[]>(mockCourses);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>(mockDocuments);
  const [faqs, setFaqs] = useState<FAQItem[]>(mockFAQs);
  const [calls, setCalls] = useState<CallRecord[]>(mockCalls);
  const [leads, setLeads] = useState<LeadRecord[]>(mockLeads);
  const [followUps, setFollowUps] = useState<FollowUpItem[]>(mockFollowUps);
  const [phoneNumbers, setPhoneNumbers] = useState<PhoneNumberRecord[]>(mockPhoneNumbers);
  const [plans, setPlans] = useState<SubscriptionPlan[]>(mockPlans);
  const [analytics, setAnalytics] = useState<AnalyticsSummary>(mockAnalytics);

  const updateOrganization = (org: Partial<Organization>) => {
    setOrganization((prev) => ({ ...prev, ...org }));
  };

  const updateAgent = (updated: Partial<AdmissionAgent>) => {
    setAgent((prev) => ({ ...prev, ...updated, lastUpdated: new Date().toISOString() }));
  };

  const addCourse = (courseData: Omit<CourseItem, "id" | "organizationId">) => {
    const newCourse: CourseItem = {
      ...courseData,
      id: `crs_${Date.now()}`,
      organizationId: organization.id,
    };
    setCourses((prev) => [newCourse, ...prev]);
  };

  const updateCourse = (id: string, updated: Partial<CourseItem>) => {
    setCourses((prev) => prev.map((c) => (c.id === id ? { ...c, ...updated } : c)));
  };

  const deleteCourse = (id: string) => {
    setCourses((prev) => prev.filter((c) => c.id !== id));
  };

  const addDocument = (file: { name: string; size: number; category: KnowledgeDocument["category"] }) => {
    const ext = file.name.split(".").pop()?.toLowerCase() as "pdf" | "docx" | "txt" | "csv";
    const newDoc: KnowledgeDocument = {
      id: `doc_${Date.now()}`,
      organizationId: organization.id,
      title: file.name,
      category: file.category,
      fileType: ["pdf", "docx", "txt", "csv"].includes(ext) ? ext : "pdf",
      fileSizeBytes: file.size,
      status: "processing",
      chunkCount: Math.floor(file.size / 100000) + 4,
      uploadedAt: new Date().toISOString(),
    };

    setDocuments((prev) => [newDoc, ...prev]);

    // Simulate RAG vector indexing completion
    setTimeout(() => {
      setDocuments((prev) =>
        prev.map((d) =>
          d.id === newDoc.id
            ? { ...d, status: "indexed", lastIndexedAt: new Date().toISOString() }
            : d
        )
      );
    }, 2500);
  };

  const deleteDocument = (id: string) => {
    setDocuments((prev) => prev.filter((d) => d.id !== id));
  };

  const addFAQ = (faqData: Omit<FAQItem, "id" | "organizationId" | "updatedAt">) => {
    const newFAQ: FAQItem = {
      ...faqData,
      id: `faq_${Date.now()}`,
      organizationId: organization.id,
      updatedAt: new Date().toISOString(),
    };
    setFaqs((prev) => [newFAQ, ...prev]);
  };

  const updateFAQ = (id: string, updated: Partial<FAQItem>) => {
    setFaqs((prev) =>
      prev.map((f) => (f.id === id ? { ...f, ...updated, updatedAt: new Date().toISOString() } : f))
    );
  };

  const deleteFAQ = (id: string) => {
    setFaqs((prev) => prev.filter((f) => f.id !== id));
  };

  const updateLeadStatus = (id: string, status: LeadStatus) => {
    setLeads((prev) =>
      prev.map((l) =>
        l.id === id
          ? {
              ...l,
              status,
              lastContactedAt: new Date().toISOString(),
            }
          : l
      )
    );
  };

  const addLeadNote = (leadId: string, author: string, content: string) => {
    setLeads((prev) =>
      prev.map((l) =>
        l.id === leadId
          ? {
              ...l,
              notes: [
                ...l.notes,
                {
                  id: `note_${Date.now()}`,
                  author,
                  content,
                  createdAt: new Date().toISOString(),
                },
              ],
            }
          : l
      )
    );
  };

  const createLead = (leadData: Omit<LeadRecord, "id" | "organizationId" | "callIds" | "createdAt" | "lastContactedAt">) => {
    const newLead: LeadRecord = {
      ...leadData,
      id: `lead_${Date.now()}`,
      organizationId: organization.id,
      callIds: [],
      createdAt: new Date().toISOString(),
      lastContactedAt: new Date().toISOString(),
    };
    setLeads((prev) => [newLead, ...prev]);
  };

  const updateFollowUpStatus = (id: string, status: FollowUpItem["status"]) => {
    setFollowUps((prev) =>
      prev.map((f) => (f.id === id ? { ...f, status } : f))
    );
  };

  const addFollowUp = (data: Omit<FollowUpItem, "id" | "organizationId" | "createdAt">) => {
    const item: FollowUpItem = {
      ...data,
      id: `flw_${Date.now()}`,
      organizationId: organization.id,
      createdAt: new Date().toISOString(),
    };
    setFollowUps((prev) => [item, ...prev]);
  };

  const triggerSimulatedCall = async (
    callerNumber: string,
    query: string,
    language: "en" | "hi" | "te"
  ): Promise<CallRecord> => {
    // Generate intelligent AI response based on knowledge
    let aiResponse = "";
    let keyTopic = "";

    if (query.toLowerCase().includes("fee") || query.toLowerCase().includes("fees")) {
      aiResponse =
        "The annual tuition fee for B.Tech CSE is ₹1,40,000, AI&ML is ₹1,50,000, and ECE is ₹1,20,000. MBA annual fee is ₹95,000. Merit scholarships are available for high rankers.";
      keyTopic = "Fee Structure & Tuition";
    } else if (query.toLowerCase().includes("hostel")) {
      aiResponse =
        "Yes, we offer secure on-campus hostels for both boys and girls with 24/7 security, Wi-Fi, and hygienic meals. The annual hostel fee is ₹75,000.";
      keyTopic = "Hostel Facilities";
    } else if (query.toLowerCase().includes("eligibility") || query.toLowerCase().includes("admission")) {
      aiResponse =
        "For B.Tech programs, eligibility is 10+2 with MPC minimum 60% or valid TSEAMCET rank. Applications close on September 15, 2026.";
      keyTopic = "Eligibility & Deadlines";
    } else {
      aiResponse =
        "ABC Institute of Technology offers NBA-accredited B.Tech in CSE, AI&ML, ECE, and MBA programs. Would you like me to arrange a counsellor callback for further details?";
      keyTopic = "General Admissions";
    }

    const newCall: CallRecord = {
      id: `call_${Date.now()}`,
      organizationId: organization.id,
      callerNumber,
      callerName: "Interactive Caller",
      startedAt: new Date().toISOString(),
      durationSeconds: 95,
      status: "completed",
      primaryLanguage: language,
      agentId: agent.id,
      agentName: agent.name,
      transcript: [
        {
          speaker: "ai",
          text: agent.greetingMessage,
          timestamp: "00:02",
          language: agent.defaultLanguage,
        },
        {
          speaker: "caller",
          text: query,
          timestamp: "00:15",
          language,
        },
        {
          speaker: "ai",
          text: aiResponse,
          timestamp: "00:32",
          language,
        },
      ],
      aiSummary: `Interactive test enquiry: "${query}". AI provided grounded response regarding ${keyTopic}.`,
      keyTopicsDiscussed: [keyTopic, "Interactive Test Simulation"],
    };

    setCalls((prev) => [newCall, ...prev]);
    return newCall;
  };

  return (
    <DataStoreContext.Provider
      value={{
        organization,
        agent,
        courses,
        documents,
        faqs,
        calls,
        leads,
        followUps,
        phoneNumbers,
        plans,
        analytics,
        updateOrganization,
        updateAgent,
        addCourse,
        updateCourse,
        deleteCourse,
        addDocument,
        deleteDocument,
        addFAQ,
        updateFAQ,
        deleteFAQ,
        updateLeadStatus,
        addLeadNote,
        createLead,
        updateFollowUpStatus,
        addFollowUp,
        triggerSimulatedCall,
      }}
    >
      {children}
    </DataStoreContext.Provider>
  );
}

export function useDataStore() {
  const context = useContext(DataStoreContext);
  if (!context) {
    throw new Error("useDataStore must be used within a DataStoreProvider");
  }
  return context;
}
