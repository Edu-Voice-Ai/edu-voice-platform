"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  GraduationCap,
  Bot,
  PhoneCall,
  Languages,
  ShieldCheck,
  Zap,
  ArrowRight,
  CheckCircle2,
  Users,
  Sparkles,
  Volume2,
  Headphones,
  FileCheck,
  Clock,
  ChevronRight,
  Award,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export default function LandingPage() {
  const [activeLang, setActiveLang] = useState<"en" | "hi" | "te">("en");
  const [monthlyEnquiries, setMonthlyEnquiries] = useState(600);

  const sampleDialogues = {
    en: {
      student: "Hi, what is the annual tuition fee for B.Tech Computer Science and when do admissions close?",
      ai: "Namaste! The annual tuition fee for B.Tech CSE is ₹1,40,000. Applications for the 2026 academic year close on September 15. We have 48 seats available under Category-B. Would you like me to schedule a counsellor callback?",
      badge: "English (Natural Code-Mixed)",
    },
    hi: {
      student: "नमस्ते, क्या कॉलेज में गर्ल्स हॉस्टल फैसिलिटी है और MBA की फीस कितनी है?",
      ai: "नमस्ते! ABC इंस्टीट्यूट में 24/7 सुरक्षा और वाई-फाई के साथ अलग गर्ल्स हॉस्टल उपलब्ध है (वार्षिक शुल्क ₹75,000)। 2-वर्षीय MBA का वार्षिक शिक्षण शुल्क ₹95,000 है। क्या आप आवेदन लिंक प्राप्त करना चाहते हैं?",
      badge: "हिन्दी (Hindi Native Voice)",
    },
    te: {
      student: "నమస్కారం అండి, B.Tech ECE లో మేనేజ్‌మెంట్ కోటా సీట్లు ఉన్నాయా? స్కాలర్‌షిప్ ఎలా వస్తుంది?",
      ai: "నమస్కారం! B.Tech ECE లో మేనేజ్‌మెంట్ కోటా సీట్లు అందుబాటులో ఉన్నాయి. TSEAMCET ర్యాంక్ 5,000 లోపు ఉన్న విద్యార్థులకు 100% ట్యూషన్ ఫీజు మినహాయింపు లభిస్తుంది. పూర్తి వివరాల కోసం మా సీనియర్ కౌన్సిలర్ మీకు కాల్ చేయమంటారా?",
      badge: "తెలుగు (Telugu Dialect Grounded)",
    },
  };

  const calculatedHoursSaved = Math.round((monthlyEnquiries * 6.5) / 60);
  const calculatedCostSavings = Math.round(monthlyEnquiries * 75);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 selection:bg-indigo-500 selection:text-white">
      {/* SaaS Navigation */}
      <nav className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/25">
              <GraduationCap className="h-6 w-6" />
            </div>
            <span className="text-xl font-extrabold tracking-tight text-slate-900">
              Edu-Voice-AI
            </span>
          </div>

          <div className="hidden md:flex items-center gap-8 text-sm font-semibold text-slate-600">
            <a href="#how-it-works" className="hover:text-indigo-600 transition-colors">
              How It Works
            </a>
            <a href="#capabilities" className="hover:text-indigo-600 transition-colors">
              Admission AI
            </a>
            <a href="#multilingual" className="hover:text-indigo-600 transition-colors">
              Multilingual Demo
            </a>
            <a href="#pricing" className="hover:text-indigo-600 transition-colors">
              Pricing Plans
            </a>
          </div>

          <div className="flex items-center gap-3">
            <Link href="/login">
              <Button variant="ghost" size="sm" className="font-semibold text-slate-700">
                Sign In
              </Button>
            </Link>
            <Link href="/onboarding">
              <Button size="sm" variant="gradient" className="font-bold">
                Launch Counsellor
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative overflow-hidden pt-12 pb-20 lg:pt-20 lg:pb-28">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(45rem_50rem_at_top,theme(colors.indigo.100),theme(colors.slate.50))]" />
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto">
            <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50/80 px-4 py-1.5 text-xs font-bold text-indigo-700 shadow-sm mb-6">
              <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
              <span>Next-Gen Voice AI for Educational Institutions</span>
              <Badge variant="indigo" className="text-[10px] py-0 px-1.5 ml-1">
                V1 Launch
              </Badge>
            </div>

            <h1 className="text-4xl font-extrabold tracking-tight text-slate-900 sm:text-6xl sm:leading-tight">
              Launch Your Institution&apos;s{" "}
              <span className="bg-gradient-to-r from-indigo-600 via-violet-600 to-purple-600 bg-clip-text text-transparent">
                AI Admission Counsellor
              </span>{" "}
              in Minutes.
            </h1>

            <p className="mt-6 text-lg text-slate-600 leading-relaxed sm:text-xl">
              Equip your college, university, or institute with a 24/7 multilingual voice
              agent that answers phone enquiries using verified campus knowledge, qualifies
              prospective student leads, and escalates to human counsellors instantly.
            </p>

            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/onboarding" className="w-full sm:w-auto">
                <Button size="lg" variant="gradient" className="w-full sm:w-auto text-base shadow-xl">
                  Start Free 14-Day Setup
                  <ArrowRight className="ml-2 h-5 w-5" />
                </Button>
              </Link>
              <Link href="/dashboard" className="w-full sm:w-auto">
                <Button size="lg" variant="outline" className="w-full sm:w-auto text-base bg-white">
                  Explore Live Demo Dashboard
                </Button>
              </Link>
            </div>

            {/* Quick Proof Badges */}
            <div className="mt-10 flex flex-wrap items-center justify-center gap-6 text-xs font-semibold text-slate-500">
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Zero Hallucination Grounded AI</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>English, Hindi & Telugu Support</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Indian Virtual Number Included</span>
              </div>
            </div>
          </div>

          {/* Interactive Voice Simulator Widget */}
          <div id="multilingual" className="mt-16 max-w-4xl mx-auto">
            <Card className="border-indigo-100 shadow-2xl shadow-indigo-500/10 bg-white/95 backdrop-blur overflow-hidden rounded-3xl">
              <div className="border-b border-slate-100 bg-slate-50/80 px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
                    <Volume2 className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">
                      Live Admission AI Conversation Preview
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Simulated phone conversation using verified prospectus RAG
                    </p>
                  </div>
                </div>

                {/* Language Switcher */}
                <div className="flex rounded-xl bg-slate-200/80 p-1">
                  <button
                    onClick={() => setActiveLang("en")}
                    className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                      activeLang === "en"
                        ? "bg-white text-indigo-700 shadow-sm"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    English
                  </button>
                  <button
                    onClick={() => setActiveLang("hi")}
                    className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                      activeLang === "hi"
                        ? "bg-white text-indigo-700 shadow-sm"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    हिन्दी
                  </button>
                  <button
                    onClick={() => setActiveLang("te")}
                    className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                      activeLang === "te"
                        ? "bg-white text-indigo-700 shadow-sm"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    తెలుగు
                  </button>
                </div>
              </div>

              <CardContent className="p-6 sm:p-8 space-y-6">
                {/* Caller Message */}
                <div className="flex items-start gap-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 font-bold text-xs text-slate-700">
                    Caller
                  </div>
                  <div className="rounded-2xl rounded-tl-none bg-slate-100 p-4 text-sm text-slate-800 leading-relaxed max-w-xl">
                    <p>{sampleDialogues[activeLang].student}</p>
                  </div>
                </div>

                {/* AI Counsellor Response */}
                <div className="flex items-start gap-4 flex-row-reverse">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-white font-bold text-xs shadow-md shadow-indigo-500/30">
                    <Bot className="h-5 w-5" />
                  </div>
                  <div className="rounded-2xl rounded-tr-none bg-indigo-50 border border-indigo-100 p-4 text-sm text-indigo-950 leading-relaxed max-w-xl">
                    <div className="flex items-center justify-between mb-2">
                      <Badge variant="indigo" className="text-[10px]">
                        {sampleDialogues[activeLang].badge}
                      </Badge>
                      <span className="text-[10px] font-mono text-indigo-600">Grounded in 2026 Prospectus</span>
                    </div>
                    <p>{sampleDialogues[activeLang].ai}</p>
                  </div>
                </div>

                {/* Structured Lead Auto-Extraction Result */}
                <div className="rounded-xl border border-dashed border-emerald-200 bg-emerald-50/60 p-4">
                  <p className="text-xs font-bold text-emerald-900 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-emerald-600" />
                    Automatic Lead Captured in CRM
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                    <div>
                      <span className="text-slate-500 block">Course Interested</span>
                      <span className="font-semibold text-slate-900">B.Tech CSE</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Lead Qualification</span>
                      <span className="font-semibold text-emerald-700">Highly Interested</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Callback Status</span>
                      <span className="font-semibold text-slate-900">Requested Tomorrow</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Assigned Staff</span>
                      <span className="font-semibold text-slate-900">Dr. K. S. Rao</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section id="how-it-works" className="py-20 bg-white border-y border-slate-200/80">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-xs font-bold uppercase tracking-wider text-indigo-600">
              Simple 4-Step Setup
            </h2>
            <p className="mt-2 text-3xl font-extrabold text-slate-900 sm:text-4xl">
              From PDF Prospectus to 24/7 AI Receptionist in Minutes
            </p>
            <p className="mt-4 text-sm text-slate-600">
              No machine learning knowledge or coding required. Built specifically for
              educational administrative teams.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            {[
              {
                step: "01",
                icon: FileCheck,
                title: "Upload Campus Information",
                desc: "Upload brochures, fee structures, eligibility guidelines, and hostel FAQs.",
              },
              {
                step: "02",
                icon: Bot,
                title: "Configure Admission AI",
                desc: "Set greeting, voice preferences, and activate English, Hindi, and Telugu.",
              },
              {
                step: "03",
                icon: PhoneCall,
                title: "Get Indian Virtual Number",
                desc: "Receive a dedicated Indian phone number or connect your existing landline.",
              },
              {
                step: "04",
                icon: Users,
                title: "Capture Qualified Leads",
                desc: "Every enquiry is transcribed, qualified, and organized into your CRM dashboard.",
              },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.step}
                  className="relative flex flex-col items-start p-6 rounded-2xl bg-slate-50 border border-slate-100 hover:border-indigo-200 transition-all hover:shadow-lg"
                >
                  <span className="text-3xl font-black text-indigo-100 dark:text-slate-800">
                    {item.step}
                  </span>
                  <div className="mt-2 flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="mt-4 text-base font-bold text-slate-900">{item.title}</h3>
                  <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
                    {item.desc}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Core V1 Capabilities */}
      <section id="capabilities" className="py-20 bg-slate-50">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-xs font-bold uppercase tracking-wider text-indigo-600">
              V1 Core Features
            </h2>
            <p className="mt-2 text-3xl font-extrabold text-slate-900 sm:text-4xl">
              Engineered Specifically for College & University Admissions
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <Card className="border-slate-200/80 hover:shadow-xl transition-all">
              <CardContent className="p-6 space-y-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-600">
                  <ShieldCheck className="h-6 w-6" />
                </div>
                <h3 className="text-lg font-bold text-slate-900">Zero Hallucinations</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  The Admission AI strictly answers from verified institution documents. If a
                  fee or date is unknown, it transparently offers a counsellor transfer.
                </p>
              </CardContent>
            </Card>

            <Card className="border-slate-200/80 hover:shadow-xl transition-all">
              <CardContent className="p-6 space-y-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-600">
                  <Headphones className="h-6 w-6" />
                </div>
                <h3 className="text-lg font-bold text-slate-900">Live Human Handoff</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  When a caller requests a counsellor or requires complex scholarship evaluation,
                  the AI transfers the call instantly to your staff&apos;s phone.
                </p>
              </CardContent>
            </Card>

            <Card className="border-slate-200/80 hover:shadow-xl transition-all">
              <CardContent className="p-6 space-y-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-100 text-violet-600">
                  <Languages className="h-6 w-6" />
                </div>
                <h3 className="text-lg font-bold text-slate-900">Multilingual Fluency</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Seamlessly handles English, Hindi, Telugu, and natural mixed conversations
                  (e.g., English-Telugu) without forcing callers through clumsy IVR menus.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* ROI & Calculator Section */}
      <section className="py-20 bg-white border-t border-slate-200/80">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
          <div className="rounded-3xl bg-gradient-to-tr from-slate-900 to-indigo-950 p-8 sm:p-12 text-white shadow-2xl">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 items-center">
              <div>
                <Badge variant="indigo" className="mb-4">
                  Admission ROI Calculator
                </Badge>
                <h3 className="text-2xl sm:text-3xl font-extrabold leading-tight">
                  Calculate Your Admission Team&apos;s Time & Cost Savings
                </h3>
                <p className="mt-3 text-sm text-slate-300">
                  Slide to match your institution&apos;s monthly admission phone call volume.
                </p>

                <div className="mt-6 space-y-3">
                  <div className="flex justify-between text-xs font-semibold">
                    <span>Monthly Inbound Enquiries:</span>
                    <span className="text-indigo-400 font-mono text-sm">
                      {monthlyEnquiries} calls/mo
                    </span>
                  </div>
                  <input
                    type="range"
                    min="100"
                    max="3000"
                    step="50"
                    value={monthlyEnquiries}
                    onChange={(e) => setMonthlyEnquiries(Number(e.target.value))}
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                  />
                  <div className="flex justify-between text-[10px] text-slate-400">
                    <span>100 Calls</span>
                    <span>1,500 Calls</span>
                    <span>3,000 Calls</span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 rounded-2xl bg-white/10 p-6 backdrop-blur-sm border border-white/10">
                <div className="p-4 rounded-xl bg-white/5">
                  <Clock className="h-6 w-6 text-indigo-400 mb-2" />
                  <p className="text-2xl sm:text-3xl font-extrabold text-white">
                    {calculatedHoursSaved}h
                  </p>
                  <p className="text-xs text-slate-300 mt-1">Staff Hours Saved / Month</p>
                </div>

                <div className="p-4 rounded-xl bg-white/5">
                  <Award className="h-6 w-6 text-emerald-400 mb-2" />
                  <p className="text-2xl sm:text-3xl font-extrabold text-emerald-400">
                    +38%
                  </p>
                  <p className="text-xs text-slate-300 mt-1">Lead Conversion Rate</p>
                </div>

                <div className="col-span-2 p-4 rounded-xl bg-white/5 flex items-center justify-between">
                  <div>
                    <p className="text-xs text-slate-300">Est. Operational Savings</p>
                    <p className="text-xl font-bold text-white">
                      ₹{calculatedCostSavings.toLocaleString("en-IN")} / mo
                    </p>
                  </div>
                  <Link href="/onboarding">
                    <Button size="sm" variant="gradient" className="font-bold">
                      Deploy Now
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-20 bg-slate-50">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-xs font-bold uppercase tracking-wider text-indigo-600">
              Pricing Built For Education
            </h2>
            <p className="mt-2 text-3xl font-extrabold text-slate-900 sm:text-4xl">
              Flexible Plans with Indian Phone Numbers Included
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* Starter Plan */}
            <Card className="border-slate-200 bg-white">
              <CardContent className="p-8 space-y-6">
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Basic Admission Starter</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    For single-campus schools and coaching centers
                  </p>
                  <div className="mt-4 flex items-baseline">
                    <span className="text-3xl font-extrabold text-slate-900">₹4,999</span>
                    <span className="text-xs text-muted-foreground ml-1">/ month</span>
                  </div>
                </div>
                <ul className="space-y-3 text-xs text-slate-600">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    1 Dedicated Indian Phone Number
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    500 Inbound Voice Minutes Included
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    Admission AI in English, Hindi & Telugu
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    Lead Qualification & Audio Recordings
                  </li>
                </ul>
                <Link href="/onboarding" className="block">
                  <Button variant="outline" className="w-full font-bold">
                    Select Starter
                  </Button>
                </Link>
              </CardContent>
            </Card>

            {/* Pro Plan */}
            <Card className="border-2 border-indigo-600 bg-white shadow-xl relative">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600 px-3 py-0.5 text-[10px] font-bold text-white uppercase tracking-wider">
                Most Popular
              </div>
              <CardContent className="p-8 space-y-6">
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Pro Institute Growth</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    For leading colleges, universities & large institutes
                  </p>
                  <div className="mt-4 flex items-baseline">
                    <span className="text-3xl font-extrabold text-slate-900">₹12,999</span>
                    <span className="text-xs text-muted-foreground ml-1">/ month</span>
                  </div>
                </div>
                <ul className="space-y-3 text-xs text-slate-600">
                  <li className="flex items-center gap-2 font-semibold text-slate-900">
                    <CheckCircle2 className="h-4 w-4 text-indigo-600 shrink-0" />
                    3 Dedicated Indian Virtual Phone Numbers
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-indigo-600 shrink-0" />
                    2,500 Inbound Voice Minutes Included
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-indigo-600 shrink-0" />
                    WhatsApp Business Lead Notifications
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-indigo-600 shrink-0" />
                    Live Counsellor Transfer Fallback
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-indigo-600 shrink-0" />
                    10 Staff Accounts with Role Permissions
                  </li>
                </ul>
                <Link href="/onboarding" className="block">
                  <Button variant="gradient" className="w-full font-bold shadow-md">
                    Start Pro Setup
                  </Button>
                </Link>
              </CardContent>
            </Card>

            {/* Enterprise Plan */}
            <Card className="border-slate-200 bg-white">
              <CardContent className="p-8 space-y-6">
                <div>
                  <h3 className="text-lg font-bold text-slate-900">Enterprise Multi-Campus</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    For university systems & multi-branch groups
                  </p>
                  <div className="mt-4 flex items-baseline">
                    <span className="text-3xl font-extrabold text-slate-900">₹29,999</span>
                    <span className="text-xs text-muted-foreground ml-1">/ month</span>
                  </div>
                </div>
                <ul className="space-y-3 text-xs text-slate-600">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    10+ Toll-Free & Virtual Numbers
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    10,000 Voice Minutes Included
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    ERP & Custom CRM Sync
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    Multi-Campus Tenant Partitioning
                  </li>
                </ul>
                <Link href="/onboarding" className="block">
                  <Button variant="outline" className="w-full font-bold">
                    Contact Enterprise
                  </Button>
                </Link>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white">
                <GraduationCap className="h-5 w-5" />
              </div>
              <div>
                <span className="font-bold text-slate-900">Edu-Voice-AI</span>
                <p className="text-xs text-muted-foreground">
                  AI Admission Communication SaaS for Educational Institutions
                </p>
              </div>
            </div>

            <div className="flex items-center gap-6 text-xs text-slate-600">
              <Link href="/dashboard" className="hover:text-indigo-600">
                Dashboard Demo
              </Link>
              <Link href="/agents/test" className="hover:text-indigo-600">
                AI Voice Test Console
              </Link>
              <Link href="/login" className="hover:text-indigo-600">
                Staff Login
              </Link>
              <Link href="/onboarding" className="hover:text-indigo-600">
                Institution Setup
              </Link>
            </div>
          </div>
          <div className="mt-8 border-t border-slate-100 pt-6 text-center text-xs text-muted-foreground">
            © 2026 Edu-Voice-AI. All rights reserved. Designed for Indian educational institutions.
          </div>
        </div>
      </footer>
    </div>
  );
}
