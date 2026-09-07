"use client";

import React, { useState } from "react";
import {
  Users,
  Search,
  Filter,
  Phone,
  Mail,
  Clock,
  Plus,
  ChevronRight,
  MessageSquare,
  Calendar,
  CheckCircle2,
  UserCheck,
  GraduationCap,
  Sparkles,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Drawer } from "@/components/ui/drawer";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useDataStore } from "@/hooks/useDataStore";
import { LeadRecord, LeadStatus } from "@/types";
import { formatRelativeDate } from "@/lib/utils";

const LEAD_STATUSES: LeadStatus[] = [
  "New",
  "Interested",
  "Highly Interested",
  "Follow-up Required",
  "Callback Requested",
  "Converted",
  "Not Interested",
  "Lost",
];

export default function LeadsPage() {
  const { leads, updateLeadStatus, addLeadNote, createLead, calls } = useDataStore();
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [courseFilter, setCourseFilter] = useState<string>("all");
  const [selectedLead, setSelectedLead] = useState<LeadRecord | null>(null);

  // New Note state
  const [newNoteContent, setNewNoteContent] = useState("");

  // Create Lead Modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newLeadForm, setNewLeadForm] = useState({
    studentName: "",
    phone: "",
    email: "",
    courseInterested: "B.Tech Computer Science & Engineering (CSE)",
    currentQualification: "Intermediate MPC (10+2)",
    status: "New" as LeadStatus,
    callbackRequested: true,
    preferredCallbackTime: "Tomorrow afternoon",
    assignedCounsellor: "Dr. K. S. Rao",
  });

  const filteredLeads = leads.filter((lead) => {
    const matchesSearch =
      lead.studentName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      lead.phone.includes(searchQuery) ||
      lead.courseInterested.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "all" || lead.status === statusFilter;
    const matchesCourse = courseFilter === "all" || lead.courseInterested.includes(courseFilter);
    return matchesSearch && matchesStatus && matchesCourse;
  });

  const handleAddNote = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedLead || !newNoteContent.trim()) return;
    addLeadNote(selectedLead.id, "Dr. K. S. Rao", newNoteContent);
    setNewNoteContent("");
    // Refresh local selectedLead
    const updated = leads.find((l) => l.id === selectedLead.id);
    if (updated) setSelectedLead(updated);
  };

  const handleCreateLeadSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newLeadForm.studentName || !newLeadForm.phone) return;
    createLead({
      ...newLeadForm,
      notes: [
        {
          id: `note_${Date.now()}`,
          author: "Manual Entry",
          content: "Lead created by admission staff.",
          createdAt: new Date().toISOString(),
        },
      ],
    });
    setIsCreateModalOpen(false);
  };

  const getStatusBadgeVariant = (status: LeadStatus) => {
    switch (status) {
      case "Highly Interested":
      case "Converted":
        return "success";
      case "Interested":
      case "New":
        return "indigo";
      case "Callback Requested":
      case "Follow-up Required":
        return "warning";
      case "Lost":
      case "Not Interested":
        return "destructive";
      default:
        return "secondary";
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Users className="h-6 w-6 text-indigo-600" />
            Admission Lead Management & CRM
          </h1>
          <p className="text-xs text-muted-foreground">
            Auto-qualified student leads extracted from inbound voice enquiries with counsellor callback tracking.
          </p>
        </div>

        <Button
          size="sm"
          variant="gradient"
          onClick={() => setIsCreateModalOpen(true)}
          className="text-xs font-bold shadow-md"
        >
          <Plus className="h-3.5 w-3.5 mr-1" /> Add Direct Lead
        </Button>
      </div>

      {/* Filter Toolbar */}
      <Card className="shadow-sm">
        <CardContent className="p-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="w-full sm:w-80">
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by student name, phone, course..."
              leftIcon={<Search className="h-3.5 w-3.5" />}
              className="h-9 text-xs"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-9 text-xs w-44"
            >
              <option value="all">All Lead Statuses</option>
              {LEAD_STATUSES.map((st) => (
                <option key={st} value={st}>
                  {st}
                </option>
              ))}
            </Select>

            <Select
              value={courseFilter}
              onChange={(e) => setCourseFilter(e.target.value)}
              className="h-9 text-xs w-36"
            >
              <option value="all">All Courses</option>
              <option value="CSE">B.Tech CSE</option>
              <option value="AI&ML">B.Tech AI&ML</option>
              <option value="ECE">B.Tech ECE</option>
              <option value="MBA">MBA</option>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Leads Table */}
      <Card className="shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50/80 text-slate-500 font-semibold uppercase tracking-wider dark:border-slate-800 dark:bg-slate-900/60">
              <tr>
                <th className="px-5 py-3.5">Student Name</th>
                <th className="px-5 py-3.5">Course Interested</th>
                <th className="px-5 py-3.5">Qualification</th>
                <th className="px-5 py-3.5">Status</th>
                <th className="px-5 py-3.5">Callback Time</th>
                <th className="px-5 py-3.5">Assigned To</th>
                <th className="px-5 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-medium">
              {filteredLeads.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-muted-foreground">
                    No leads found matching criteria.
                  </td>
                </tr>
              ) : (
                filteredLeads.map((lead) => (
                  <tr
                    key={lead.id}
                    onClick={() => setSelectedLead(lead)}
                    className="hover:bg-indigo-50/40 dark:hover:bg-slate-800/40 transition-colors cursor-pointer"
                  >
                    <td className="px-5 py-3.5">
                      <div>
                        <p className="font-bold text-slate-900 dark:text-slate-100">
                          {lead.studentName}
                        </p>
                        <p className="text-[11px] font-mono text-muted-foreground">{lead.phone}</p>
                      </div>
                    </td>

                    <td className="px-5 py-3.5 font-semibold text-slate-800 dark:text-slate-200">
                      {lead.courseInterested}
                    </td>

                    <td className="px-5 py-3.5 text-slate-600 dark:text-slate-400">
                      {lead.currentQualification}
                    </td>

                    <td className="px-5 py-3.5">
                      <Badge variant={getStatusBadgeVariant(lead.status)} className="text-[10px]">
                        {lead.status}
                      </Badge>
                    </td>

                    <td className="px-5 py-3.5 text-slate-600">
                      {lead.preferredCallbackTime || "—"}
                    </td>

                    <td className="px-5 py-3.5 text-slate-700 dark:text-slate-300">
                      {lead.assignedCounsellor || "Unassigned"}
                    </td>

                    <td className="px-5 py-3.5 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs text-indigo-600 font-semibold"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedLead(lead);
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

      {/* Lead Details Drawer */}
      {selectedLead && (
        <Drawer
          isOpen={!!selectedLead}
          onClose={() => setSelectedLead(null)}
          title={selectedLead.studentName}
          description={`Phone: ${selectedLead.phone} • Added ${formatRelativeDate(selectedLead.createdAt)}`}
          width="lg"
        >
          <div className="space-y-6">
            {/* Status Switcher Bar */}
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-4 space-y-2">
              <label className="text-xs font-bold text-indigo-950">Update Lead Lifecycle Status</label>
              <div className="flex gap-2">
                <Select
                  value={selectedLead.status}
                  onChange={(e) => {
                    const nextStatus = e.target.value as LeadStatus;
                    updateLeadStatus(selectedLead.id, nextStatus);
                    setSelectedLead({ ...selectedLead, status: nextStatus });
                  }}
                  className="bg-white text-xs h-9"
                >
                  {LEAD_STATUSES.map((st) => (
                    <option key={st} value={st}>
                      {st}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            {/* Structured Prospect Profile */}
            <div className="space-y-3">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Prospect Profile
              </p>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="rounded-xl bg-slate-50 p-3 border border-slate-200">
                  <span className="text-slate-500 block text-[10px]">Target Program</span>
                  <span className="font-bold text-slate-900">{selectedLead.courseInterested}</span>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 border border-slate-200">
                  <span className="text-slate-500 block text-[10px]">Academic Record</span>
                  <span className="font-bold text-slate-900">{selectedLead.currentQualification}</span>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 border border-slate-200">
                  <span className="text-slate-500 block text-[10px]">Preferred Callback Time</span>
                  <span className="font-bold text-slate-900">{selectedLead.preferredCallbackTime || "None"}</span>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 border border-slate-200">
                  <span className="text-slate-500 block text-[10px]">Assigned Counsellor</span>
                  <span className="font-bold text-slate-900">{selectedLead.assignedCounsellor || "Dr. K. S. Rao"}</span>
                </div>
              </div>
            </div>

            {/* Counsellor Notes & Activity Log */}
            <div className="space-y-3">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Counsellor Notes & Activity History
              </p>

              {/* Add Note Form */}
              <form onSubmit={handleAddNote} className="space-y-2">
                <Textarea
                  rows={2}
                  value={newNoteContent}
                  onChange={(e) => setNewNoteContent(e.target.value)}
                  placeholder="Add counselling follow-up notes or admission status update..."
                  className="text-xs"
                />
                <div className="flex justify-end">
                  <Button type="submit" size="sm" variant="gradient" className="font-bold text-xs">
                    Post Note
                  </Button>
                </div>
              </form>

              {/* Notes Timeline */}
              <div className="space-y-2 pt-2">
                {selectedLead.notes.map((note) => (
                  <div
                    key={note.id}
                    className="rounded-xl border border-slate-200 bg-slate-50/60 p-3 space-y-1 text-xs"
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-bold text-slate-900">{note.author}</span>
                      <span className="text-slate-400 font-mono">
                        {formatRelativeDate(note.createdAt)}
                      </span>
                    </div>
                    <p className="text-slate-700 leading-relaxed">{note.content}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Drawer>
      )}

      {/* Manual Add Lead Modal */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Add Direct Admission Lead"
        description="Manually register a prospective student enquiry received in person or via web."
      >
        <form onSubmit={handleCreateLeadSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-700">Student Name</label>
              <Input
                value={newLeadForm.studentName}
                onChange={(e) =>
                  setNewLeadForm({ ...newLeadForm, studentName: e.target.value })
                }
                placeholder="e.g. Sneha Reddy"
                required
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Phone Number</label>
              <Input
                value={newLeadForm.phone}
                onChange={(e) => setNewLeadForm({ ...newLeadForm, phone: e.target.value })}
                placeholder="+91 94401 23456"
                required
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Target Course</label>
            <Select
              value={newLeadForm.courseInterested}
              onChange={(e) =>
                setNewLeadForm({ ...newLeadForm, courseInterested: e.target.value })
              }
            >
              <option value="B.Tech Computer Science & Engineering (CSE)">B.Tech CSE</option>
              <option value="B.Tech Artificial Intelligence & Machine Learning (AI&ML)">B.Tech AI&ML</option>
              <option value="B.Tech Electronics & Communication Engineering (ECE)">B.Tech ECE</option>
              <option value="Master of Business Administration (MBA)">MBA</option>
            </Select>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Current Academic Qualification</label>
            <Input
              value={newLeadForm.currentQualification}
              onChange={(e) =>
                setNewLeadForm({ ...newLeadForm, currentQualification: e.target.value })
              }
              placeholder="e.g. Intermediate MPC (92%)"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-700">Initial Status</label>
              <Select
                value={newLeadForm.status}
                onChange={(e) =>
                  setNewLeadForm({ ...newLeadForm, status: e.target.value as LeadStatus })
                }
              >
                {LEAD_STATUSES.map((st) => (
                  <option key={st} value={st}>
                    {st}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700">Preferred Callback Time</label>
              <Input
                value={newLeadForm.preferredCallbackTime}
                onChange={(e) =>
                  setNewLeadForm({ ...newLeadForm, preferredCallbackTime: e.target.value })
                }
                placeholder="Tomorrow afternoon"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsCreateModalOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" variant="gradient" size="sm" className="font-bold">
              Save Lead to CRM
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
