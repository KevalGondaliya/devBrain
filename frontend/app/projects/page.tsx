"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { getProjects, ApiError, type ProjectOut } from "@/lib/api";
import { RequireToken } from "@/components/RequireToken";

export default function ProjectsPage() {
  return (
    <div>
      <h1>Projects</h1>
      <p className="subtitle">
        <code>GET /projects</code>
      </p>
      <RequireToken>
        <ProjectsBody />
      </RequireToken>
    </div>
  );
}

function ProjectsBody() {
  const { token } = useAuth();
  const [projects, setProjects] = useState<ProjectOut[] | null>(null);
  const [selected, setSelected] = useState<ProjectOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getProjects(token)
      .then((res) => {
        if (cancelled) return;
        setProjects(res.projects);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load projects");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (loading) return <div className="card">Loading projects…</div>;
  if (error) return <div className="error-box">{error}</div>;
  if (!projects || projects.length === 0) {
    return <div className="card muted">No projects found.</div>;
  }

  return (
    <div>
      <div className="grid">
        {projects.map((p) => (
          <div
            key={p.id}
            className="card"
            style={{ cursor: "pointer" }}
            onClick={() => setSelected(p)}
          >
            <strong>{p.name}</strong>
            <div className="pill-row">
              <span className={`badge ${p.status?.toLowerCase()}`}>{p.status}</span>
              {p.priority ? <span className="badge medium">{p.priority}</span> : null}
            </div>
            <p className="muted" style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
              {p.description ?? "No description"}
            </p>
            <p className="muted" style={{ fontSize: "0.8rem" }}>
              owner: {p.owner ?? "—"}
            </p>
          </div>
        ))}
      </div>

      {selected ? (
        <div className="card" style={{ marginTop: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <h2 style={{ margin: 0 }}>{selected.name}</h2>
            <button className="btn secondary" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <p>{selected.description ?? "No description"}</p>
          <table>
            <tbody>
              <tr>
                <th>Status</th>
                <td>{selected.status}</td>
              </tr>
              <tr>
                <th>Priority</th>
                <td>{selected.priority ?? "—"}</td>
              </tr>
              <tr>
                <th>Owner</th>
                <td>{selected.owner ?? "—"}</td>
              </tr>
              <tr>
                <th>Start date</th>
                <td>{selected.start_date ?? "—"}</td>
              </tr>
              <tr>
                <th>Target date</th>
                <td>{selected.target_date ?? "—"}</td>
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
