"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { getTools, ApiError, type ServerTools } from "@/lib/api";
import { RequireToken } from "@/components/RequireToken";

export default function ToolsPage() {
  return (
    <div>
      <h1>Tools</h1>
      <p className="subtitle">
        <code>GET /tools</code> — the five connected MCP servers and their
        registered tools.
      </p>
      <RequireToken>
        <ToolsBody />
      </RequireToken>
    </div>
  );
}

function ToolsBody() {
  const { token } = useAuth();
  const [servers, setServers] = useState<ServerTools[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getTools(token)
      .then((res) => {
        if (cancelled) return;
        setServers(res.servers);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load tools");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (loading) return <div className="card">Loading tools…</div>;
  if (error) return <div className="error-box">{error}</div>;
  if (!servers || servers.length === 0) {
    return <div className="card muted">No servers found.</div>;
  }

  return (
    <div className="grid">
      {servers.map((s) => (
        <div key={s.server} className="card">
          <strong>{s.server}</strong>
          <div className="muted" style={{ fontSize: "0.8rem", marginBottom: "0.25rem" }}>
            {s.tools.length} tool{s.tools.length === 1 ? "" : "s"}
          </div>
          <div className="pill-row">
            {s.tools.map((t) => (
              <span className="pill" key={t}>
                {t}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
