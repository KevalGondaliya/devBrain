"use client";

/**
 * Minimal auth context: holds the bearer token (and its resolved role, from
 * `POST /auth/login`) in React state + `localStorage`, so a refresh doesn't
 * force re-entering it. Deliberately not a polished auth system — a
 * text-input-and-store-the-token flow is enough to demo Phase 8's
 * token-based auth from the frontend, per the task's own scope.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { login as apiLogin } from "./api";

const STORAGE_KEY = "devbrain_token";
const ROLE_STORAGE_KEY = "devbrain_role";

interface AuthState {
  token: string | null;
  role: string | null;
  actor: string | null;
  loading: boolean;
  error: string | null;
  signIn: (token: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [actor, setActor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const storedToken = window.localStorage.getItem(STORAGE_KEY);
    const storedRole = window.localStorage.getItem(ROLE_STORAGE_KEY);
    if (storedToken) {
      setToken(storedToken);
      setRole(storedRole);
    }
  }, []);

  const signIn = useCallback(async (candidate: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiLogin(candidate);
      setToken(candidate);
      setRole(res.role);
      setActor(res.actor);
      window.localStorage.setItem(STORAGE_KEY, candidate);
      window.localStorage.setItem(ROLE_STORAGE_KEY, res.role);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(() => {
    setToken(null);
    setRole(null);
    setActor(null);
    window.localStorage.removeItem(STORAGE_KEY);
    window.localStorage.removeItem(ROLE_STORAGE_KEY);
  }, []);

  return (
    <AuthContext.Provider
      value={{ token, role, actor, loading, error, signIn, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
