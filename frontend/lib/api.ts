/**
 * Shared API client for the FastAPI backend (Phase 8).
 *
 * Types below mirror `backend/src/devbrain_backend/api/schemas.py`
 * field-for-field — that file is the source of truth; if the two drift,
 * schemas.py wins and this file should be updated to match.
 *
 * `apiFetch` attaches the bearer token (see `lib/auth.tsx`) and throws a
 * plain `Error` with the backend's `{"error": {"code","message"}}` message
 * on non-2xx responses, so callers can just `try/catch` and show
 * `err.message`.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  code: string | undefined;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function apiFetch<T>(
  path: string,
  token: string | null,
  init?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    let code: string | undefined;
    try {
      const body = await res.json();
      if (body?.error?.message) {
        message = body.error.message;
        code = body.error.code;
      }
    } catch {
      // ignore non-JSON error bodies
    }
    throw new ApiError(res.status, message, code);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

// --- /auth/login ---

export interface LoginResponse {
  role: string;
  actor: string;
}

export function login(token: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/auth/login", token, {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

// --- /chat ---

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  reply: string;
  intent: string;
  orchestrator: string | null;
  data: Record<string, unknown>;
}

export function sendChat(
  token: string | null,
  message: string,
  history: ChatMessage[],
): Promise<ChatResponse> {
  return apiFetch<ChatResponse>("/chat", token, {
    method: "POST",
    body: JSON.stringify({ message, history }),
  });
}

// --- /activity ---

export interface ActivityItem {
  id: string;
  server: string;
  tool: string;
  arguments: Record<string, unknown>;
  result_summary: string;
  status: string;
  latency_ms: number | null;
  actor: string;
  created_at: string;
}

export interface ActivityResponse {
  items: ActivityItem[];
  limit: number;
  offset: number;
  total: number;
}

export function getActivity(
  token: string | null,
  limit = 50,
  offset = 0,
): Promise<ActivityResponse> {
  return apiFetch<ActivityResponse>(
    `/activity?limit=${limit}&offset=${offset}`,
    token,
  );
}

// --- /permissions ---

export interface ToolPermission {
  tool: string;
  risk_tier: string;
  min_role: string;
  approval_required: boolean;
}

export interface ServerPermissions {
  tools: ToolPermission[];
}

export interface PermissionsResponse {
  roles: string[];
  servers: Record<string, ServerPermissions>;
}

export function getPermissions(token: string | null): Promise<PermissionsResponse> {
  return apiFetch<PermissionsResponse>("/permissions", token);
}

// --- /projects ---

export interface ProjectOut {
  id: string;
  name: string;
  description: string | null;
  status: string;
  priority: string | null;
  owner: string | null;
  start_date: string | null;
  target_date: string | null;
}

export interface ProjectsResponse {
  projects: ProjectOut[];
}

export function getProjects(token: string | null): Promise<ProjectsResponse> {
  return apiFetch<ProjectsResponse>("/projects", token);
}

// --- /tools ---

export interface ServerTools {
  server: string;
  tools: string[];
}

export interface ToolsResponse {
  servers: ServerTools[];
}

export function getTools(token: string | null): Promise<ToolsResponse> {
  return apiFetch<ToolsResponse>("/tools", token);
}

// --- /approvals ---

export interface ApprovalOut {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  actor: string;
  risk_tier: string;
  status: string;
  requested_at: string | null;
  decided_at: string | null;
  decided_by: string | null;
  reason: string | null;
  consumed_at: string | null;
}

export interface PendingApprovalsResponse {
  approvals: ApprovalOut[];
}

export function getPendingApprovals(
  token: string | null,
): Promise<PendingApprovalsResponse> {
  return apiFetch<PendingApprovalsResponse>("/approvals/pending", token);
}

export function decideApproval(
  token: string | null,
  id: string,
  decision: "approved" | "rejected",
  reason?: string,
): Promise<ApprovalOut> {
  return apiFetch<ApprovalOut>(`/approvals/${id}/decide`, token, {
    method: "POST",
    body: JSON.stringify({ decision, reason: reason ?? null }),
  });
}
