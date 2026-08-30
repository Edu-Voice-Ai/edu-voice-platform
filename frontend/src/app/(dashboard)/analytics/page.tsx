"use client";

import React from "react";
import {
  BarChart3,
  TrendingUp,
  PhoneCall,
  Bot,
  Users,
  Award,
  Languages,
  Clock,
  HelpCircle,
  ArrowUpRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatCard } from "@/components/ui/stat-card";
import { useDataStore } from "@/hooks/useDataStore";

export default function AnalyticsPage() {
  const { analytics } = useDataStore();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-indigo-600" />
            Admission AI Performance & Voice Analytics
          </h1>
          <p className="text-xs text-muted-foreground">
            Real-time conversion metrics, peak calling hours, and regional language demand.
          </p>
        </div>

        <Badge variant="indigo" className="text-xs py-1 px-3">
          Academic Year 2026-27 Inbound
        </Badge>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Inbound Minutes"
          value="4,149 mins"
          change={{ value: "+22.4%", isPositive: true, period: "this month" }}
          icon={<Clock className="h-5 w-5 text-indigo-600" />}
        />
        <StatCard
          title="AI Self-Resolution"
          value="91.4%"
          change={{ value: "+4.2%", isPositive: true, period: "1,354 calls" }}
          icon={<Bot className="h-5 w-5 text-emerald-600" />}
        />
        <StatCard
          title="Lead Qualification Rate"
          value="57.1%"
          change={{ value: "+8.5%", isPositive: true, period: "846 prospects" }}
          icon={<Users className="h-5 w-5 text-violet-600" />}
        />
        <StatCard
          title="Confirmed Admissions"
          value="84 Students"
          change={{ value: "+38%", isPositive: true, period: "first round" }}
          icon={<Award className="h-5 w-5 text-amber-600" />}
        />
      </div>

      {/* Conversion Funnel & Peak Inbound Calling Hours */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Admission Funnel */}
        <Card className="lg:col-span-2 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold">Admission Pipeline Funnel</CardTitle>
            <CardDescription className="text-xs">
              Progression from raw phone inquiry to confirmed enrolled student
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              { label: "1. Total Inbound Phone Calls", count: 1482, pct: 100, color: "bg-indigo-600" },
              { label: "2. Prospect Details & Intent Captured", count: 846, pct: 57, color: "bg-indigo-500" },
              { label: "3. Highly Interested & Callbacks", count: 312, pct: 21, color: "bg-violet-500" },
              { label: "4. Human Counsellor Consultations", count: 128, pct: 9, color: "bg-emerald-500" },
              { label: "5. Fee Paid & Enrolled", count: 84, pct: 6, color: "bg-emerald-600" },
            ].map((stage) => (
              <div key={stage.label} className="space-y-1.5">
                <div className="flex justify-between text-xs font-semibold">
                  <span className="text-slate-800 dark:text-slate-200">{stage.label}</span>
                  <span className="text-slate-600 font-mono">
                    {stage.count.toLocaleString("en-IN")} ({stage.pct}%)
                  </span>
                </div>
                <div className="h-4 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full ${stage.color} rounded-full transition-all duration-500`}
                    style={{ width: `${stage.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Multilingual Voice Split */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold flex items-center gap-2">
              <Languages className="h-4 w-4 text-indigo-600" />
              Language Breakdown
            </CardTitle>
            <CardDescription className="text-xs">
              Caller primary dialect distribution
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {analytics.languageBreakdown.map((item) => (
              <div key={item.language} className="space-y-1.5">
                <div className="flex justify-between text-xs font-semibold">
                  <span className="text-slate-800 dark:text-slate-200">{item.language}</span>
                  <span className="text-slate-500 font-mono">
                    {item.count} calls ({item.percentage}%)
                  </span>
                </div>
                <div className="h-2.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <div
                    className="h-full bg-indigo-600 rounded-full"
                    style={{ width: `${item.percentage}%` }}
                  />
                </div>
              </div>
            ))}

            <div className="rounded-xl bg-indigo-50/70 p-3 text-[11px] text-indigo-900 border border-indigo-100 mt-4 leading-relaxed">
              <p className="font-bold">Multilingual Code-Mixing Insight:</p>
              <p className="mt-0.5 text-indigo-700">
                Over 42% of Telugu callers comfortably code-mixed technical English terms (e.g., &quot;B.Tech CSE seats&quot;, &quot;hostel fees&quot;) without confusion.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Hourly Inbound Calling Volume Histogram */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-bold">Peak Inbound Calling Hours (IST)</CardTitle>
          <CardDescription className="text-xs">
            Volume distribution throughout the academic enquiry workday
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-6 sm:grid-cols-12 gap-2 pt-2">
            {analytics.hourlyVolume.map((item) => {
              const maxVol = 280;
              const heightPct = Math.round((item.calls / maxVol) * 100);

              return (
                <div key={item.hour} className="flex flex-col items-center gap-1.5">
                  <div className="relative flex h-28 w-full flex-col justify-end rounded-lg bg-slate-100 dark:bg-slate-800 p-1">
                    <div
                      className="w-full rounded bg-gradient-to-t from-indigo-600 to-violet-500 transition-all duration-300"
                      style={{ height: `${heightPct}%` }}
                    />
                  </div>
                  <span className="text-[10px] font-semibold text-slate-500">{item.hour}</span>
                  <span className="text-[9px] font-mono font-bold text-slate-700 dark:text-slate-300">
                    {item.calls}
                  </span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
