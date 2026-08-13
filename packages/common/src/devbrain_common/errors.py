"""Structured application error hierarchy.

ORCHESTRATION.md §1: "Structured errors only — `{"error": {"code": "...",
"message": "..."}}`, never a raw traceback or stack string back to the
client." Every error a service/tool layer wants to surface to a caller
should be one of these (or a subclass), rendered via `to_error_envelope`.
"""

from __future__ import annotations

from typing import Any


class DevBrainError(Exception):
    """Base class for all structured application errors.

    Subclasses set a class-level `code` and `default_message`; callers may
    override `message` per-instance and attach `details` for logging (never
    included in the client-facing envelope unless explicitly whitelisted).
    """

    code: str = "internal_error"
    default_message: str = "An internal error occurred."
    http_status: int = 500

    def __init__(
        self, message: str | None = None, *, details: dict[str, Any] | None = None
    ) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)

    def to_error_envelope(self) -> dict[str, dict[str, str]]:
        """Render as the `{"error": {"code", "message"}}` envelope."""
        return to_error_envelope(self)


class NotFoundError(DevBrainError):
    code = "not_found"
    default_message = "The requested resource was not found."
    http_status = 404


class ValidationError(DevBrainError):
    code = "validation_error"
    default_message = "The request failed validation."
    # DevBrain_vision.md §24 lists "400 Invalid arguments" (not 422) as the
    # canonical client-input-error status; this is the type that satisfies it.
    http_status = 400


class ConflictError(DevBrainError):
    code = "conflict"
    default_message = "The request conflicts with the current state of the resource."
    http_status = 409


class UnauthorizedError(DevBrainError):
    code = "unauthorized"
    default_message = "Authentication is required."
    http_status = 401


class ForbiddenError(DevBrainError):
    code = "forbidden"
    default_message = "You do not have permission to perform this action."
    http_status = 403


class RateLimitedError(DevBrainError):
    code = "rate_limited"
    default_message = "Too many requests — please slow down."
    http_status = 429


class ApprovalRequiredError(DevBrainError):
    """Raised when a `Role.USER` caller attempts a medium+ risk write tool
    without supplying a valid, matching, unconsumed `approval_id`.

    Phase 6's human-in-the-loop gate (`devbrain_common.approvals`) — see
    PROGRESS_REPORT.md Phase 6 "Decisions made" for the full design. 403
    (not 401) — the caller is authenticated and has a role that *could*
    eventually perform this action once approved, they're just missing a
    prerequisite, same shape as `ForbiddenError`.
    """

    code = "approval_required"
    default_message = "This action requires approval before it can execute."
    http_status = 403


class UpstreamTimeoutError(DevBrainError):
    """Raised when a tool call exceeds `Settings.tool_timeout_seconds`
    (DevBrain_vision.md §15 "timeouts", §24 "504 Timeout")."""

    code = "upstream_timeout"
    default_message = "The operation timed out."
    http_status = 504


def to_error_envelope(error: DevBrainError | Exception) -> dict[str, dict[str, str]]:
    """Render any error as the client-facing `{"error": {"code", "message"}}` envelope.

    Non-`DevBrainError` exceptions are mapped to a generic `internal_error`
    envelope — their raw message/traceback is never forwarded to the client.
    """
    if isinstance(error, DevBrainError):
        return {"error": {"code": error.code, "message": error.message}}
    return {
        "error": {
            "code": DevBrainError.code,
            "message": DevBrainError.default_message,
        }
    }
