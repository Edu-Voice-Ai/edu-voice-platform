"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GraduationCap, Shield, UserCheck, Lock, Mail, ArrowRight, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("admissions@abccollege.edu.in");
  const [password, setPassword] = useState("password123");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError("Please fill in all credentials.");
      return;
    }
    setIsLoading(true);
    setError("");

    setTimeout(() => {
      login(email, email.includes("counsellor") ? "counsellor" : "admin");
      setIsLoading(false);
      router.push("/dashboard");
    }, 700);
  };

  const handleQuickFill = (role: "admin" | "counsellor") => {
    if (role === "admin") {
      setEmail("admissions@abccollege.edu.in");
      setPassword("adminpass2026");
    } else {
      setEmail("counsellor.murthy@abccollege.edu.in");
      setPassword("counsellorpass2026");
    }
    setError("");
  };

  return (
    <div className="min-h-screen flex flex-col justify-center items-center bg-slate-50 p-4 sm:p-6 lg:p-8">
      {/* Background Glow */}
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(35rem_35rem_at_center,theme(colors.indigo.100),theme(colors.slate.50))]" />

      <div className="w-full max-w-md space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <Link href="/" className="inline-flex items-center gap-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-600 text-white shadow-md">
              <GraduationCap className="h-6 w-6" />
            </div>
            <span className="text-xl font-extrabold tracking-tight text-slate-900">
              Edu-Voice-AI
            </span>
          </Link>
          <h1 className="text-2xl font-bold text-slate-900">Staff & Admin Sign In</h1>
          <p className="text-xs text-muted-foreground">
            Access your institution&apos;s Admission AI dashboard
          </p>
        </div>

        {/* Demo Quick Persona Selector */}
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50/70 p-3.5 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-indigo-950 flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-indigo-600" />
              Demo Quick Persona Fill
            </span>
            <Badge variant="indigo" className="text-[10px]">
              1-Click
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => handleQuickFill("admin")}
              className="flex items-center gap-2 rounded-xl bg-white p-2 text-left text-xs font-semibold text-slate-700 shadow-sm border border-indigo-100 hover:border-indigo-300 transition-all"
            >
              <Shield className="h-4 w-4 text-indigo-600 shrink-0" />
              <div>
                <p className="font-bold text-slate-900 leading-tight">Admin / Principal</p>
                <p className="text-[10px] text-muted-foreground">Dr. K. S. Rao</p>
              </div>
            </button>

            <button
              type="button"
              onClick={() => handleQuickFill("counsellor")}
              className="flex items-center gap-2 rounded-xl bg-white p-2 text-left text-xs font-semibold text-slate-700 shadow-sm border border-indigo-100 hover:border-indigo-300 transition-all"
            >
              <UserCheck className="h-4 w-4 text-emerald-600 shrink-0" />
              <div>
                <p className="font-bold text-slate-900 leading-tight">Lead Counsellor</p>
                <p className="text-[10px] text-muted-foreground">S. K. Murthy</p>
              </div>
            </button>
          </div>
        </div>

        {/* Form Card */}
        <Card className="border-slate-200 shadow-xl bg-white">
          <CardHeader className="space-y-1 pb-4">
            <CardTitle className="text-base font-bold">Account Credentials</CardTitle>
            <CardDescription className="text-xs">
              Enter your registered educational email address
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="rounded-lg bg-red-50 p-2.5 text-xs text-red-600 font-medium">
                  {error}
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700">Official Email</label>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@college.edu.in"
                  leftIcon={<Mail className="h-4 w-4" />}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-700">Password</label>
                  <Link
                    href="/forgot-password"
                    className="text-[11px] font-semibold text-indigo-600 hover:underline"
                  >
                    Forgot?
                  </Link>
                </div>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  leftIcon={<Lock className="h-4 w-4" />}
                  required
                />
              </div>

              <Button
                type="submit"
                variant="gradient"
                className="w-full font-bold shadow-md"
                isLoading={isLoading}
              >
                Sign In to Dashboard
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="text-center text-xs text-muted-foreground">
          Don&apos;t have an institution account?{" "}
          <Link href="/onboarding" className="font-bold text-indigo-600 hover:underline">
            Launch Onboarding Wizard
          </Link>
        </div>
      </div>
    </div>
  );
}
