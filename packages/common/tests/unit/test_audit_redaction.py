from __future__ import annotations

from devbrain_common.audit import redact_arguments


def test_redact_arguments_hides_sensitive_top_level_keys() -> None:
    result = redact_arguments({"token": "abc123", "note_id": "n1"})
    assert result == {"token": "***redacted***", "note_id": "n1"}


def test_redact_arguments_is_case_insensitive_and_substring_matched() -> None:
    result = redact_arguments({"Authorization": "Bearer xyz", "API_KEY": "sk-1", "apikey": "sk-2"})
    assert result == {
        "Authorization": "***redacted***",
        "API_KEY": "***redacted***",
        "apikey": "***redacted***",
    }


def test_redact_arguments_recurses_into_nested_dicts_and_lists() -> None:
    result = redact_arguments(
        {
            "user": {"password": "hunter2", "name": "alice"},
            "items": [{"secret": "s1"}, {"note": "fine"}],
        }
    )
    assert result == {
        "user": {"password": "***redacted***", "name": "alice"},
        "items": [{"secret": "***redacted***"}, {"note": "fine"}],
    }


def test_redact_arguments_does_not_mutate_input() -> None:
    original = {"token": "abc123"}
    redact_arguments(original)
    assert original == {"token": "abc123"}


def test_redact_arguments_leaves_ordinary_arguments_untouched() -> None:
    payload = {"title": "My Note", "tags": ["a", "b"], "count": 3}
    assert redact_arguments(payload) == payload
