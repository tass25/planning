import { create } from "zustand";
import type { User } from "@/types";

interface UserState {
  currentUser: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<boolean>;
  signup: (email: string, password: string, name: string) => Promise<boolean>;
  logout: () => void;
}

const MOCK_USERS: Record<string, { password: string; user: User }> = {
  "admin@codara.dev": {
    password: "admin123!",
    user: {
      id: "u-001",
      email: "admin@codara.dev",
      name: "Admin",
      role: "admin",
      conversionCount: 142,
      status: "active",
      createdAt: "2025-11-01T10:00:00Z",
    },
  },
  "user@codara.dev": {
    password: "user123!",
    user: {
      id: "u-002",
      email: "user@codara.dev",
      name: "Demo User",
      role: "user",
      conversionCount: 34,
      status: "active",
      createdAt: "2026-01-15T10:00:00Z",
    },
  },
};

export const useUserStore = create<UserState>((set) => ({
  currentUser: null,
  isAuthenticated: false,
  isLoading: false,

  login: async (email, password) => {
    set({ isLoading: true });
    await new Promise((r) => setTimeout(r, 1200));
    const mock = MOCK_USERS[email];
    if (mock && mock.password === password) {
      set({ isLoading: false, isAuthenticated: true, currentUser: mock.user });
      return true;
    }
    // Fallback: accept any credentials for demo
    set({
      isLoading: false,
      isAuthenticated: true,
      currentUser: {
        id: `u-${Date.now()}`,
        email,
        name: email.split("@")[0].replace(/[._]/g, " "),
        role: "user",
        conversionCount: 0,
        status: "active",
        createdAt: new Date().toISOString(),
      },
    });
    return true;
  },

  signup: async (email, _password, name) => {
    set({ isLoading: true });
    await new Promise((r) => setTimeout(r, 1500));
    set({
      isLoading: false,
      isAuthenticated: true,
      currentUser: {
        id: `u-${Date.now()}`,
        email,
        name,
        role: "user",
        conversionCount: 0,
        status: "active",
        createdAt: new Date().toISOString(),
      },
    });
    return true;
  },

  logout: () => set({ isAuthenticated: false, currentUser: null }),
}));
