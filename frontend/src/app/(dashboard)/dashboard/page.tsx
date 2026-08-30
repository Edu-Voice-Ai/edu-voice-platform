"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  PhoneCall,
  Bot,
  Users,
  CalendarClock,
  Sparkles,
  PhoneForwarded,
  ArrowUpRight,
  TrendingUp,
  Clock,
  BookOpen,
  Phone,
  FileText,
  ChevronRight,
  Play,
  CheckCircle2,
  AlertCircle,
  Plus,
} from "lucide-react";
import { StatCard } from "@/components/ui/stat-card";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Drawer } from "@/components/ui/drawer";
import { useDataStore } from "@/hooks/useDataStore";
import { CallRecord, LeadRecord } from "@/types";
import { formatDuration, formatRelativeDate } from "@/lib/utils";

export default function DashboardPage() {
  const {
    organization,
    agent,
    updateAgent,
    calls,
    leads,
    followUps,
    documents,
    phoneNumbers,
    analytics,
  } = useDataStore();

  const [selectedCall, setSelectedCall] = useState<CallRecord | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);

  const activeNumber = phoneNumbers.find((p) => p.status === "active");
  const recentCalls = calls.slice(0, 5);
  const hotLeads = leads
    .filter((l) => l.status === "Highly Interested" || l.status === "Callback Requested")
    .slice(0, 5);

  const toggleAgentStatus = () => {
    updateAgent({ status: agent.status === "active" ? "inactive" : "active" });
  };

  return (
    <div className="space-y-6">
      {/* Top Banner: Admission AI Health Status */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-indigo-900 via-indigo-800 to-slate-900 p-6 text-white shadow-xl">
        <div className="relative z-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="flex h-2.5 w-2.5 relative">
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
              </span>
              <Badge
                variant={agent.status === "active" ? "success" : "warning"}
                className="text-xs"
              >
                {agent.status === "active" ? "Admission AI — Demo Simulator Mode" : "AI Inbound Paused"}
              </Badge>
              <span className="text-xs font-mono text-indigo-200">
                Demo Line: {activeNumber?.formattedNumber || "+91 80 4719 8800"}
              </span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight">
              {organization.name} — Admission Intelligence (Demo)
            </h1>
            <p className="text-xs text-indigo-200">
              {agent.name} is configured to simulate inbound enquiries in English, Hindi & Telugu.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link href="/agents/test">
              <Button
                size="sm"
                variant="gradient"
                className="bg-white text-indigo-900 hover:bg-slate-100 shadow-md font-bold text-xs"
              >
                <Sparkles className="h-3.5 w-3.5 mr-1.5 text-indigo-600" />
                Live Voice Test
              </Button>
            </Link>

            <Button
              size="sm"
              variant="outline"
              onClick={toggleAgentStatus}
              className="bg-white/10 border-white/20 text-white hover:bg-white/20 text-xs font-semibold"
            >
              {agent.status === "active" ? "Pause Agent" : "Resume Agent"}
            </Button>
          </div>
        </div>
      </div>

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Inbound Calls"
          value={analytics.totalCalls.toLocaleString("en-IN")}
          change={{ value: "+18.4%", isPositive: true, period: "vs last week" }}
          icon={<PhoneCall className="h-5 w-5 text-indigo-600" />}
          iconBgColor="bg-indigo-50 dark:bg-indigo-950/50"
        />

        <StatCard
          title="AI Resolution Rate"
          value={`${analytics.aiHandledPercentage}%`}
          change={{ value: "+4.2%", isPositive: true, period: "1,354 fully handled" }}
          icon={<Bot className="h-5 w-5 text-emerald-600" />}
          iconBgColor="bg-emerald-50 dark:bg-emerald-950/50"
        />

        <StatCard
          title="Qualified Leads Captured"
          value={analytics.totalLeadsCaptured.toLocaleString("en-IN")}
          change={{ value: "+24.8%", isPositive: true, period: "312 Highly Interested" }}
          icon={<Users className="h-5 w-5 text-violet-600" />}
          iconBgColor="bg-violet-50 dark:bg-violet-950/50"
        />

        <StatCard
          title="Human Transfers"
          value={analytics.humanTransfers}
          subtitle="8.6% escalation to counsellor"
          icon={<PhoneForwarded className="h-5 w-5 text-amber-600" />}
          iconBgColor="bg-amber-50 dark:bg-amber-950/50"
        />
      </div>

      {/* Admission Funnel & Course Demand Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Weekly Call Trend & Admission Funnel */}
        <Card className="lg:col-span-2 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base font-bold">Admission Call Volume & Lead Capture (Sample Data)</CardTitle>
                <CardDescription className="text-xs">
                  Daily simulated inbound call volume vs qualified leads extracted
                </CardDescription>
              </div>
              <Badge variant="indigo" className="text-xs">
                Demo Trend
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Visual Trend Bars */}
            <div className="grid grid-cols-7 gap-2 pt-2">
              {analytics.callTrends.map((trend) => {
                const maxCalls = 300;
                const heightPct = Math.round((trend.calls / maxCalls) * 100);

                return (
                  <div key={trend.date} className="flex flex-col items-center gap-1.5">
                    <div className="relative flex h-32 w-full flex-col justify-end rounded-lg bg-slate-100 dark:bg-slate-800 p-1">
                      <div
                        className="w-full rounded bg-indigo-600 transition-all duration-300 hover:bg-indigo-500"
                        style={{ height: `${heightPct}%` }}
                        title={`${trend.calls} calls on ${trend.date}`}
                      />
                    </div>
                    <span className="text-[10px] font-semibold text-slate-500">{trend.date}</span>
                    <span className="text-[10px] font-mono font-bold text-slate-700 dark:text-slate-300">
                      {trend.calls}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Funnel conversion summary */}
            <div className="grid grid-cols-3 gap-3 border-t border-slate-100 pt-4 dark:border-slate-800 text-center">
              <div>
                <p className="text-xs text-muted-foreground">Inbound Calls</p>
                <p className="text-base font-bold text-slate-900 dark:text-slate-100">1,482</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Prospects Qualified</p>
                <p className="text-base font-bold text-indigo-600">846 (57%)</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Counsellor Callbacks</p>
                <p className="text-base font-bold text-emerald-600">312 (37%)</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Top Enquired Courses & Language Split */}
        <Card className="shadow-sm space-y-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-bold">Top Course Inquiries</CardTitle>
            <CardDescription className="text-xs">
              Student demand breakdown from AI transcripts
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {analytics.topCourses.map((course) => {
              const maxEnq = 700;
              const pct = Math.round((course.enquiries / maxEnq) * 100);
              return (
                <div key={course.name} className="space-y-1">
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-800 dark:text-slate-200">{course.name}</span>
                    <span className="text-slate-500 font-mono">{course.enquiries} calls</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}

            <div className="border-t border-slate-100 pt-3 dark:border-slate-800">
              <p className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-2">
                Language Split
              </p>
              <div className="flex gap-2 text-xs">
                <span className="rounded-lg bg-indigo-50 px-2 py-1 font-semibold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                  English 48%
                </span>
                <span className="rounded-lg bg-emerald-50 px-2 py-1 font-semibold text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                  Telugu 32%
                </span>
                <span className="rounded-lg bg-amber-50 px-2 py-1 font-semibold text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                  Hindi 20%
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Two Column Layout: Recent Calls vs Hot Leads */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Inbound Calls Stream */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold">Recent Inbound Calls</CardTitle>
              <CardDescription className="text-xs">
                Real-time admission enquiries and transcripts
              </CardDescription>
            </div>
            <Link href="/calls">
              <Button variant="ghost" size="sm" className="text-xs font-semibold text-indigo-600">
                View All Calls <ChevronRight className="ml-1 h-3.5 w-3.5" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {recentCalls.map((call) => (
              <div
                key={call.id}
                onClick={() => setSelectedCall(call)}
                className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/60 p-3.5 hover:border-indigo-200 hover:bg-indigo-50/30 transition-all cursor-pointer group"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-indigo-600 shadow-sm border border-slate-200 dark:bg-slate-800 dark:border-slate-700">
                    <Phone className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-xs font-bold text-slate-900 dark:text-slate-100">
                        {call.callerName || call.callerNumber}
                      </p>
                      <Badge
                        variant={call.status === "completed" ? "success" : "warning"}
                        className="text-[9px] py-0 px-1.5"
                      >
                        {call.status === "completed" ? "AI Answered" : "Transferred"}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-1 max-w-[280px]">
                      {call.aiSummary}
                    </p>
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <span className="text-[10px] font-mono text-slate-400 block">
                    {formatDuration(call.durationSeconds)}
                  </span>
                  <span className="text-[10px] text-slate-500 font-semibold">
                    {formatRelativeDate(call.startedAt)}
                  </span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Priority Hot Leads */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold">Priority Admission Leads</CardTitle>
              <CardDescription className="text-xs">
                Prospective students requiring counsellor callback
              </CardDescription>
            </div>
            <Link href="/leads">
              <Button variant="ghost" size="sm" className="text-xs font-semibold text-indigo-600">
                View CRM <ChevronRight className="ml-1 h-3.5 w-3.5" />
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {hotLeads.map((lead) => (
              <div
                key={lead.id}
                className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50/60 p-3.5 hover:border-indigo-200 transition-all"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <p className="text-xs font-bold text-slate-900 dark:text-slate-100">
                      {lead.studentName}
                    </p>
                    <Badge
                      variant={lead.status === "Highly Interested" ? "indigo" : "warning"}
                      className="text-[9px] py-0 px-1.5"
                    >
                      {lead.status}
                    </Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {lead.courseInterested} • {lead.currentQualification}
                  </p>
                  {lead.preferredCallbackTime && (
                    <p className="text-[10px] font-semibold text-indigo-600 flex items-center gap-1">
                      <Clock className="h-3 w-3" /> Callback: {lead.preferredCallbackTime}
                    </p>
                  )}
                </div>

                <Link href={`/leads`}>
                  <Button size="sm" variant="outline" className="text-xs h-7 px-2.5">
                    View Lead
                  </Button>
                </Link>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Call Details Drawer */}
      {selectedCall && (
        <Drawer
          isOpen={!!selectedCall}
          onClose={() => {
            setSelectedCall(null);
            setIsPlayingAudio(false);
          }}
          title="Call Recording & Transcript"
          description={`Caller: ${selectedCall.callerName || selectedCall.callerNumber} • Duration: ${formatDuration(selectedCall.durationSeconds)}`}
        >
          <div className="space-y-6">
            {/* Audio Waveform Player Simulation */}
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setIsPlayingAudio(!isPlayingAudio)}
                    className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-600 text-white shadow-md hover:bg-indigo-700"
                  >
                    <Play className="h-4 w-4 ml-0.5" />
                  </button>
                  <div>
                    <p className="text-xs font-bold text-indigo-950">Inbound Call Audio</p>
                    <p className="text-[10px] text-indigo-700">
                      {isPlayingAudio ? "Playing audio recording..." : "00:00 / 03:44"}
                    </p>
                  </div>
                </div>
                <Badge variant="indigo" className="text-[10px]">
                  {selectedCall.primaryLanguage.toUpperCase()}
                </Badge>
              </div>

              {/* Simulated Waveform Bar */}
              <div className="flex items-center gap-1 h-8 px-2 bg-white/80 rounded-lg">
                {[12, 24, 32, 16, 28, 40, 20, 36, 44, 24, 18, 30, 42, 22, 16, 28, 38, 20].map(
                  (h, i) => (
                    <div
                      key={i}
                      className={`flex-1 rounded-full transition-all duration-300 ${
                        isPlayingAudio ? "bg-indigo-600 animate-pulse" : "bg-slate-300"
                      }`}
                      style={{ height: `${h}px` }}
                    />
                  )
                )}
              </div>
            </div>

            {/* AI Summary Card */}
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-1.5">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                AI Conversation Summary
              </p>
              <p className="text-xs text-slate-800 leading-relaxed">{selectedCall.aiSummary}</p>
              <div className="flex flex-wrap gap-1.5 pt-2">
                {selectedCall.keyTopicsDiscussed.map((topic) => (
                  <span
                    key={topic}
                    className="rounded bg-white border border-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-700"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>

            {/* Full Transcript */}
            <div className="space-y-3">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Full Dialogue Transcript
              </p>
              <div className="space-y-3">
                {selectedCall.transcript.map((msg, index) => (
                  <div
                    key={index}
                    className={`flex items-start gap-3 text-xs leading-relaxed ${
                      msg.speaker === "ai"
                        ? "bg-indigo-50/60 border border-indigo-100 p-3 rounded-xl"
                        : "bg-slate-100 p-3 rounded-xl"
                    }`}
                  >
                    <span
                      className={`font-bold shrink-0 ${
                        msg.speaker === "ai" ? "text-indigo-700" : "text-slate-800"
                      }`}
                    >
                      {msg.speaker === "ai" ? "Admission AI" : "Caller"} ({msg.timestamp}):
                    </span>
                    <p className="text-slate-800">{msg.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
}
