"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Bell,
  Sparkles,
  Phone,
  Shield,
  UserCheck,
  ChevronDown,
  LogOut,
  Building,
  Menu,
  Languages,
} from "lucide-react";
import { useDataStore } from "@/hooks/useDataStore";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function Header({ onMobileMenuToggle }: { onMobileMenuToggle?: () => void }) {
  const { organization, agent, phoneNumbers } = useDataStore();
  const { user, switchRole, logout } = useAuth();
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  const [showNotification, setShowNotification] = useState(false);

  const activeNumber = phoneNumbers.find((p) => p.status === "active");

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95 sm:px-6">
      {/* Left side: Mobile trigger & Active Institution badge */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMobileMenuToggle}
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 md:hidden dark:hover:bg-slate-800"
        >
          <Menu className="h-5 w-5" />
          <span className="sr-only">Toggle Menu</span>
        </button>

        <div className="hidden sm:flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
            <Building className="h-4 w-4" />
          </div>
          <div>
            <p className="text-xs font-bold text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
              {organization.name}
              <Badge variant="outline" className="text-[10px] py-0 px-1 font-mono uppercase">
                {organization.type}
              </Badge>
            </p>
            <p className="text-[11px] text-muted-foreground flex items-center gap-1">
              <span>{organization.city}, {organization.state}</span>
              <span>•</span>
              <span className="text-indigo-600 dark:text-indigo-400 font-medium">Demo Environment</span>
            </p>
          </div>
        </div>
      </div>

      {/* Right side: Live status, Languages, Test AI button, Role Switcher */}
      <div className="flex items-center gap-3">
        {/* Active Indian Phone Number Pill */}
        {activeNumber && (
          <div className="hidden lg:flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50/70 px-3 py-1 text-xs text-indigo-800 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-300">
            <Phone className="h-3 w-3 text-indigo-600" />
            <span className="font-mono font-semibold">Demo Line: {activeNumber.formattedNumber}</span>
          </div>
        )}

        {/* Languages Supported */}
        <div className="hidden xl:flex items-center gap-1.5 text-xs text-slate-500 bg-slate-100 px-2.5 py-1 rounded-lg dark:bg-slate-800">
          <Languages className="h-3.5 w-3.5 text-indigo-500" />
          <span className="font-semibold text-slate-700 dark:text-slate-300">EN</span>
          <span>•</span>
          <span className="font-semibold text-slate-700 dark:text-slate-300">हिन्दी</span>
          <span>•</span>
          <span className="font-semibold text-slate-700 dark:text-slate-300">తెలుగు</span>
        </div>

        {/* Quick Test AI Button */}
        <Link href="/agents/test">
          <Button
            size="sm"
            variant="gradient"
            className="flex items-center gap-1.5 shadow-sm text-xs font-semibold"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Test AI Counsellor</span>
            <span className="sm:hidden">Test AI</span>
          </Button>
        </Link>

        {/* Role Demo Switcher Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowRoleDropdown(!showRoleDropdown)}
            className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
          >
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600 text-[10px] text-white">
              {user?.role === "admin" ? "AD" : "CN"}
            </div>
            <span className="hidden md:inline">
              {user?.role === "admin" ? "Admin Mode" : "Counsellor Mode"}
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
          </button>

          {showRoleDropdown && (
            <div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-800 dark:bg-slate-900 animate-in fade-in zoom-in-95">
              <p className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Demo Persona Switcher
              </p>
              <button
                onClick={() => {
                  switchRole("admin");
                  setShowRoleDropdown(false);
                }}
                className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-xs font-semibold transition-colors ${
                  user?.role === "admin"
                    ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                    : "text-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800"
                }`}
              >
                <div className="flex items-center gap-2">
                  <Shield className="h-4 w-4 text-indigo-600" />
                  <div className="text-left">
                    <p className="font-bold">Dr. K. S. Rao</p>
                    <p className="text-[10px] text-muted-foreground">Institute Admin / Principal</p>
                  </div>
                </div>
                {user?.role === "admin" && <Badge variant="indigo" className="text-[9px]">Active</Badge>}
              </button>

              <button
                onClick={() => {
                  switchRole("counsellor");
                  setShowRoleDropdown(false);
                }}
                className={`mt-1 flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-xs font-semibold transition-colors ${
                  user?.role === "counsellor"
                    ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                    : "text-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800"
                }`}
              >
                <div className="flex items-center gap-2">
                  <UserCheck className="h-4 w-4 text-emerald-600" />
                  <div className="text-left">
                    <p className="font-bold">S. K. Murthy</p>
                    <p className="text-[10px] text-muted-foreground">Senior Admission Counsellor</p>
                  </div>
                </div>
                {user?.role === "counsellor" && <Badge variant="indigo" className="text-[9px]">Active</Badge>}
              </button>

              <div className="my-1 border-t border-slate-100 dark:border-slate-800" />
              <Link
                href="/login"
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span>Log Out</span>
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
