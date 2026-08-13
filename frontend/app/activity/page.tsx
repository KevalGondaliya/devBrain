"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { getActivity, ApiError, type ActivityItem } from "@/lib/api";
import { RequireToken } from "@/components/RequireToken";

const PAGE_SIZE = 25;

export default function ActivityPage() {
  return (
    <div>
      <h1>Activity</h1>
      <p className="subtitle">
        <code>GET /activity</code> — audit trail, rendered as the Tool
        Execution Viewer shape (server / tool / arguments / result / status /
        latency) from DevBrain_vision.md §21.
      </p>
      <RequireToken>
        <ActivityBody />
      </RequireToken>
    </div>
  );
}

function ActivityBody() {
  const { token } = useAuth();
  const [items, setItems] = useState<ActivityItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getActivity(token, PAGE_SIZE, offset)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load activity");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, offset]);

  if (loading && !items) return <div className="card">Loading activity…</div>;
  if (error) return <div className="error-box">{error}</div>;
  if (!items || items.length === 0) {
    return <div className="card muted">No activity recorded yet.</div>;
  }

  return (
    <div>
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Server</th>
              <th>Tool</th>
              <th>Actor</th>
              <th>Status</th>
              <th>Latency</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <ActivityRow
                key={item.id}
                item={item}
                expanded={expanded === item.id}
                onToggle={() =>
                  setExpanded(expanded === item.id ? null : item.id)
                }
              />
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "1rem" }}>
        <button
          className="btn secondary"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          Previous
        </button>
        <button
          className="btn secondary"
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Next
        </button>
        <span className="muted">
          {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
        </span>
      </div>
    </div>
  );
}

function ActivityRow({
  item,
  expanded,
  onToggle,
}: {
  item: ActivityItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr style={{ cursor: "pointer" }} onClick={onToggle}>
        <td>
          <span className="pill">{item.server}</span>
        </td>
        <td>{item.tool}</td>
        <td className="muted">{item.actor}</td>
        <td>
          <span className={`badge ${item.status?.toLowerCase()}`}>{item.status}</span>
        </td>
        <td>{item.latency_ms != null ? `${item.latency_ms}ms` : "—"}</td>
        <td className="muted">{new Date(item.created_at).toLocaleString()}</td>
      </tr>
      {expanded ? (
        <tr>
          <td colSpan={6}>
            <div style={{ display: "grid", gap: "0.5rem" }}>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem" }}>
                  Arguments
                </div>
                <pre>{JSON.stringify(item.arguments, null, 2)}</pre>
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.75rem" }}>
                  Result
                </div>
                <pre>{item.result_summary}</pre>
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}
