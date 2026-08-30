"use client";

import React, { useState } from "react";
import {
  CalendarClock,
  CheckCircle2,
  Clock,
  Phone,
  Plus,
  AlertCircle,
  ChevronRight,
  UserCheck,
  Calendar,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useDataStore } from "@/hooks/useDataStore";
import { FollowUpItem } from "@/types";
import { formatRelativeDate } from "@/lib/utils";

export default function FollowUpsPage() {
  const { followUps, updateFollowUpStatus, addFollowUp } = useDataStore();
  const [activeTab, setActiveTab] = useState<"pending" | "completed">("pending");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [callingStudent, setCallingStudent] = useState<string | null>(null);

  // Form state
  const [studentName, setStudentName] = useState("");
  const [phone, setPhone] = useState("");
  const [course, setCourse] = useState("B.Tech Computer Science & Engineering (CSE)");
  const [scheduledFor, setScheduledFor] = useState("");
  const [priority, setPriority] = useState<"high" | "medium" | "low">("high");
  const [notes, setNotes] = useState("");

  const filteredItems = followUps.filter((f) =>
    activeTab === "pending" ? f.status === "pending" || f.status === "overdue" : f.status === "completed"
  );

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!studentName || !phone) return;
    addFollowUp({
      leadId: `lead_${Date.now()}`,
      studentName,
      phone,
      courseInterested: course,
      scheduledFor: scheduledFor || new Date().toISOString(),
      status: "pending",
      priority,
      assignedTo: "Dr. K. S. Rao",
      notes,
    });
    setStudentName("");
    setPhone("");
    setNotes("");
    setIsModalOpen(false);
  };

  const handleTriggerDial = (name: string) => {
    setCallingStudent(name);
    setTimeout(() => {
      setCallingStudent(null);
    }, 2500);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <CalendarClock className="h-6 w-6 text-indigo-600" />
            Counsellor Follow-up & Callback Queue
          </h1>
          <p className="text-xs text-muted-foreground">
            Scheduled prospective student callbacks captured automatically by your Admission AI.
          </p>
        </div>

        <Button
          size="sm"
          variant="gradient"
          onClick={() => setIsModalOpen(true)}
          className="text-xs font-bold shadow-md"
        >
          <Plus className="h-3.5 w-3.5 mr-1" /> Schedule Callback
        </Button>
      </div>

      {callingStudent && (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-xs font-bold text-indigo-950 flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <Phone className="h-4 w-4 text-indigo-600 animate-pulse" />
            <span>Initiating Outbound Counsellor Call to {callingStudent}...</span>
          </div>
          <Badge variant="indigo">Connecting</Badge>
        </div>
      )}

      {/* Tabs */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("pending")}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all ${
                activeTab === "pending"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              Due & Pending Callbacks (
              {followUps.filter((f) => f.status === "pending").length}
              )
            </button>
            <button
              onClick={() => setActiveTab("completed")}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all ${
                activeTab === "completed"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              Completed Callbacks (
              {followUps.filter((f) => f.status === "completed").length}
              )
            </button>
          </div>
        </CardHeader>

        <CardContent className="p-6 space-y-3">
          {filteredItems.length === 0 ? (
            <div className="text-center py-12 text-xs text-muted-foreground">
              No callbacks in this queue.
            </div>
          ) : (
            filteredItems.map((item) => (
              <div
                key={item.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 hover:border-indigo-200 transition-all"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <p className="text-xs font-bold text-slate-900 dark:text-slate-100">
                      {item.studentName}
                    </p>
                    <Badge
                      variant={item.priority === "high" ? "destructive" : "indigo"}
                      className="text-[9px]"
                    >
                      {item.priority.toUpperCase()} PRIORITY
                    </Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    {item.courseInterested} • Phone: <span className="font-mono font-semibold text-slate-700">{item.phone}</span>
                  </p>
                  <p className="text-[11px] text-slate-700 dark:text-slate-300">
                    <span className="font-semibold">Notes:</span> {item.notes}
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleTriggerDial(item.studentName)}
                    className="h-8 text-xs font-semibold"
                  >
                    <Phone className="h-3 w-3 mr-1 text-emerald-600" /> Call Student
                  </Button>

                  {item.status === "pending" ? (
                    <Button
                      size="sm"
                      variant="gradient"
                      onClick={() => updateFollowUpStatus(item.id, "completed")}
                      className="h-8 text-xs font-bold"
                    >
                      <CheckCircle2 className="h-3 w-3 mr-1" /> Mark Done
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => updateFollowUpStatus(item.id, "pending")}
                      className="h-8 text-xs font-medium"
                    >
                      Reopen
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Schedule Callback Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Schedule Counsellor Follow-up"
        description="Add a prospective student callback task into the team queue."
      >
        <form onSubmit={handleCreateSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-700">Student Name</label>
              <Input
                value={studentName}
                onChange={(e) => setStudentName(e.target.value)}
                placeholder="e.g. Ramesh Reddy"
                required
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Phone Number</label>
              <Input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91 98480 11223"
                required
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Target Course</label>
            <Select value={course} onChange={(e) => setCourse(e.target.value)}>
              <option value="B.Tech Computer Science & Engineering (CSE)">B.Tech CSE</option>
              <option value="B.Tech Electronics & Communication (ECE)">B.Tech ECE</option>
              <option value="Master of Business Administration (MBA)">MBA</option>
            </Select>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Counsellor Brief / Notes</label>
            <Textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Call to discuss hostel availability and management quota token..."
              required
            />
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
            <Button type="submit" variant="gradient" size="sm" className="font-bold">
              Schedule Callback
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
