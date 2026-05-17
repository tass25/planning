import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import api, { setToken, clearToken, isAuthenticated } from "./api";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user" | "viewer";
  conversionCount: number;
  status: string;
  emailVerified: boolean;
  createdAt: string;
}

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<{ emailVerificationRequired: boolean }>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    if (!isAuthenticated()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await api.get("/auth/me") as AuthUser;
      setUser(res);
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post("/auth/login", { email, password }) as {
      user: AuthUser;
      token: string;
    };
    setToken(res.token);
    setUser(res.user);
  }, []);

  const signup = useCallback(async (email: string, password: string, name: string) => {
    const res = await api.post("/auth/signup", { email, password, name }) as {
      user: AuthUser;
      token: string;
      emailVerificationRequired: boolean;
    };
    setToken(res.token);
    setUser(res.user);
    return { emailVerificationRequired: res.emailVerificationRequired };
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    window.location.hash = "#/login";
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
