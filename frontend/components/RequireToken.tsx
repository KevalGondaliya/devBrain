"use client";

import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";

/** Small guard used by every data page: shows a hint instead of firing
 * requests when no bearer token is set yet (see `TopNav`'s sign-in form). */
export function RequireToken({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  if (!token) {
    return (
      <div className="card">
        Sign in with an API bearer token (top right) to load this page&apos;s data.
      </div>
    );
  }
  return <>{children}</>;
}
