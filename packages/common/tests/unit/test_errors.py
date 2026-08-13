from __future__ import annotations

import pytest
from devbrain_common.errors import (
    ApprovalRequiredError,
    ConflictError,
    DevBrainError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
    UpstreamTimeoutError,
    ValidationError,
    to_error_envelope,
)


@pytest.mark.parametrize(
    ("error_cls", "expected_code"),
    [
        (NotFoundError, "not_found"),
        (ValidationError, "validation_error"),
        (ConflictError, "conflict"),
        (UnauthorizedError, "unauthorized"),
        (ForbiddenError, "forbidden"),
        (RateLimitedError, "rate_limited"),
        (ApprovalRequiredError, "approval_required"),
        (UpstreamTimeoutError, "upstream_timeout"),
    ],
)
def test_error_default_code_and_message(error_cls: type[DevBrainError], expected_code: str) -> None:
    err = error_cls()
    assert err.code == expected_code
    assert err.message == error_cls.default_message
    assert str(err) == error_cls.default_message


@pytest.mark.parametrize(
    ("error_cls", "expected_status"),
    [
        (ValidationError, 400),
        (UnauthorizedError, 401),
        (ForbiddenError, 403),
        (ApprovalRequiredError, 403),
        (NotFoundError, 404),
        (ConflictError, 409),
        (RateLimitedError, 429),
        (DevBrainError, 500),
        (UpstreamTimeoutError, 504),
    ],
)
def test_error_http_status_covers_devbrain_vision_24_list(
    error_cls: type[DevBrainError], expected_status: int
) -> None:
    """DevBrain_vision.md §24: 400/401/403/404/409/429/500/504 must each
    have a corresponding `devbrain_common.errors` type."""
    assert error_cls.http_status == expected_status


def test_error_custom_message_overrides_default() -> None:
    err = NotFoundError("project abc123 not found")
    assert err.code == "not_found"
    assert err.message == "project abc123 not found"


def test_error_details_default_to_empty_dict() -> None:
    err = ValidationError()
    assert err.details == {}


def test_error_details_are_stored_but_not_in_envelope() -> None:
    err = ValidationError("bad field", details={"field": "title", "reason": "too long"})
    assert err.details == {"field": "title", "reason": "too long"}
    envelope = err.to_error_envelope()
    assert envelope == {"error": {"code": "validation_error", "message": "bad field"}}
    assert "details" not in envelope["error"]


def test_to_error_envelope_shape_for_devbrain_error() -> None:
    err = ForbiddenError("nope")
    assert to_error_envelope(err) == {"error": {"code": "forbidden", "message": "nope"}}


def test_to_error_envelope_generic_exception_never_leaks_message() -> None:
    err = RuntimeError("some internal secret stack detail")
    envelope = to_error_envelope(err)
    assert envelope == {
        "error": {"code": "internal_error", "message": "An internal error occurred."}
    }
    assert "secret" not in str(envelope)


def test_devbrain_error_is_an_exception() -> None:
    with pytest.raises(NotFoundError):
        raise NotFoundError("gone")
