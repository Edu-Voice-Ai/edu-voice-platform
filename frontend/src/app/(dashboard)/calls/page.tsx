"use client";

import React, { useState } from "react";
import {
  PhoneCall,
  Search,
  Filter,
  Phone,
  Play,
  Pause,
  Clock,
  User,
  Bot,
  PhoneForwarded,
  Sparkles,
  ChevronRight,
  Download,
  Calendar,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Drawer } from "@/components/ui/drawer";
import { Select } from "@/components/ui/select";
import { useDataStore } from "@/hooks/useDataStore";
import { CallRecord, CallStatus } from "@/types";
import { formatDuration, formatRelativeDate } from "@/lib/utils";

export default function CallsPage() {
  const { calls } = useDataStore();
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedCall, setSelectedCall] = useState<CallRecord | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);

  const filteredCalls = calls.filter((c) => {
    const matchesSearch =
      c.callerNumber.includes(searchQuery) ||
      (c.callerName && c.callerName.toLowerCase().includes(searchQuery.toLowerCase())) ||
      c.aiSummary.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "all" || c.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <PhoneCall className="h-6 w-6 text-indigo-600" />
            Inbound Call History & Recordings
          </h1>
          <p className="text-xs text-muted-foreground">
            Complete call records, synchronized transcripts, AI summaries, and human handoff tracking.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="indigo" className="text-xs font-semibold py-1 px-3">
            {calls.length} Inbound Calls Tracked
          </Badge>
        </div>
      </div>

      {/* Filters Bar */}
      <Card className="shadow-sm">
        <CardContent className="p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="w-full sm:w-80">
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by caller, name, or keywords..."
              leftIcon={<Search className="h-3.5 w-3.5" />}
              className="h-9 text-xs"
            />
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-9 text-xs w-44"
            >
              <option value="all">All Call Outcomes</option>
              <option value="completed">AI Answered (Completed)</option>
              <option value="transferred">Transferred to Counsellor</option>
              <option value="missed">Missed / Abandoned</option>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Calls Table */}
      <Card className="shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50/80 text-slate-500 font-semibold uppercase tracking-wider dark:border-slate-800 dark:bg-slate-900/60">
              <tr>
                <th className="px-5 py-3.5">Caller / Student</th>
                <th className="px-5 py-3.5">Language</th>
                <th className="px-5 py-3.5">Duration</th>
                <th className="px-5 py-3.5">Outcome</th>
                <th className="px-5 py-3.5">AI Summary</th>
                <th className="px-5 py-3.5">Time</th>
                <th className="px-5 py-3.5 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-medium">
              {filteredCalls.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-muted-foreground">
                    No call records found matching criteria.
                  </td>
                </tr>
              ) : (
                filteredCalls.map((call) => (
                  <tr
                    key={call.id}
                    onClick={() => setSelectedCall(call)}
                    className="hover:bg-indigo-50/40 dark:hover:bg-slate-800/40 transition-colors cursor-pointer"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 font-bold text-[11px]">
                          {call.callerName ? call.callerName.slice(0, 2).toUpperCase() : "IN"}
                        </div>
                        <div>
                          <p className="font-bold text-slate-900 dark:text-slate-100">
                            {call.callerName || "Prospective Student"}
                          </p>
                          <p className="text-[11px] font-mono text-muted-foreground">
                            {call.callerNumber}
                          </p>
                        </div>
                      </div>
                    </td>

                    <td className="px-5 py-3.5">
                      <Badge variant="indigo" className="text-[9px] uppercase font-mono">
                        {call.primaryLanguage}
                      </Badge>
                    </td>

                    <td className="px-5 py-3.5 font-mono text-slate-700 dark:text-slate-300">
                      {formatDuration(call.durationSeconds)}
                    </td>

                    <td className="px-5 py-3.5">
                      <Badge
                        variant={call.status === "completed" ? "success" : "warning"}
                        className="text-[10px]"
                      >
                        {call.status === "completed" ? "AI Handled" : "Transferred"}
                      </Badge>
                    </td>

                    <td className="px-5 py-3.5 max-w-xs">
                      <p className="line-clamp-1 text-slate-600 dark:text-slate-400">
                        {call.aiSummary}
                      </p>
                    </td>

                    <td className="px-5 py-3.5 text-slate-500 whitespace-nowrap">
                      {formatRelativeDate(call.startedAt)}
                    </td>

                    <td className="px-5 py-3.5 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs text-indigo-600 font-semibold"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedCall(call);
                        }}
                      >
                        Details <ChevronRight className="ml-1 h-3 w-3" />
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Call Details & Transcript Drawer */}
      {selectedCall && (
        <Drawer
          isOpen={!!selectedCall}
          onClose={() => {
            setSelectedCall(null);
            setIsPlayingAudio(false);
          }}
          title="Inbound Call Record & Transcript"
          description={`Caller: ${selectedCall.callerName || selectedCall.callerNumber} • Handled by ${selectedCall.agentName}`}
          width="xl"
        >
          <div className="space-y-6">
            {/* Audio Waveform Player */}
            <div className="rounded-2xl border border-indigo-100 bg-indigo-50/70 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setIsPlayingAudio(!isPlayingAudio)}
                    className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-600 text-white shadow-md hover:bg-indigo-700 transition-transform active:scale-95"
                  >
                    {isPlayingAudio ? (
                      <Pause className="h-4 w-4" />
                    ) : (
                      <Play className="h-4 w-4 ml-0.5" />
                    )}
                  </button>
                  <div>
                    <p className="text-xs font-bold text-indigo-950">Call Audio Recording</p>
                    <p className="text-[10px] text-indigo-700 font-mono">
                      {isPlayingAudio ? "Playing... 01:14" : `00:00 / ${formatDuration(selectedCall.durationSeconds)}`}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Badge variant="indigo" className="text-[10px]">
                    {selectedCall.primaryLanguage.toUpperCase()}
                  </Badge>
                  <Button size="sm" variant="outline" className="h-7 text-[11px] bg-white">
                    <Download className="h-3 w-3 mr-1" /> Audio
                  </Button>
                </div>
              </div>

              {/* Waveform Visualizer */}
              <div className="flex items-center gap-1 h-9 px-3 bg-white/90 rounded-xl">
                {[14, 28, 36, 18, 32, 44, 22, 38, 48, 26, 20, 34, 46, 24, 18, 32, 40, 22, 30, 42, 16, 28, 36, 18].map(
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

            {/* AI Summary & Topics */}
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
                  AI Summary & Lead Qualification
                </span>
                {selectedCall.leadStatus && (
                  <Badge variant="indigo" className="text-[10px]">
                    {selectedCall.leadStatus}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-slate-800 leading-relaxed">{selectedCall.aiSummary}</p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {selectedCall.keyTopicsDiscussed.map((topic) => (
                  <span
                    key={topic}
                    className="rounded-md bg-white border border-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-700"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>

            {/* Human Transfer details if transferred */}
            {selectedCall.status === "transferred" && (
              <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 space-y-1 text-xs">
                <div className="flex items-center gap-2 font-bold text-amber-900">
                  <PhoneForwarded className="h-4 w-4 text-amber-600" />
                  Live Human Counsellor Transfer
                </div>
                <p className="text-amber-800">
                  Transferred to: <span className="font-semibold">{selectedCall.transferredTo}</span>
                </p>
                {selectedCall.transferReason && (
                  <p className="text-[11px] text-amber-700">Reason: {selectedCall.transferReason}</p>
                )}
              </div>
            )}

            {/* Synchronized Transcript */}
            <div className="space-y-3">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Synchronized Transcript
              </p>
              <div className="space-y-3">
                {selectedCall.transcript.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex items-start gap-3 text-xs leading-relaxed ${
                      msg.speaker === "ai"
                        ? "bg-indigo-50/70 border border-indigo-100 p-3.5 rounded-2xl rounded-tl-none text-indigo-950"
                        : msg.speaker === "human"
                        ? "bg-amber-50 border border-amber-200 p-3.5 rounded-2xl text-amber-950"
                        : "bg-slate-100 p-3.5 rounded-2xl rounded-tr-none text-slate-800"
                    }`}
                  >
                    <div className="shrink-0 font-bold">
                      {msg.speaker === "ai"
                        ? "AI Counsellor"
                        : msg.speaker === "human"
                        ? "Staff Counsellor"
                        : "Caller"}{" "}
                      <span className="font-mono text-[10px] text-muted-foreground font-normal">
                        ({msg.timestamp})
                      </span>
                      :
                    </div>
                    <p className="flex-1">{msg.text}</p>
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
