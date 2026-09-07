"use client";

import React, { useState } from "react";
import {
  MessageSquare,
  CheckCircle2,
  QrCode,
  Sparkles,
  Link2,
  Send,
  ShieldCheck,
  AlertCircle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useDataStore } from "@/hooks/useDataStore";

export default function WhatsAppPage() {
  const { organization } = useDataStore();
  const [isConnected, setIsConnected] = useState(true);
  const [autoSendProspectus, setAutoSendProspectus] = useState(true);
  const [autoSendConfirmation, setAutoSendConfirmation] = useState(true);
  const [unifiedKnowledge, setUnifiedKnowledge] = useState(true);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <MessageSquare className="h-6 w-6 text-emerald-600" />
            WhatsApp Business Integration
          </h1>
          <p className="text-xs text-muted-foreground">
            Automate admission brochures, application links, and callback confirmations via WhatsApp.
          </p>
        </div>

        <Badge
          variant={isConnected ? "success" : "warning"}
          className="text-xs py-1 px-3"
        >
          {isConnected ? "WhatsApp Business Connected" : "Integration Paused"}
        </Badge>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Connection Status Card */}
        <Card className="lg:col-span-2 shadow-sm">
          <CardHeader className="pb-3 border-b border-slate-100">
            <CardTitle className="text-base font-bold">Meta WhatsApp Business Account</CardTitle>
            <CardDescription className="text-xs">
              Direct official API channel for {organization.name}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-6 space-y-5">
            <div className="flex items-center justify-between rounded-xl bg-slate-50 p-4 border border-slate-200">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-sm">
                  <MessageSquare className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-900">
                    +91 80 4719 8800 (Verified Business)
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    Meta Cloud API • Green Tick Official Profile
                  </p>
                </div>
              </div>

              <Button
                size="sm"
                variant={isConnected ? "outline" : "gradient"}
                onClick={() => setIsConnected(!isConnected)}
                className="text-xs font-semibold"
              >
                {isConnected ? "Disconnect Channel" : "Connect Meta Account"}
              </Button>
            </div>

            {/* Automation Rules */}
            <div className="space-y-3">
              <p className="text-xs font-bold text-slate-900">Admission Automation Triggers</p>
              <div className="space-y-3 rounded-xl border border-slate-200 p-4">
                <Switch
                  checked={autoSendProspectus}
                  onCheckedChange={setAutoSendProspectus}
                  label="Instant Prospectus & Fee Structure via WhatsApp"
                  description="When prospective student requests course brochure during voice call, auto-send official PDF link."
                />
                <div className="border-t border-slate-100 my-2" />
                <Switch
                  checked={autoSendConfirmation}
                  onCheckedChange={setAutoSendConfirmation}
                  label="Counsellor Callback Confirmation Message"
                  description="Immediately send WhatsApp text confirming counsellor name and scheduled callback appointment."
                />
                <div className="border-t border-slate-100 my-2" />
                <Switch
                  checked={unifiedKnowledge}
                  onCheckedChange={setUnifiedKnowledge}
                  label="Unified Grounded Knowledge RAG"
                  description="Use the exact same verified campus knowledge base for WhatsApp text queries as Admission AI voice."
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Info & Meta Compliance */}
        <div className="space-y-6">
          <Card className="shadow-sm border-emerald-100 bg-emerald-50/30">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-bold flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-emerald-600" />
                Meta Enterprise Compliance
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs text-slate-700">
              <p className="leading-relaxed">
                WhatsApp templates comply with Meta Educational Guidelines and TRAI DND regulations.
              </p>
              <div className="rounded-lg bg-white p-3 border border-emerald-200 mt-2 space-y-1 font-mono text-[11px] text-slate-800">
                <p className="font-bold text-emerald-800">Sample Template:</p>
                <p>
                  &quot;Hello Rahul! Thank you for contacting ABC Institute Admissions. As requested, here is your 2026 B.Tech CSE Fee Structure brochure: abccollege.edu.in/btech-2026.pdf&quot;
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
