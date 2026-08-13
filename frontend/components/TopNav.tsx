"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

const LINKS = [
  { href: "/chat", label: "Chat" },
  { href: "/projects", label: "Projects" },
  { href: "/activity", label: "Activity" },
  { href: "/tools", label: "Tools" },
  { href: "/permissions", label: "Permissions" },
];

export function TopNav() {
  const pathname = usePathname();
  const { token, role, signIn, signOut, loading, error } = useAuth();
  const [input, setInput] = useState("");

  async function handleSignIn(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    try {
      await signIn(input.trim());
      setInput("");
    } catch {
      // error already surfaced via useAuth().error
    }
  }

  return (
    <nav className="nav">
      <span className="brand">DevBrain</span>
      <div className="nav-links">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            style={{
              color: pathname?.startsWith(link.href) ? "var(--text)" : undefined,
              background: pathname?.startsWith(link.href)
                ? "rgba(255,255,255,0.08)"
                : undefined,
            }}
          >
            {link.label}
          </Link>
        ))}
      </div>
      {token ? (
        <div className="auth-box">
          <span className="muted">role: {role ?? "unknown"}</span>
          <button className="btn secondary" onClick={signOut}>
            Sign out
          </button>
        </div>
      ) : (
        <form className="auth-box" onSubmit={handleSignIn}>
          <input
            type="password"
            placeholder="API bearer token"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
          <button className="btn" type="submit" disabled={loading}>
            {loading ? "..." : "Sign in"}
          </button>
          {error ? <span style={{ color: "var(--danger)" }}>{error}</span> : null}
        </form>
      )}
    </nav>
  );
}
