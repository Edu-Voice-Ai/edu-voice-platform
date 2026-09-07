"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Bot,
  BookOpen,
  PhoneCall,
  Users,
  CalendarClock,
  BarChart3,
  Phone,
  MessageSquare,
  CreditCard,
  Settings,
  Sparkles,
  ChevronRight,
  GraduationCap,
} from "lucide-react";
import { useDataStore } from "@/hooks/useDataStore";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface NavItem {
  name: string;
  href: string;
  icon: React.ElementType;
  badge?: string | number;
  badgeVariant?: "default" | "success" | "warning" | "indigo" | "teal";
  role?: "all" | "admin";
}

export function Sidebar({ className }: { className?: string }) {
  const pathname = usePathname();
  const { organization, agent, leads, followUps } = useDataStore();
  const { user } = useAuth();

  const pendingCallbacks = leads.filter(
    (l) => l.status === "Callback Requested" || l.callbackRequested
  ).length;

  const dueFollowUps = followUps.filter((f) => f.status === "pending").length;

  const navItems: NavItem[] = [
    {
      name: "Dashboard",
      href: "/dashboard",
      icon: LayoutDashboard,
    },
    {
      name: "Admission AI",
      href: "/agents",
      icon: Bot,
      badge: agent.status === "active" ? "Live" : "Paused",
      badgeVariant: agent.status === "active" ? "success" : "warning",
    },
    {
      name: "Knowledge Base",
      href: "/knowledge",
      icon: BookOpen,
    },
    {
      name: "Calls & Recordings",
      href: "/calls",
      icon: PhoneCall,
    },
    {
      name: "Admission Leads",
      href: "/leads",
      icon: Users,
      badge: pendingCallbacks > 0 ? pendingCallbacks : undefined,
      badgeVariant: "indigo",
    },
    {
      name: "Follow-ups & Queue",
      href: "/follow-ups",
      icon: CalendarClock,
      badge: dueFollowUps > 0 ? dueFollowUps : undefined,
      badgeVariant: "warning",
    },
    {
      name: "Analytics",
      href: "/analytics",
      icon: BarChart3,
    },
    {
      name: "Phone Numbers",
      href: "/phone-numbers",
      icon: Phone,
    },
    {
      name: "WhatsApp Business",
      href: "/whatsapp",
      icon: MessageSquare,
      badge: "V1",
      badgeVariant: "teal",
    },
    {
      name: "Billing & Plans",
      href: "/billing",
      icon: CreditCard,
      role: "admin",
    },
    {
      name: "Settings",
      href: "/settings",
      icon: Settings,
      role: "admin",
    },
  ];

  return (
    <aside
      className={cn(
        "flex h-screen w-64 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 select-none",
        className
      )}
    >
      {/* Brand Header */}
      <div className="flex h-16 items-center gap-3 border-b border-slate-100 px-5 dark:border-slate-800">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/30">
          <GraduationCap className="h-5 w-5" />
        </div>
        <div className="flex flex-col">
          <span className="text-base font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-1.5">
            Edu-Voice-AI
            <span className="rounded bg-indigo-100 px-1.5 py-0.2 text-[9px] font-bold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              V1
            </span>
          </span>
          <span className="text-[11px] text-muted-foreground truncate max-w-[140px]">
            {organization.name}
          </span>
        </div>
      </div>

      {/* Interactive AI Tester CTA */}
      <div className="p-3">
        <Link
          href="/agents/test"
          className="flex items-center justify-between rounded-xl bg-gradient-to-r from-indigo-600/10 via-violet-600/10 to-purple-600/10 p-3 border border-indigo-200/60 dark:border-indigo-800/60 hover:border-indigo-400 transition-all group"
        >
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-sm shadow-indigo-500/30">
              <Sparkles className="h-4 w-4 animate-pulse" />
            </div>
            <div>
              <p className="text-xs font-bold text-indigo-950 dark:text-indigo-200">
                Test Admission AI
              </p>
              <p className="text-[10px] text-indigo-600 dark:text-indigo-400">
                Voice & Text Simulator
              </p>
            </div>
          </div>
          <ChevronRight className="h-4 w-4 text-indigo-400 group-hover:translate-x-0.5 transition-transform" />
        </Link>
      </div>

      {/* Navigation List */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
        <p className="px-3 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
          Core Platform
        </p>
        {navItems.map((item) => {
          if (item.role === "admin" && user?.role !== "admin") return null;

          const isActive =
            pathname === item.href ||
            (item.href !== "/dashboard" && pathname.startsWith(item.href));

          const Icon = item.icon;

          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center justify-between rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-150 group",
                isActive
                  ? "bg-indigo-50 text-indigo-700 shadow-sm dark:bg-indigo-950/60 dark:text-indigo-300"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200"
              )}
            >
              <div className="flex items-center gap-3">
                <Icon
                  className={cn(
                    "h-4 w-4 transition-colors",
                    isActive
                      ? "text-indigo-600 dark:text-indigo-400"
                      : "text-slate-400 group-hover:text-slate-600 dark:group-hover:text-slate-300"
                  )}
                />
                <span>{item.name}</span>
              </div>
              {item.badge && (
                <Badge
                  variant={item.badgeVariant || "default"}
                  className="text-[10px] px-1.5 py-0"
                >
                  {item.badge}
                </Badge>
              )}
            </Link>
          );
        })}
      </div>

      {/* Tenant & Status Footer */}
      <div className="border-t border-slate-100 p-3 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40">
        <div className="flex items-center justify-between px-2 py-1">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
            </span>
            <span className="text-[11px] font-medium text-slate-600 dark:text-slate-400">
              Demo AI Inbound Simulator
            </span>
          </div>
          <span className="text-[10px] font-mono font-medium text-slate-500">
            Demo Line
          </span>
        </div>
      </div>
    </aside>
  );
}
