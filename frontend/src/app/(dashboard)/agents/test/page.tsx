"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Bot,
  Sparkles,
  PhoneCall,
  Volume2,
  Mic,
  Send,
  Languages,
  CheckCircle2,
  BookOpen,
  ArrowLeft,
  User,
  ShieldCheck,
  PhoneForwarded,
  RotateCcw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useDataStore } from "@/hooks/useDataStore";
import { SupportedLanguage } from "@/types";

interface TestMessage {
  id: string;
  sender: "ai" | "user" | "system";
  text: string;
  timestamp: string;
  retrievedChunk?: string;
  confidenceScore?: number;
  extractedLead?: {
    course?: string;
    interest?: string;
    callback?: string;
  };
}

export default function AgentTestConsolePage() {
  const { organization, agent, courses, documents } = useDataStore();
  const [activeLang, setActiveLang] = useState<SupportedLanguage>("en");
  const [inputQuery, setInputQuery] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [messages, setMessages] = useState<TestMessage[]>([
    {
      id: "msg_init",
      sender: "ai",
      text: agent.greetingMessage,
      timestamp: "00:02",
      retrievedChunk: "Default verified institutional welcome prompt",
      confidenceScore: 0.99,
    },
  ]);

  const quickPrompts = [
    { label: "B.Tech CSE Fee", query: "What is the annual tuition fee for B.Tech Computer Science?" },
    { label: "Telugu Mixed Query", query: "CSE లో మేనేజ్‌మెంట్ కోటా సీట్లు ఎన్ని ఉన్నాయి? ఫీజ్ ఎంత?" },
    { label: "Hindi Hostel Query", query: "क्या गर्ल्स के लिए हॉस्टल फैसिलिटी और मेस अवेलेबल है?" },
    { label: "Scholarship / Handoff", query: "I have 3200 EAMCET rank. Can I get a full fee waiver?" },
    { label: "Unknown Fact", query: "What is the name of the chemistry faculty member in block 4?" },
  ];

  const handleSend = (queryToSend?: string) => {
    const text = queryToSend || inputQuery;
    if (!text.trim()) return;

    const userMsg: TestMessage = {
      id: `usr_${Date.now()}`,
      sender: "user",
      text,
      timestamp: "Now",
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputQuery("");
    setIsProcessing(true);

    setTimeout(() => {
      let aiReply = "";
      let chunk = "";
      let confidence = 0.94;
      let leadInfo: TestMessage["extractedLead"] = undefined;

      const lower = text.toLowerCase();

      if (lower.includes("fee") || lower.includes("fees") || text.includes("ఫీజ్")) {
        aiReply = `At ${organization.name}, the annual tuition fee for B.Tech CSE is ₹1,40,000, AI&ML is ₹1,50,000, and ECE is ₹1,20,000. MBA annual tuition is ₹95,000. Merit scholarships are available for ranks below 5,000.`;
        chunk = "Fee_Structure_Scholarships_and_Payment_Schedules_2026.pdf (Chunk #4)";
        confidence = 0.98;
        leadInfo = { course: "B.Tech CSE", interest: "Enquiring Fee", callback: "No" };
      } else if (lower.includes("hostel") || text.includes("हॉस्टल")) {
        aiReply = `Yes, ${organization.name} provides separate high-security hostels for boys and girls with 24/7 security, Wi-Fi, and hygienic meals. The annual hostel fee is ₹75,000.`;
        chunk = "Hostel_Rules_Mess_Menu_and_Campus_Facilities.docx (Chunk #2)";
        confidence = 0.96;
        leadInfo = { course: "Campus Facilities", interest: "Hostel Enquiry", callback: "No" };
      } else if (lower.includes("scholarship") || lower.includes("waiver") || lower.includes("3200")) {
        aiReply = `Students with EAMCET ranks below 5,000 qualify for a 100% tuition fee waiver! However, fee concession approval requires direct evaluation by our senior admission team. Let me connect you with our Chief Counsellor at ${agent.humanHandoffNumber}.`;
        chunk = "EAMCET_and_JEE_Previous_Year_Cutoff_Ranks.pdf (Chunk #1)";
        confidence = 0.97;
        leadInfo = { course: "B.Tech ECE/CSE", interest: "Highly Interested (Rank 3200)", callback: "Transferred to Human" };
      } else if (lower.includes("faculty") || lower.includes("chemistry")) {
        aiReply = agent.fallbackMessage;
        chunk = "No grounded match in indexed knowledge base (Confidence < 0.85)";
        confidence = 0.42;
      } else {
        aiReply = `${organization.name} offers NBA-accredited B.Tech in CSE, AI&ML, ECE, and MBA programs. Admissions for the 2026 academic year are currently open. Would you like me to schedule a counsellor callback?`;
        chunk = "ABC_College_Official_Admission_Prospectus_2026-27.pdf (Chunk #1)";
        confidence = 0.92;
        leadInfo = { course: "General Admissions", interest: "Interested", callback: "Offered" };
      }

      const aiMsg: TestMessage = {
        id: `ai_${Date.now()}`,
        sender: "ai",
        text: aiReply,
        timestamp: "Now",
        retrievedChunk: chunk,
        confidenceScore: confidence,
        extractedLead: leadInfo,
      };

      setMessages((prev) => [...prev, aiMsg]);
      setIsProcessing(false);
    }, 800);
  };

  const handleReset = () => {
    setMessages([
      {
        id: "msg_init",
        sender: "ai",
        text: agent.greetingMessage,
        timestamp: "00:02",
        retrievedChunk: "Default verified institutional welcome prompt",
        confidenceScore: 0.99,
      },
    ]);
  };

  return (
    <div className="space-y-6">
      {/* Top Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <Link
            href="/agents"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:underline mb-1"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Agent Configuration
          </Link>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-indigo-600" />
            Interactive Admission AI Test Console (Demo Simulation Mode)
          </h1>
          <p className="text-xs text-muted-foreground">
            Simulate prospective student phone enquiries in English, Telugu, and Hindi to verify institutional knowledge grounding.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleReset} className="text-xs">
            <RotateCcw className="h-3.5 w-3.5 mr-1" /> Reset Simulation
          </Button>
        </div>
      </div>

      {/* Main Split Console Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Simulated Call / Chat Screen */}
        <div className="lg:col-span-2 space-y-4">
          {/* Quick prompt bar */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            <span className="text-[11px] font-bold text-slate-500 shrink-0">Sample Inquiries:</span>
            {quickPrompts.map((p) => (
              <button
                key={p.label}
                onClick={() => handleSend(p.query)}
                className="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-sm hover:border-indigo-300 hover:text-indigo-600 transition-all dark:bg-slate-800 dark:border-slate-700 dark:text-slate-300"
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Chat / Transcript Panel */}
          <Card className="shadow-lg border-indigo-100 bg-white h-[500px] flex flex-col">
            <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600 text-white">
                  <Bot className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-900">{agent.name}</p>
                  <p className="text-[10px] text-emerald-600 font-medium">● Grounded in 5 indexed documents</p>
                </div>
              </div>
              <Badge variant="indigo" className="text-[10px]">
                Audio Synthesis Active
              </Badge>
            </div>

            {/* Message Stream */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex items-start gap-3 ${
                    msg.sender === "user" ? "flex-row-reverse" : ""
                  }`}
                >
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                      msg.sender === "user"
                        ? "bg-slate-800 text-white"
                        : "bg-indigo-600 text-white shadow-sm shadow-indigo-500/20"
                    }`}
                  >
                    {msg.sender === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                  </div>

                  <div
                    className={`rounded-2xl p-3.5 text-xs leading-relaxed max-w-lg ${
                      msg.sender === "user"
                        ? "bg-slate-900 text-white rounded-tr-none"
                        : "bg-indigo-50/70 border border-indigo-100 text-indigo-950 rounded-tl-none"
                    }`}
                  >
                    <p>{msg.text}</p>
                    {msg.retrievedChunk && (
                      <div className="mt-2 border-t border-indigo-200/60 pt-1.5 text-[10px] flex items-center justify-between text-indigo-700">
                        <span className="truncate max-w-[280px]">RAG: {msg.retrievedChunk}</span>
                        <span className="font-mono font-bold">
                          {Math.round((msg.confidenceScore || 0.9) * 100)}% Match
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {isProcessing && (
                <div className="flex items-center gap-2 text-xs text-indigo-600 animate-pulse pl-11">
                  <Bot className="h-4 w-4" />
                  <span>Retrieving verified campus knowledge & synthesizing voice...</span>
                </div>
              )}
            </div>

            {/* Input Bar */}
            <div className="border-t border-slate-100 p-3 bg-slate-50/60 flex items-center gap-2">
              <Input
                value={inputQuery}
                onChange={(e) => setInputQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="Ask an admission question in English, हिन्दी, or తెలుగు..."
                className="bg-white text-xs"
              />
              <Button
                variant="gradient"
                size="sm"
                onClick={() => handleSend()}
                disabled={isProcessing || !inputQuery.trim()}
                className="font-bold shrink-0"
              >
                <Send className="h-4 w-4 mr-1" /> Ask AI
              </Button>
            </div>
          </Card>
        </div>

        {/* Right 1 Column: Real-time RAG & Lead Inspector */}
        <div className="space-y-4">
          <Card className="shadow-sm border-slate-200">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-emerald-600" />
                Simulated RAG Grounding & Lead Inspector
              </CardTitle>
              <CardDescription className="text-xs">
                Inspect simulated chunk matches and zero-hallucination bounds
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div className="rounded-xl bg-slate-50 p-3 border border-slate-200 space-y-1">
                <span className="text-slate-500 block text-[10px] font-bold uppercase">
                  Connected Knowledge Index
                </span>
                <span className="font-bold text-slate-900 block">{organization.name} Knowledge Base</span>
                <span className="text-[10px] text-emerald-600 font-medium">5 Documents • 96 Vector Chunks</span>
              </div>

              <div className="rounded-xl bg-slate-50 p-3 border border-slate-200 space-y-2">
                <span className="text-slate-500 block text-[10px] font-bold uppercase">
                  Active Safety Rules
                </span>
                <ul className="space-y-1 text-[11px] text-slate-700">
                  <li className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                    Strict zero-hallucination verification
                  </li>
                  <li className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                    Human handoff fallback active (+91 98480 22338)
                  </li>
                  <li className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                    Automatic lead qualification enabled
                  </li>
                </ul>
              </div>

              <div className="rounded-xl bg-indigo-50/70 p-3 border border-indigo-100 space-y-1.5">
                <span className="text-indigo-900 font-bold block">Test Call Trigger</span>
                <p className="text-[11px] text-indigo-700 leading-relaxed">
                  Callers dialling <span className="font-mono font-bold">+91 80 4719 8800</span> will experience this exact conversational model.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
