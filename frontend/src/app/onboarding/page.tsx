"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  GraduationCap,
  Building,
  BookOpen,
  FileText,
  Bot,
  Languages,
  PhoneCall,
  Phone,
  Sparkles,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  Plus,
  Trash2,
  Upload,
  Volume2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useDataStore } from "@/hooks/useDataStore";
import { Organization } from "@/types";

const STEPS = [
  { id: 1, title: "Institution Details", icon: Building },
  { id: 2, title: "Courses & Fees", icon: BookOpen },
  { id: 3, title: "Knowledge Upload", icon: FileText },
  { id: 4, title: "Configure AI", icon: Bot },
  { id: 5, title: "Languages & Voice", icon: Languages },
  { id: 6, title: "Human Handoff", icon: PhoneCall },
  { id: 7, title: "Phone Number", icon: Phone },
  { id: 8, title: "Test & Launch", icon: Sparkles },
];

export default function OnboardingPage() {
  const router = useRouter();
  const {
    organization,
    updateOrganization,
    agent,
    updateAgent,
    courses,
    addCourse,
    deleteCourse,
    documents,
    addDocument,
  } = useDataStore();

  const [currentStep, setCurrentStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Local form state for step 2 course adder
  const [newCourseName, setNewCourseName] = useState("");
  const [newCourseFee, setNewCourseFee] = useState(140000);
  const [newCourseDegree, setNewCourseDegree] = useState<"B.Tech" | "MBA">("B.Tech");

  // Step 8 test simulator state
  const [testQuery, setTestQuery] = useState("What is the fee for B.Tech CSE?");
  const [testResponse, setTestResponse] = useState("");
  const [isTesting, setIsTesting] = useState(false);

  const handleNext = () => {
    if (currentStep < 8) {
      setCurrentStep(currentStep + 1);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  const handleAddCourse = () => {
    if (!newCourseName) return;
    addCourse({
      name: newCourseName,
      code: newCourseName.toUpperCase().replace(/\s+/g, "-").slice(0, 8),
      degree: newCourseDegree,
      durationYears: newCourseDegree === "B.Tech" ? 4 : 2,
      annualFeeINR: newCourseFee,
      eligibility: "10+2 with MPC 60%+ or equivalent qualifying exam.",
      totalSeats: 120,
      availableSeats: 30,
      applicationDeadline: "2026-09-15",
    });
    setNewCourseName("");
  };

  const handleTestAICall = () => {
    setIsTesting(true);
    setTimeout(() => {
      setTestResponse(
        `Namaste! At ${organization.name}, the annual tuition fee for B.Tech CSE is ₹${courses[0]?.annualFeeINR.toLocaleString("en-IN") || "1,40,000"}. Would you like to reserve a seat or speak with a senior counsellor?`
      );
      setIsTesting(false);
    }, 900);
  };

  const handleCompleteLaunch = () => {
    setIsSubmitting(true);
    updateOrganization({ onboardingCompleted: true });
    setTimeout(() => {
      setIsSubmitting(false);
      router.push("/dashboard");
    }, 1000);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-20">
      {/* Top Navbar */}
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white">
              <GraduationCap className="h-5 w-5" />
            </div>
            <div>
              <span className="font-extrabold text-slate-900">Edu-Voice-AI</span>
              <p className="text-[11px] text-muted-foreground">
                Self-Service Institution Onboarding
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-slate-500">
              Step {currentStep} of {STEPS.length}
            </span>
            <div className="w-28 bg-slate-200 h-2 rounded-full overflow-hidden">
              <div
                className="bg-indigo-600 h-full transition-all duration-300"
                style={{ width: `${(currentStep / STEPS.length) * 100}%` }}
              />
            </div>
          </div>
        </div>
      </header>

      {/* Stepper Wizard Bar */}
      <div className="border-b border-slate-200 bg-white py-3 overflow-x-auto">
        <div className="mx-auto flex max-w-5xl px-4 sm:px-6 space-x-2">
          {STEPS.map((step) => {
            const isDone = currentStep > step.id;
            const isCurrent = currentStep === step.id;
            const StepIcon = step.icon;

            return (
              <button
                key={step.id}
                onClick={() => setCurrentStep(step.id)}
                className={`flex items-center gap-2 whitespace-nowrap rounded-xl px-3 py-1.5 text-xs font-bold transition-all ${
                  isCurrent
                    ? "bg-indigo-600 text-white shadow-sm"
                    : isDone
                    ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                    : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                }`}
              >
                {isDone ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                ) : (
                  <StepIcon className="h-3.5 w-3.5" />
                )}
                <span>
                  {step.id}. {step.title}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Wizard Body Container */}
      <main className="mx-auto mt-8 max-w-3xl px-4 sm:px-6">
        <Card className="border-slate-200 shadow-xl bg-white rounded-2xl overflow-hidden">
          <CardContent className="p-6 sm:p-8 space-y-6">
            {/* Step 1: Institution Details */}
            {currentStep === 1 && (
              <div className="space-y-5 animate-in fade-in duration-200">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Institution Information</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Provide basic details so your Admission AI accurately introduces your campus.
                  </p>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-semibold text-slate-700">Official Institution Name</label>
                    <Input
                      value={organization.name}
                      onChange={(e) => updateOrganization({ name: e.target.value })}
                      placeholder="e.g. ABC College of Engineering & Technology"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-semibold text-slate-700">Institution Category</label>
                      <Select
                        value={organization.type}
                        onChange={(e) =>
                          updateOrganization({
                            type: e.target.value as Organization["type"],
                          })
                        }
                      >
                        <option value="college">Engineering / Degree College</option>
                        <option value="university">University</option>
                        <option value="coaching">Competitive Exam Coaching Center</option>
                        <option value="training">Training / Skill Institute</option>
                        <option value="school">K-12 School</option>
                      </Select>
                    </div>

                    <div>
                      <label className="text-xs font-semibold text-slate-700">Tagline / Motto</label>
                      <Input
                        value={organization.tagline}
                        onChange={(e) => updateOrganization({ tagline: e.target.value })}
                        placeholder="e.g. Empowering Next-Gen Engineers Since 2004"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-semibold text-slate-700">City</label>
                      <Input
                        value={organization.city}
                        onChange={(e) => updateOrganization({ city: e.target.value })}
                        placeholder="e.g. Hyderabad"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-700">State</label>
                      <Input
                        value={organization.state}
                        onChange={(e) => updateOrganization({ state: e.target.value })}
                        placeholder="e.g. Telangana"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-slate-700">Official Website</label>
                    <Input
                      value={organization.website}
                      onChange={(e) => updateOrganization({ website: e.target.value })}
                      placeholder="https://www.abccollege.edu.in"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Step 2: Courses & Fees */}
            {currentStep === 2 && (
              <div className="space-y-5 animate-in fade-in duration-200">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Courses & Annual Fees</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Your Admission AI will quote these verified tuition fees directly to prospective students.
                  </p>
                </div>

                {/* Add course sub-form */}
                <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 space-y-3">
                  <p className="text-xs font-bold text-indigo-950">Add a Course</p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Input
                      value={newCourseName}
                      onChange={(e) => setNewCourseName(e.target.value)}
                      placeholder="Course name (e.g. B.Tech CSE)"
                    />
                    <Input
                      type="number"
                      value={newCourseFee}
                      onChange={(e) => setNewCourseFee(Number(e.target.value))}
                      placeholder="Annual Fee (INR)"
                    />
                    <Button onClick={handleAddCourse} variant="gradient" size="sm" className="font-bold">
                      <Plus className="h-4 w-4 mr-1" /> Add Course
                    </Button>
                  </div>
                </div>

                {/* Course List */}
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-slate-700">Configured Courses ({courses.length})</p>
                  {courses.map((course) => (
                    <div
                      key={course.id}
                      className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 shadow-sm hover:border-indigo-200 transition-all"
                    >
                      <div>
                        <p className="text-xs font-bold text-slate-900">{course.name}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {course.durationYears} Years • ₹{course.annualFeeINR.toLocaleString("en-IN")}/yr • {course.availableSeats} Seats Open
                        </p>
                      </div>
                      <button
                        onClick={() => deleteCourse(course.id)}
                        className="text-slate-400 hover:text-red-600 transition-colors p-1"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Step 3: Knowledge Documents */}
            {currentStep === 3 && (
              <div className="space-y-5 animate-in fade-in duration-200">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Upload Knowledge Documents</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Upload official prospectuses, fee notifications, and hostel rules to ground the AI.
                  </p>
                </div>

                {/* Upload Zone */}
                <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-indigo-200 bg-indigo-50/40 p-8 text-center hover:bg-indigo-50/70 transition-all cursor-pointer">
                  <Upload className="h-8 w-8 text-indigo-600 mb-2" />
                  <p className="text-sm font-bold text-slate-900">
                    Click to upload brochure or prospectus
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Supports PDF, DOCX, TXT, CSV up to 25MB
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-4 bg-white font-semibold"
                    onClick={() =>
                      addDocument({
                        name: "Campus_Admission_Policy_2026.pdf",
                        size: 2400000,
                        category: "courses",
                      })
                    }
                  >
                    Upload Sample Prospectus
                  </Button>
                </div>

                {/* Uploaded Documents List */}
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-slate-700">Indexed Knowledge Documents</p>
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3"
                    >
                      <div className="flex items-center gap-3">
                        <FileText className="h-5 w-5 text-indigo-600" />
                        <div>
                          <p className="text-xs font-bold text-slate-900">{doc.title}</p>
                          <p className="text-[10px] text-muted-foreground">
                            {doc.chunkCount} Chunks Indexed • Category: {doc.category}
                          </p>
                        </div>
                      </div>
                      <Badge variant="success">Indexed</Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Step 4: Configure Admission AI */}
            {currentStep === 4 && (
              <div className="space-y-5 animate-in fade-in duration-200">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Configure Admission AI Agent</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Customize your AI Admission Counsellor persona and official welcome greeting.
                  </p>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-semibold text-slate-700">AI Agent Name</label>
                    <Input
                      value={agent.name}
                      onChange={(e) => updateAgent({ name: e.target.value })}
                      placeholder="e.g. ABC Admission AI Counsellor"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-slate-700">Official Voice Greeting Message</label>
                    <Textarea
                      rows={3}
                      value={agent.greetingMessage}
                      onChange={(e) => updateAgent({ greetingMessage: e.target.value })}
                      placeholder="Greeting spoken as soon as caller connects..."
                    />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-slate-700">Zero-Hallucination Fallback Message</label>
                    <Textarea
                      rows={2}
                      value={agent.fallbackMessage}
                      onChange={(e) => updateAgent({ fallbackMessage: e.target.value })}
                      placeholder="Spoken when information is not found in knowledge base..."
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Step 5: Languages & Voice */}
            {currentStep === 5 && (
              <div className="space-y-5 animate-in fade-in duration-200">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Language & Voice Tuning</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Activate Indian regional languages and calibrate speaking speed.
                  </p>
                </div>

                <div className="space-y-4">
                  <div className="rounded-xl border border-slate-200 p-4 space-y-3">
                    <p className="text-xs font-bold text-slate-900">Multilingual Inbound Support</p>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="flex items-center justify-between rounded-lg bg-indigo-50 p-2.5 border border-indigo-100">
                        <span className="text-xs font-bold text-indigo-900">English (India)</span>
                        <CheckCircle2 className="h-4 w-4 text-indigo-600" />
                      </div>
                      <div className="flex items-center justify-between rounded-lg bg-indigo-50 p-2.5 border border-indigo-100">
                        <span className="text-xs font-bold text-indigo-900">हिन्दी (Hindi)</span>
                        <CheckCircle2 className="h-4 w-4 text-indigo-600" />
                      </div>
                      <div className="flex items-center justify-between rounded-lg bg-indigo-50 p-2.5 border border-indigo-100">
                        <span className="text-xs font-bold text-indigo-900">తెలుగు (Telugu)</span>
                        <CheckCircle2 className="h-4 w-4 text-indigo-600" />
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-semibold text-slate-700">Voice Gender</label>
                      <Select
                        value={agent.voiceGender}
                        onChange={(e) =>
                          updateAgent({
                            voiceGender: e.target.value as "female" | "male",
                          })
                        }
                      >
                        <option value="female">Female (Polite & Professional)</option>
                        <option value="male">Male (Authoritative & Warm)</option>
                      </Select>
                    </div>

                    <div>
                      <label className="text-xs font-semibold text-slate-700">Speaking Speed</label>
                      <Select
                        value={String(agent.voiceSpeed)}
                        onChange={(e) => updateAgent({ voiceSpeed: Number(e.target.value) })}
                      >
                        <option value="0.9">0.9x (Deliberate & Clear)</option>
                        <option value="1.0">1.0x (Standard Conversational)</option>
                        <option value="1.1">1.1x (Energetic)</option>
                      </Select>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Step 6: Human Handoff */}
            {currentStep === 6 && (
              <div className="space-y-5 animate-in fade-in duration-200">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Human Counsellor Escalation</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    When callers require complex evaluation or fee concessions, transfer them instantly.
                  </p>
                </div>

                <div className="space-y-4">
                  <div>
                    <label className="text-xs font-semibold text-slate-700">
                      Chief Counsellor Transfer Phone Number
                    </label>
                    <Input
                      value={agent.humanHandoffNumber}
                      onChange={(e) => updateAgent({ humanHandoffNumber: e.target.value })}
                      placeholder="+91 98480 22338"
                      leftIcon={<Phone className="h-4 w-4" />}
                    />
                  </div>

                  <div className="space-y-2 pt-2">
                    <p className="text-xs font-bold text-slate-900">Automatic Escalation Triggers</p>
                    <div className="space-y-2 rounded-xl border border-slate-200 p-4">
                      <Switch
                        checked={agent.handoffTriggers.callerRequested}
                        onCheckedChange={(checked) =>
                          updateAgent({
                            handoffTriggers: { ...agent.handoffTriggers, callerRequested: checked },
                          })
                        }
                        label="Caller Asks for Human Counsellor"
                        description="Immediately initiate call forward when caller says 'connect to counsellor'."
                      />
                      <div className="border-t border-slate-100 my-2" />
                      <Switch
                        checked={agent.handoffTriggers.feeNegotiation}
                        onCheckedChange={(checked) =>
                          updateAgent({
                            handoffTriggers: { ...agent.handoffTriggers, feeNegotiation: checked },
                          })
                        }
                        label="Special Scholarship or Fee Concession Requests"
                        description="Escalate financial aid & fee waiver discussions to human staff."
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Step 7: Indian Phone Number */}
            {currentStep === 7 && (
              <div className="space-y-5 animate-in fade-in duration-200">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Assigned Indian Virtual Number</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Your Admission AI is provisioned with a dedicated Indian inbound line.
                  </p>
                </div>

                <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-6 text-center space-y-3">
                  <Badge variant="success" className="mb-1">
                    Ready for Inbound Calls
                  </Badge>
                  <p className="font-mono text-3xl font-bold text-slate-900 tracking-wider">
                    +91 80 4719 8800
                  </p>
                  <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                    Calls to this number route directly to <span className="font-semibold">{agent.name}</span> with fallback to <span className="font-semibold">{agent.humanHandoffNumber}</span>.
                  </p>
                </div>
              </div>
            )}

            {/* Step 8: Test & Launch */}
            {currentStep === 8 && (
              <div className="space-y-5 animate-in fade-in duration-200">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Interactive Test & Go Live</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Test your configured Admission AI in real time before launching to parents and students.
                  </p>
                </div>

                <div className="rounded-2xl border border-indigo-100 bg-indigo-50/40 p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-indigo-950 flex items-center gap-1.5">
                      <Volume2 className="h-4 w-4 text-indigo-600" />
                      Live AI Test Console
                    </span>
                    <Badge variant="indigo" className="text-[10px]">
                      Simulated Call
                    </Badge>
                  </div>

                  <div className="flex gap-2">
                    <Input
                      value={testQuery}
                      onChange={(e) => setTestQuery(e.target.value)}
                      placeholder="Ask a question (e.g. What is the fee for B.Tech CSE?)"
                    />
                    <Button onClick={handleTestAICall} variant="gradient" isLoading={isTesting}>
                      Ask AI
                    </Button>
                  </div>

                  {testResponse && (
                    <div className="rounded-xl bg-white border border-indigo-100 p-4 text-xs leading-relaxed text-indigo-950 animate-in fade-in">
                      <p className="font-bold text-indigo-600 mb-1">{agent.name}:</p>
                      <p>{testResponse}</p>
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 flex items-center gap-3">
                  <CheckCircle2 className="h-6 w-6 text-emerald-600 shrink-0" />
                  <div className="text-xs">
                    <p className="font-bold text-emerald-900">All 8 Configuration Steps Verified</p>
                    <p className="text-emerald-700">
                      Your institution profile, courses, prospectus RAG, and virtual line are ready.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Navigation Button Controls */}
            <div className="flex items-center justify-between pt-6 border-t border-slate-100">
              <Button
                variant="outline"
                onClick={handleBack}
                disabled={currentStep === 1}
                className="font-semibold"
              >
                <ArrowLeft className="mr-1.5 h-4 w-4" /> Back
              </Button>

              {currentStep < 8 ? (
                <Button variant="gradient" onClick={handleNext} className="font-bold">
                  Next Step <ArrowRight className="ml-1.5 h-4 w-4" />
                </Button>
              ) : (
                <Button
                  variant="gradient"
                  onClick={handleCompleteLaunch}
                  isLoading={isSubmitting}
                  className="font-bold px-8 shadow-lg shadow-indigo-500/25"
                >
                  <Sparkles className="mr-2 h-4 w-4" /> Go Live to Dashboard
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
