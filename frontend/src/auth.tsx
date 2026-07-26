import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, tokenStore } from "./api/client";
import type { AuthUser } from "./types";

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  loginWithSso: (provider: string, next?: string) => void;
  /** Adopt the session established by an SSO redirect (refresh cookie is already set). */
  adoptSession: () => Promise<boolean>;
  logout: () => Promise<void>;
  logoutEverywhere: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

/** Renew the access token a minute before it expires, so requests never race the clock. */
const RENEW_MARGIN_MS = 60_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const renewTimer = useRef<number | null>(null);

  const clearTimer = () => {
    if (renewTimer.current !== null) {
      window.clearTimeout(renewTimer.current);
      renewTimer.current = null;
    }
  };

  // Access tokens are short-lived and held in memory, so schedule a silent renewal
  // rather than waiting for a request to fail with a 401.
  const scheduleRenewal = useCallback((ttlSeconds: number) => {
    clearTimer();
    const delay = Math.max(ttlSeconds * 1000 - RENEW_MARGIN_MS, 30_000);
    renewTimer.current = window.setTimeout(async () => {
      const ok = await api.restoreSession();
      if (ok) scheduleRenewal(ttlSeconds);
      else {
        setUser(null);
        clearTimer();
      }
    }, delay);
  }, []);

  const adoptSession = useCallback(async (): Promise<boolean> => {
    // The refresh token is an HttpOnly cookie, so a page load has no access token in
    // hand -- trade the cookie for one before deciding the visitor is signed out.
    const restored = await api.restoreSession();
    if (!restored) {
      setUser(null);
      return false;
    }
    try {
      setUser(await api.me());
      scheduleRenewal(15 * 60);
      return true;
    } catch {
      setUser(null);
      return false;
    }
  }, [scheduleRenewal]);

  useEffect(() => {
    tokenStore.onLost(() => setUser(null));
    adoptSession().finally(() => setLoading(false));
    return clearTimer;
  }, [adoptSession]);

  const finishAuth = async (expiresIn: number) => {
    setUser(await api.me());
    scheduleRenewal(expiresIn || 15 * 60);
  };

  const value: AuthState = {
    user,
    loading,
    isAdmin: user?.role === "admin",
    login: async (email, password) => finishAuth((await api.login(email, password)).expires_in),
    register: async (email, password, fullName) =>
      finishAuth((await api.register(email, password, fullName)).expires_in),
    loginWithSso: (provider, next = "/") => api.startSso(provider, next),
    adoptSession,
    logout: async () => {
      clearTimer();
      await api.logout();
      setUser(null);
    },
    logoutEverywhere: async () => {
      clearTimer();
      await api.logoutEverywhere();
      setUser(null);
    },
    refreshUser: async () => setUser(await api.me()),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
