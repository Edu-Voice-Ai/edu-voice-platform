"use client";

import React, { useState } from "react";
import {
  Phone,
  Plus,
  CheckCircle2,
  PhoneCall,
  Sparkles,
  Shield,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useDataStore } from "@/hooks/useDataStore";

export default function PhoneNumbersPage() {
  const { phoneNumbers, agent } = useDataStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [testCallNumber, setTestCallNumber] = useState<string | null>(null);

  const handleTestCall = (num: string) => {
    setTestCallNumber(num);
    setTimeout(() => {
      setTestCallNumber(null);
    }, 2500);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Phone className="h-6 w-6 text-indigo-600" />
            Indian Virtual Phone Numbers
          </h1>
          <p className="text-xs text-muted-foreground">
            Manage your dedicated Indian inbound telephone numbers connected to Admission AI.
          </p>
        </div>

        <Button
          size="sm"
          variant="gradient"
          onClick={() => setIsModalOpen(true)}
          className="text-xs font-bold shadow-md"
        >
          <Plus className="h-3.5 w-3.5 mr-1" /> Provision Virtual Number
        </Button>
      </div>

      {testCallNumber && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs font-bold text-emerald-900 flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <PhoneCall className="h-4 w-4 text-emerald-600 animate-pulse" />
            <span>Simulating live inbound call routing to {agent.name}...</span>
          </div>
          <Badge variant="success">Active Test</Badge>
        </div>
      )}

      {/* Phone Number Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {phoneNumbers.map((num) => (
          <Card key={num.id} className="shadow-sm border-slate-200 bg-white overflow-hidden">
            <div className="border-b border-slate-100 p-5 bg-slate-50/60 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
                  <Phone className="h-5 w-5" />
                </div>
                <div>
                  <span className="font-mono text-lg font-bold text-slate-900">
                    {num.formattedNumber}
                  </span>
                  <p className="text-[10px] text-muted-foreground">
                    Telephony Provider: {num.provider}
                  </p>
                </div>
              </div>

              <Badge
                variant={num.status === "active" ? "success" : "warning"}
                className="text-xs capitalize"
              >
                {num.status}
              </Badge>
            </div>

            <CardContent className="p-5 space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-slate-50 p-3 border border-slate-200">
                  <span className="text-slate-500 block text-[10px]">Connected Agent</span>
                  <span className="font-bold text-slate-900">{num.assignedAgentName}</span>
                </div>

                <div className="rounded-xl bg-slate-50 p-3 border border-slate-200">
                  <span className="text-slate-500 block text-[10px]">Human Fallback</span>
                  <span className="font-mono font-bold text-slate-900">{num.fallbackNumber}</span>
                </div>
              </div>

              <div className="flex items-center justify-between text-slate-600 pt-2 border-t border-slate-100">
                <span>Inbound Calls Served: <strong className="font-mono text-slate-900">{num.totalCallsHandled.toLocaleString("en-IN")}</strong></span>
                <span>Monthly Rental: <strong className="font-mono text-slate-900">₹{num.monthlyRentalINR.toLocaleString("en-IN")}/mo</strong></span>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleTestCall(num.number)}
                  className="text-xs font-semibold"
                >
                  <PhoneCall className="h-3 w-3 mr-1 text-indigo-600" />
                  Test Routing
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Provision Number Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Provision Dedicated Indian Virtual Number"
        description="Select city prefix and allocate an active inbound line for your campus."
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-700">Select City / Area Code</label>
            <Select defaultValue="80">
              <option value="80">Bengaluru / Karnataka (+91 80)</option>
              <option value="40">Hyderabad / Telangana (+91 40)</option>
              <option value="11">Delhi NCR (+91 11)</option>
              <option value="22">Mumbai / Maharashtra (+91 22)</option>
              <option value="44">Chennai / Tamil Nadu (+91 44)</option>
              <option value="1800">All-India Toll Free (1800 XXX XXX)</option>
            </Select>
          </div>

          <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 p-4 text-xs text-indigo-950 space-y-1">
            <p className="font-bold">Telephony Compliance Note:</p>
            <p className="text-[11px] text-indigo-800">
              Indian virtual cloud numbers are configured with low-latency SIP trunks routing directly to Admission AI with carrier-grade human escalation fallback.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="gradient"
              size="sm"
              onClick={() => setIsModalOpen(false)}
              className="font-bold"
            >
              Confirm & Allocate Line
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
