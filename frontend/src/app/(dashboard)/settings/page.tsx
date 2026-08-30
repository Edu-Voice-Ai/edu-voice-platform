"use client";

import React, { useState } from "react";
import {
  Settings,
  Building,
  Users,
  Shield,
  Bell,
  Key,
  Save,
  CheckCircle2,
  Plus,
  Trash2,
  Lock,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { useDataStore } from "@/hooks/useDataStore";
import { useAuth } from "@/hooks/useAuth";
import { Organization } from "@/types";

export default function SettingsPage() {
  const { organization, updateOrganization } = useDataStore();
  const { user } = useAuth();
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [activeTab, setActiveTab] = useState<"profile" | "team" | "security" | "notifications">("profile");

  // Add staff modal state
  const [isAddStaffModalOpen, setIsAddStaffModalOpen] = useState(false);
  const [newStaffName, setNewStaffName] = useState("");
  const [newStaffEmail, setNewStaffEmail] = useState("");
  const [newStaffRole, setNewStaffRole] = useState<"counsellor" | "staff">("counsellor");

  const [staffList, setStaffList] = useState([
    {
      id: "usr_001",
      name: "Dr. K. S. Rao",
      email: "admissions@abccollege.edu.in",
      role: "admin",
      title: "Principal & Chief Administrator",
    },
    {
      id: "usr_002",
      name: "S. K. Murthy",
      email: "counsellor.murthy@abccollege.edu.in",
      role: "counsellor",
      title: "Senior Admission Counsellor",
    },
  ]);

  const handleSaveProfile = (e: React.FormEvent) => {
    e.preventDefault();
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  const handleAddStaff = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStaffName || !newStaffEmail) return;
    setStaffList((prev) => [
      ...prev,
      {
        id: `usr_${Date.now()}`,
        name: newStaffName,
        email: newStaffEmail,
        role: newStaffRole,
        title: newStaffRole === "counsellor" ? "Admission Counsellor" : "Support Staff",
      },
    ]);
    setNewStaffName("");
    setNewStaffEmail("");
    setIsAddStaffModalOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Settings className="h-6 w-6 text-indigo-600" />
            Institution Settings & Team RBAC
          </h1>
          <p className="text-xs text-muted-foreground">
            Manage organization credentials, counsellor permissions, and security controls.
          </p>
        </div>
      </div>

      {savedSuccess && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-emerald-800 font-semibold flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          Settings updated successfully.
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-200 pb-3">
        {[
          { id: "profile", label: "Institution Profile", icon: Building },
          { id: "team", label: "Team & Permissions", icon: Users },
          { id: "security", label: "Tenant Security", icon: Shield },
          { id: "notifications", label: "Notifications", icon: Bell },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as "profile" | "team" | "security" | "notifications")}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-all ${
                isActive
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Profile Form */}
      {activeTab === "profile" && (
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold">Institution Profile</CardTitle>
            <CardDescription className="text-xs">
              Official campus contact details used in voice AI greetings and notifications
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSaveProfile} className="space-y-4 max-w-2xl">
              <div>
                <label className="text-xs font-semibold text-slate-700">Institution Name</label>
                <Input
                  value={organization.name}
                  onChange={(e) => updateOrganization({ name: e.target.value })}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-semibold text-slate-700">Category / Type</label>
                  <Select
                    value={organization.type}
                    onChange={(e) =>
                      updateOrganization({
                        type: e.target.value as Organization["type"],
                      })
                    }
                  >
                    <option value="college">Autonomous / Affiliated College</option>
                    <option value="university">University</option>
                    <option value="coaching">Coaching / Exam Prep</option>
                    <option value="training">Training Institute</option>
                    <option value="school">School</option>
                  </Select>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700">Tagline</label>
                  <Input
                    value={organization.tagline}
                    onChange={(e) => updateOrganization({ tagline: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-semibold text-slate-700">City</label>
                  <Input
                    value={organization.city}
                    onChange={(e) => updateOrganization({ city: e.target.value })}
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700">State</label>
                  <Input
                    value={organization.state}
                    onChange={(e) => updateOrganization({ state: e.target.value })}
                  />
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <Button type="submit" variant="gradient" size="sm" className="font-bold text-xs">
                  <Save className="h-3.5 w-3.5 mr-1" /> Save Profile
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Team & Permissions */}
      {activeTab === "team" && (
        <Card className="shadow-sm">
          <CardHeader className="pb-3 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base font-bold">Staff & Counsellors</CardTitle>
              <CardDescription className="text-xs">
                Role-based access control for administrative staff and admission counsellors
              </CardDescription>
            </div>
            <Button
              size="sm"
              variant="gradient"
              onClick={() => setIsAddStaffModalOpen(true)}
              className="text-xs font-bold shadow-md"
            >
              <Plus className="h-3.5 w-3.5 mr-1" /> Add Staff Member
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            {staffList.map((member) => (
              <div
                key={member.id}
                className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700 font-bold text-xs">
                    {member.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-xs font-bold text-slate-900">{member.name}</p>
                      <Badge
                        variant={member.role === "admin" ? "indigo" : "success"}
                        className="text-[9px] uppercase font-mono"
                      >
                        {member.role}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground">{member.email} • {member.title}</p>
                  </div>
                </div>

                <Badge variant="outline" className="text-xs">
                  Active
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Security & Tenant Isolation */}
      {activeTab === "security" && (
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold">Tenant Isolation & Data Protection</CardTitle>
            <CardDescription className="text-xs">
              Organization isolation boundaries and cryptographic protection
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 max-w-2xl text-xs text-slate-700 leading-relaxed">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2">
              <div className="flex justify-between">
                <span className="font-semibold text-slate-900">Tenant Organization ID</span>
                <span className="font-mono text-indigo-700 font-bold">{organization.id}</span>
              </div>
              <p className="text-[11px] text-muted-foreground">
                All phone recordings, leads, vector chunks, and configuration records are strictly scoped to this organization ID with Supabase Row Level Security (RLS).
              </p>
            </div>

            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 space-y-1 text-emerald-950">
              <div className="flex items-center gap-2 font-bold">
                <Lock className="h-4 w-4 text-emerald-600" />
                Zero-Browser Credential Guarantee
              </div>
              <p className="text-[11px] text-emerald-800">
                Third-party provider keys (Groq, ElevenLabs, Exotel, Supabase service-role) are never exposed to browser clients.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Notifications */}
      {activeTab === "notifications" && (
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-bold">Alert & Dispatch Preferences</CardTitle>
            <CardDescription className="text-xs">
              Real-time notifications for new leads and human escalation transfers
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 max-w-xl">
            <Switch
              checked={true}
              onCheckedChange={() => {}}
              label="SMS Alert on High-Interest Lead Capture"
              description="Notify counsellors immediately when a student with 80%+ marks requests admission callback."
            />
            <div className="border-t border-slate-100 my-2" />
            <Switch
              checked={true}
              onCheckedChange={() => {}}
              label="Instant Live Transfer Ring"
              description="Forward calls to senior staff phone number when complex questions or fee concessions arise."
            />
          </CardContent>
        </Card>
      )}

      {/* Add Staff Modal */}
      <Modal
        isOpen={isAddStaffModalOpen}
        onClose={() => setIsAddStaffModalOpen(false)}
        title="Add Staff Counsellor"
        description="Invite a team member to manage admission leads and human callbacks."
      >
        <form onSubmit={handleAddStaff} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-700">Full Name</label>
            <Input
              value={newStaffName}
              onChange={(e) => setNewStaffName(e.target.value)}
              placeholder="e.g. Ramesh Reddy"
              required
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Official Email</label>
            <Input
              type="email"
              value={newStaffEmail}
              onChange={(e) => setNewStaffEmail(e.target.value)}
              placeholder="counsellor@college.edu.in"
              required
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700">Role & Access Level</label>
            <Select
              value={newStaffRole}
              onChange={(e) => setNewStaffRole(e.target.value as "counsellor" | "staff")}
            >
              <option value="counsellor">Admission Counsellor (Leads, Calls, Callbacks)</option>
              <option value="staff">Administrative Staff (View Only)</option>
            </Select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsAddStaffModalOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" variant="gradient" size="sm" className="font-bold">
              Send Invitation
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
