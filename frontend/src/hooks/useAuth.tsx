"use client";

import React, { createContext, useContext, useState } from "react";
import { User, UserRole } from "@/types";
import { mockUser } from "@/services/mockData";

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  login: (email: string, role?: UserRole) => void;
  logout: () => void;
  switchRole: (role: UserRole) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(mockUser);

  const login = (email: string, role: UserRole = "admin") => {
    setUser({
      id: `usr_${Date.now()}`,
      name: role === "admin" ? "Dr. K. S. Rao" : "S. K. Murthy",
      email,
      role,
      avatarUrl:
        role === "admin"
          ? "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80"
          : "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80",
      organizationId: "org_abc_001",
    });
  };

  const logout = () => {
    setUser(null);
  };

  const switchRole = (role: UserRole) => {
    if (!user) return;
    setUser({
      ...user,
      role,
      name: role === "admin" ? "Dr. K. S. Rao (Admin)" : "S. K. Murthy (Counsellor)",
    });
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        login,
        logout,
        switchRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
