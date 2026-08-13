"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { getPermissions, ApiError, type PermissionsResponse } from "@/lib/api";
import { RequireToken } from "@/components/RequireToken";

export default function PermissionsPage() {
  return (
    <div>
      <h1>Permissions</h1>
      <p className="subtitle">
        <code>GET /permissions</code> — role → tool risk matrix.
      </p>
      <RequireToken>
        <PermissionsBody />
      </RequireToken>
    </div>
  );
}

function PermissionsBody() {
  const { token } = useAuth();
  const [data, setData] = useState<PermissionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getPermissions(token)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError ? err.message : "Failed to load permissions",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (loading) return <div className="card">Loading permissions…</div>;
  if (error) return <div className="error-box">{error}</div>;
  if (!data) return null;

  return (
    <div>
      <p className="muted">Roles: {data.roles.join(", ")}</p>
      {Object.entries(data.servers).map(([server, perms]) => (
        <div key={server} style={{ marginBottom: "1.5rem" }}>
          <h2 className="section-heading">{server}</h2>
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Tool</th>
                  <th>Risk tier</th>
                  <th>Min role</th>
                  <th>Approval required</th>
                </tr>
              </thead>
              <tbody>
                {perms.tools.map((t) => (
                  <tr key={t.tool}>
                    <td>{t.tool}</td>
                    <td>
                      <span className={`badge ${t.risk_tier?.toLowerCase()}`}>
                        {t.risk_tier}
                      </span>
                    </td>
                    <td>{t.min_role}</td>
                    <td>{t.approval_required ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
