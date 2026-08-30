"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Bot,
  Languages,
  Volume2,
  PhoneCall,
  Clock,
  Sparkles,
  Save,
  CheckCircle2,
  Phone,
  ShieldAlert,
  Play,
  Sliders,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { useDataStore } from "@/hooks/useDataStore";

export default function AgentsPage() {
  const { agent, updateAgent } = useDataStore();
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [isPlayingPreview, setIsPlayingPreview] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  const handlePlayVoiceSample = () => {
    setIsPlayingPreview(true);
    setTimeout(() => setIsPlayingPreview(false), 2500);
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Bot className="h-6 w-6 text-indigo-600" />
            Admission AI Management
          </h1>
          <p className="text-xs text-muted-foreground">
            Configure conversational behavior, multilingual voices, and human handoff rules.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link href="/agents/test">
            <Button variant="gradient" size="sm" className="font-bold text-xs shadow-md">
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              Open Voice Test Console
            </Button>
          </Link>

          <Button
            type="button"
            onClick={handleSave}
            size="sm"
            className="bg-indigo-600 text-white hover:bg-indigo-700 font-bold text-xs"
          >
            <Save className="mr-1.5 h-3.5 w-3.5" />
            Save Changes
          </Button>
        </div>
      </div>

      {savedSuccess && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-emerald-800 font-semibold flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          Admission AI configuration successfully updated and synced with inbound telephony.
        </div>
      )}

      {/* Main Configuration Grid */}
      <form onSubmit={handleSave} className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Agent Persona & Prompts */}
        <div className="lg:col-span-2 space-y-6">
          {/* Persona & Greeting */}
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base font-bold">Agent Persona & Status</CardTitle>
                  <CardDescription className="text-xs">
                    Define the AI identity and official inbound voice greeting
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-600">Active Inbound</span>
                  <Switch
                    checked={agent.status === "active"}
                    onCheckedChange={(checked) =>
                      updateAgent({ status: checked ? "active" : "inactive" })
                    }
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Agent Display Name
                </label>
                <Input
                  value={agent.name}
                  onChange={(e) => updateAgent({ name: e.target.value })}
                  placeholder="e.g. ABC Admission AI Counsellor"
                />
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                    Official Welcome Greeting (Spoken upon connection)
                  </label>
                  <span className="text-[10px] text-muted-foreground">Supports EN, HI, TE</span>
                </div>
                <Textarea
                  rows={3}
                  value={agent.greetingMessage}
                  onChange={(e) => updateAgent({ greetingMessage: e.target.value })}
                />
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                    Zero-Hallucination Grounding Fallback
                  </label>
                  <Badge variant="indigo" className="text-[9px]">
                    Strict Accuracy
                  </Badge>
                </div>
                <Textarea
                  rows={2}
                  value={agent.fallbackMessage}
                  onChange={(e) => updateAgent({ fallbackMessage: e.target.value })}
                />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  The AI never guesses fees or dates. If unverified, this fallback triggers and offers human counsellor escalation.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Multilingual & Code-Mixing Settings */}
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Languages className="h-4 w-4 text-indigo-600" />
                Multilingual Voice Capabilities
              </CardTitle>
              <CardDescription className="text-xs">
                Indian regional language detection and code-mixed conversational support
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-3.5 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-indigo-950">English (India)</span>
                    <Badge variant="success" className="text-[9px]">Active</Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Indian English accent with technical course terminology.
                  </p>
                </div>

                <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-3.5 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-indigo-950">हिन्दी (Hindi)</span>
                    <Badge variant="success" className="text-[9px]">Active</Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Native Hindi vocabulary with Hinglish code-mixing.
                  </p>
                </div>

                <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-3.5 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-indigo-950">తెలుగు (Telugu)</span>
                    <Badge variant="success" className="text-[9px]">Active</Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Andhra & Telangana regional dialect grounding.
                  </p>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 p-4 bg-slate-50/50 space-y-2">
                <p className="text-xs font-bold text-slate-900">Voice Synthesis & Calibrations</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
                  <div>
                    <label className="text-xs font-semibold text-slate-700">Voice Persona</label>
                    <Select
                      value={agent.voiceGender}
                      onChange={(e) =>
                        updateAgent({
                          voiceGender: e.target.value as "female" | "male",
                        })
                      }
                    >
                      <option value="female">Priya (Female - Warm & Professional)</option>
                      <option value="male">Rohan (Male - Confident & Clear)</option>
                    </Select>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-slate-700">Speaking Pace</label>
                    <Select
                      value={String(agent.voiceSpeed)}
                      onChange={(e) => updateAgent({ voiceSpeed: Number(e.target.value) })}
                    >
                      <option value="0.9">0.9x — Deliberate & Patient</option>
                      <option value="1.0">1.0x — Standard Inbound Rate</option>
                      <option value="1.1">1.1x — Fast & Dynamic</option>
                    </Select>
                  </div>
                </div>

                <div className="pt-2 flex justify-end">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handlePlayVoiceSample}
                    className="text-xs font-semibold"
                  >
                    <Play className="h-3 w-3 mr-1.5" />
                    {isPlayingPreview ? "Playing Sample..." : "Listen to Voice Sample"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right 1 Column: Human Handoff & Business Hours */}
        <div className="space-y-6">
          {/* Human Escalation Settings */}
          <Card className="shadow-sm border-amber-100 bg-amber-50/20">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <PhoneCall className="h-4 w-4 text-amber-600" />
                Human Counsellor Escalation
              </CardTitle>
              <CardDescription className="text-xs">
                Live call transfer conditions and fallback phone numbers
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700">
                  Chief Counsellor Transfer Number
                </label>
                <Input
                  value={agent.humanHandoffNumber}
                  onChange={(e) => updateAgent({ humanHandoffNumber: e.target.value })}
                  placeholder="+91 98480 22338"
                  leftIcon={<Phone className="h-4 w-4" />}
                />
                <p className="mt-1 text-[10px] text-muted-foreground">
                  Target destination when transfer is initiated during active call.
                </p>
              </div>

              <div className="space-y-3 pt-2">
                <p className="text-xs font-bold text-slate-900">Escalation Triggers</p>
                <div className="space-y-2.5">
                  <Switch
                    checked={agent.handoffTriggers.callerRequested}
                    onCheckedChange={(c) =>
                      updateAgent({
                        handoffTriggers: { ...agent.handoffTriggers, callerRequested: c },
                      })
                    }
                    label="Caller requests human counsellor"
                  />
                  <Switch
                    checked={agent.handoffTriggers.feeNegotiation}
                    onCheckedChange={(c) =>
                      updateAgent({
                        handoffTriggers: { ...agent.handoffTriggers, feeNegotiation: c },
                      })
                    }
                    label="Special scholarship or fee waiver query"
                  />
                  <Switch
                    checked={agent.handoffTriggers.lowConfidence}
                    onCheckedChange={(c) =>
                      updateAgent({
                        handoffTriggers: { ...agent.handoffTriggers, lowConfidence: c },
                      })
                    }
                    label="Knowledge confidence below 85%"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Calling Hours & Timings */}
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <Clock className="h-4 w-4 text-indigo-600" />
                Operating Hours
              </CardTitle>
              <CardDescription className="text-xs">
                Inbound call handling schedule
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[11px] font-semibold text-slate-700">Start Time</label>
                  <Input
                    value={agent.businessHours.startTime}
                    onChange={(e) =>
                      updateAgent({
                        businessHours: { ...agent.businessHours, startTime: e.target.value },
                      })
                    }
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-slate-700">End Time</label>
                  <Input
                    value={agent.businessHours.endTime}
                    onChange={(e) =>
                      updateAgent({
                        businessHours: { ...agent.businessHours, endTime: e.target.value },
                      })
                    }
                  />
                </div>
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-700">After-Hours Action</label>
                <Select
                  value={agent.businessHours.afterHoursAction}
                  onChange={(e) =>
                    updateAgent({
                      businessHours: {
                        ...agent.businessHours,
                        afterHoursAction: e.target.value as "take_voicemail" | "ai_only" | "reject",
                      },
                    })
                  }
                >
                  <option value="ai_only">AI Answers 24/7 (Voicemail for Human)</option>
                  <option value="take_voicemail">Take Callback Request Only</option>
                </Select>
              </div>
            </CardContent>
          </Card>
        </div>
      </form>
    </div>
  );
}
