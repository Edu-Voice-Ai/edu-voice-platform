"use client";

import React, { useState } from "react";
import {
  CreditCard,
  CheckCircle2,
  Zap,
  TrendingUp,
  Clock,
  Phone,
  BookOpen,
  Users,
  Sparkles,
  ArrowRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { useDataStore } from "@/hooks/useDataStore";
import { SubscriptionPlan } from "@/types";

export default function BillingPage() {
  const { plans } = useDataStore();
  const [currentPlanId, setCurrentPlanId] = useState<"basic" | "pro" | "enterprise">("pro");
  const [isUpgradeModalOpen, setIsUpgradeModalOpen] = useState(false);

  const currentPlan = plans.find((p) => p.id === currentPlanId) || plans[1];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <CreditCard className="h-6 w-6 text-indigo-600" />
            Subscription & Resource Usage
          </h1>
          <p className="text-xs text-muted-foreground">
            Manage your institution plan, voice minute allocations, and virtual phone number limits.
          </p>
        </div>

        <Button
          size="sm"
          variant="gradient"
          onClick={() => setIsUpgradeModalOpen(true)}
          className="text-xs font-bold shadow-md"
        >
          <Zap className="h-3.5 w-3.5 mr-1" /> Upgrade Subscription
        </Button>
      </div>

      {/* Current Plan Overview Banner */}
      <div className="rounded-2xl bg-gradient-to-r from-indigo-900 via-indigo-800 to-slate-900 p-6 text-white shadow-xl">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1">
            <Badge variant="indigo" className="bg-indigo-500/30 text-indigo-200 border-indigo-400/40">
              Active Tier
            </Badge>
            <h2 className="text-2xl font-bold">{currentPlan.name}</h2>
            <p className="text-xs text-indigo-200">{currentPlan.tagline}</p>
          </div>

          <div className="text-right">
            <span className="text-3xl font-extrabold font-mono">
              ₹{currentPlan.priceMonthlyINR.toLocaleString("en-IN")}
            </span>
            <span className="text-xs text-indigo-300 ml-1">/ month</span>
            <p className="text-[10px] text-indigo-300 mt-0.5">Next renewal: 30 September 2026</p>
          </div>
        </div>
      </div>

      {/* Resource Meters Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Voice Minutes Meter */}
        <Card className="shadow-sm">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">Inbound Minutes</span>
              <Clock className="h-4 w-4 text-indigo-600" />
            </div>
            <div>
              <span className="text-2xl font-bold font-mono text-slate-900">
                {currentPlan.voiceMinutesUsed}
              </span>
              <span className="text-xs text-muted-foreground ml-1">
                / {currentPlan.voiceMinutesIncluded} mins
              </span>
            </div>
            <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-600 rounded-full"
                style={{
                  width: `${(currentPlan.voiceMinutesUsed / currentPlan.voiceMinutesIncluded) * 100}%`,
                }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Phone Numbers Meter */}
        <Card className="shadow-sm">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">Virtual Lines</span>
              <Phone className="h-4 w-4 text-emerald-600" />
            </div>
            <div>
              <span className="text-2xl font-bold font-mono text-slate-900">
                {currentPlan.phoneNumbersUsed}
              </span>
              <span className="text-xs text-muted-foreground ml-1">
                / {currentPlan.phoneNumbersIncluded} numbers
              </span>
            </div>
            <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-600 rounded-full"
                style={{
                  width: `${(currentPlan.phoneNumbersUsed / currentPlan.phoneNumbersIncluded) * 100}%`,
                }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Knowledge Documents Meter */}
        <Card className="shadow-sm">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">Knowledge Docs</span>
              <BookOpen className="h-4 w-4 text-violet-600" />
            </div>
            <div>
              <span className="text-2xl font-bold font-mono text-slate-900">
                {currentPlan.knowledgeDocsUsed}
              </span>
              <span className="text-xs text-muted-foreground ml-1">
                / {currentPlan.knowledgeDocsLimit} docs
              </span>
            </div>
            <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-violet-600 rounded-full"
                style={{
                  width: `${(currentPlan.knowledgeDocsUsed / currentPlan.knowledgeDocsLimit) * 100}%`,
                }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Staff Users Meter */}
        <Card className="shadow-sm">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">Staff Counsellor Seats</span>
              <Users className="h-4 w-4 text-amber-600" />
            </div>
            <div>
              <span className="text-2xl font-bold font-mono text-slate-900">2</span>
              <span className="text-xs text-muted-foreground ml-1">
                / {currentPlan.maxStaffUsers} seats
              </span>
            </div>
            <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-amber-500 rounded-full"
                style={{ width: `${(2 / currentPlan.maxStaffUsers) * 100}%` }}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Plan Comparison Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4">
        {plans.map((p) => {
          const isSelected = p.id === currentPlanId;
          return (
            <Card
              key={p.id}
              className={`shadow-sm transition-all ${
                isSelected ? "border-2 border-indigo-600 shadow-lg" : "border-slate-200"
              }`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-bold">{p.name}</CardTitle>
                  {isSelected && (
                    <Badge variant="indigo" className="text-[10px]">
                      Current
                    </Badge>
                  )}
                </div>
                <CardDescription className="text-xs">{p.tagline}</CardDescription>
                <div className="pt-2">
                  <span className="text-2xl font-extrabold font-mono">
                    ₹{p.priceMonthlyINR.toLocaleString("en-IN")}
                  </span>
                  <span className="text-xs text-muted-foreground"> / mo</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-2 text-xs text-slate-700">
                  {p.features.map((feat) => (
                    <li key={feat} className="flex items-center gap-2">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                      <span>{feat}</span>
                    </li>
                  ))}
                </ul>

                <Button
                  variant={isSelected ? "outline" : "gradient"}
                  className="w-full text-xs font-bold"
                  onClick={() => {
                    setCurrentPlanId(p.id);
                    setIsUpgradeModalOpen(false);
                  }}
                  disabled={isSelected}
                >
                  {isSelected ? "Current Active Plan" : `Switch to ${p.name}`}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Upgrade Modal */}
      <Modal
        isOpen={isUpgradeModalOpen}
        onClose={() => setIsUpgradeModalOpen(false)}
        title="Upgrade Institution Subscription"
        description="Select a plan with expanded voice minutes and multi-number support."
      >
        <div className="space-y-4 text-xs">
          <p className="text-slate-700 leading-relaxed">
            Need additional concurrent lines or high-volume admission campaign capacity? You can switch plans seamlessly at any time with prorated billing.
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsUpgradeModalOpen(false)}
            >
              Close
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
