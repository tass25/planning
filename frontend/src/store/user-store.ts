import { create } from "zustand";
import type { User, Notification } from "@/types";
import { api, setToken, clearToken, getToken } from "@/lib/api";

interface AuthResponse {
  user: User;
  token: string;
  emailVerificationRequired?: boolean;
}

interface UserState {
  currentUser: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  notifications: Notification[];
  unreadCount: number;
  login: (email: string, password: string) => Promise<boolean>;
  signup: (email: string, password: string, name: string) => Promise<{ success: boolean; needsVerification: boolean }>;
  loginWithGitHub: (code: string) => Promise<boolean>;
  verifyEmail: (token: string) => Promise<boolean>;
  logout: () => void;
  restoreSession: () => Promise<void>;
  fetchNotifications: () => Promise<void>;
  markNotificationRead: (id: string) => Promise<void>;
  markAllNotificationsRead: () => Promise<void>;
}

export const useUserStore = create<UserState>((set, get) => ({
  currentUser: null,
  isAuthenticated: false,
  isLoading: false,
  notifications: [],
  unreadCount: 0,

  login: async (email, password) => {
    set({ isLoading: true });
    try {
      const res = await api.post<AuthResponse>("/auth/login", { email, password });
      setToken(res.token);
      set({ isLoading: false, isAuthenticated: true, currentUser: res.user });
      get().fetchNotifications();
      return true;
    } catch {
      set({ isLoading: false });
      return false;
    }
  },

  signup: async (email, password, name) => {
    set({ isLoading: true });
    try {
      const res = await api.post<AuthResponse>("/auth/signup", { email, password, name });
      setToken(res.token);
      set({ isLoading: false, isAuthenticated: true, currentUser: res.user });
      get().fetchNotifications();
      return { success: true, needsVerification: res.emailVerificationRequired || false };
    } catch {
      set({ isLoading: false });
      return { success: false, needsVerification: false };
    }
  },

  loginWithGitHub: async (code: string) => {
    set({ isLoading: true });
    try {
      const res = await api.post<AuthResponse>("/auth/github/callback", { code });
      setToken(res.token);
      set({ isLoading: false, isAuthenticated: true, currentUser: res.user });
      get().fetchNotifications();
      return true;
    } catch {
      set({ isLoading: false });
      return false;
    }
  },

  verifyEmail: async (token: string) => {
    try {
      await api.post(`/auth/verify-email?token=${encodeURIComponent(token)}`);
      // Refresh user
      const user = await api.get<User>("/auth/me");
      set({ currentUser: user });
      get().fetchNotifications();
      return true;
    } catch {
      return false;
    }
  },

  logout: () => {
    clearToken();
    set({ isAuthenticated: false, currentUser: null, notifications: [], unreadCount: 0 });
  },

  restoreSession: async () => {
    const token = getToken();
    if (!token) return;
    try {
      const user = await api.get<User>("/auth/me");
      set({ isAuthenticated: true, currentUser: user });
      get().fetchNotifications();
    } catch {
      clearToken();
    }
  },

  fetchNotifications: async () => {
    try {
      const notifs = await api.get<Notification[]>("/notifications");
      const safeNotifs = Array.isArray(notifs) ? notifs : [];
      const unread = safeNotifs.filter((n) => !n.read).length;
      set({ notifications: safeNotifs, unreadCount: unread });
    } catch {
      // Notifications may fail on first load — that's ok
    }
  },

  markNotificationRead: async (id: string) => {
    try {
      await api.put(`/notifications/${id}/read`);
      set((s) => ({
        notifications: s.notifications.map((n) => (n.id === id ? { ...n, read: true } : n)),
        unreadCount: Math.max(0, s.unreadCount - 1),
      }));
    } catch {
      // ignore
    }
  },

  markAllNotificationsRead: async () => {
    try {
      await api.put("/notifications/read-all");
      set((s) => ({
        notifications: s.notifications.map((n) => ({ ...n, read: true })),
        unreadCount: 0,
      }));
    } catch {
      // ignore
    }
  },
}));
