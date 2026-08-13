"""Pydantic request/response models for the Phase 8 HTTP surface.

Kept separate from every router so the response *shape* (what Phase 9's
frontend can rely on) is legible in one file. Field types intentionally
mirror the underlying service DTOs / `devbrain_common` models field-for-
field — no shape is invented here beyond what DevBrain_vision.md §20/§21
ask for.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# --- /auth/login ---


class LoginRequest(BaseModel):
    token: str


class LoginResponse(BaseModel):
    role: str
    actor: str


# --- /chat ---


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    intent: str
    orchestrator: str | None
    data: dict[str, Any] = Field(default_factory=dict)


# --- /activity ---


class ActivityItem(BaseModel):
    """DevBrain_vision.md §21's "Tool Execution" shape: server, tool,
    arguments, result summary, status, latency."""

    id: str
    server: str
    tool: str
    arguments: dict[str, Any]
    result_summary: str
    status: str
    latency_ms: int | None
    actor: str
    created_at: datetime


class ActivityResponse(BaseModel):
    items: list[ActivityItem]
    limit: int
    offset: int
    total: int


# --- /permissions ---


class ToolPermission(BaseModel):
    tool: str
    risk_tier: str
    min_role: str
    approval_required: bool


class ServerPermissions(BaseModel):
    tools: list[ToolPermission]


class PermissionsResponse(BaseModel):
    roles: list[str]
    servers: dict[str, ServerPermissions]


# --- /projects ---


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    priority: str | None
    owner: str | None
    start_date: datetime | None
    target_date: datetime | None


class ProjectsResponse(BaseModel):
    projects: list[ProjectOut]


# --- /tools ---


class ServerTools(BaseModel):
    server: str
    tools: list[str]


class ToolsResponse(BaseModel):
    servers: list[ServerTools]


# --- /approvals ---


class ApprovalOut(BaseModel):
    id: str
    tool_name: str
    arguments: dict[str, Any]
    actor: str
    risk_tier: str
    status: str
    requested_at: datetime | None
    decided_at: datetime | None
    decided_by: str | None
    reason: str | None
    consumed_at: datetime | None


class PendingApprovalsResponse(BaseModel):
    approvals: list[ApprovalOut]


class ApprovalDecideRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = None
