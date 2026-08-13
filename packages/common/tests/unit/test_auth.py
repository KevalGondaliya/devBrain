from __future__ import annotations

import pytest
from devbrain_common.auth import (
    Role,
    TokenParseError,
    TokenStore,
    check_role,
    parse_tokens,
    require_role,
)
from devbrain_common.errors import ForbiddenError, UnauthorizedError

# --------------------------------------------------------------------------
# Role ordering
# --------------------------------------------------------------------------


def test_role_rank_ordering() -> None:
    assert Role.VIEWER.rank < Role.USER.rank < Role.ADMIN.rank


@pytest.mark.parametrize(
    ("role", "other", "expected"),
    [
        (Role.ADMIN, Role.VIEWER, True),
        (Role.ADMIN, Role.ADMIN, True),
        (Role.USER, Role.ADMIN, False),
        (Role.VIEWER, Role.USER, False),
    ],
)
def test_role_at_least(role: Role, other: Role, expected: bool) -> None:
    assert role.at_least(other) is expected


# --------------------------------------------------------------------------
# parse_tokens
# --------------------------------------------------------------------------


def test_parse_tokens_empty_string_yields_empty_map() -> None:
    assert parse_tokens("") == {}
    assert parse_tokens("   ") == {}


def test_parse_tokens_single_entry() -> None:
    assert parse_tokens("devtoken123:admin") == {"devtoken123": Role.ADMIN}


def test_parse_tokens_multiple_entries() -> None:
    result = parse_tokens("devtoken123:admin,viewer456:viewer,alice:user")
    assert result == {
        "devtoken123": Role.ADMIN,
        "viewer456": Role.VIEWER,
        "alice": Role.USER,
    }


def test_parse_tokens_tolerates_whitespace() -> None:
    result = parse_tokens(" devtoken123 : admin , viewer456:viewer ")
    assert result == {"devtoken123": Role.ADMIN, "viewer456": Role.VIEWER}


def test_parse_tokens_skips_blank_segments() -> None:
    result = parse_tokens("devtoken123:admin,,")
    assert result == {"devtoken123": Role.ADMIN}


@pytest.mark.parametrize(
    "raw",
    [
        "devtoken123",  # missing role
        "devtoken123:admin:extra",  # too many parts
        ":admin",  # empty token
        "devtoken123:superuser",  # unknown role
    ],
)
def test_parse_tokens_malformed_raises(raw: str) -> None:
    with pytest.raises(TokenParseError):
        parse_tokens(raw)


# --------------------------------------------------------------------------
# TokenStore
# --------------------------------------------------------------------------


def test_token_store_resolve_known_and_unknown() -> None:
    store = TokenStore.from_env_value("devtoken123:admin,viewer456:viewer")
    assert store.resolve("devtoken123") is Role.ADMIN
    assert store.resolve("nope") is None


def test_token_store_authenticate_raises_for_unknown_token() -> None:
    store = TokenStore.from_env_value("devtoken123:admin")
    with pytest.raises(UnauthorizedError):
        store.authenticate("not-a-real-token")


def test_token_store_authenticate_returns_role_for_known_token() -> None:
    store = TokenStore.from_env_value("devtoken123:admin")
    assert store.authenticate("devtoken123") is Role.ADMIN


# --------------------------------------------------------------------------
# check_role / require_role
# --------------------------------------------------------------------------


def test_check_role_allows_sufficient_role() -> None:
    check_role(Role.ADMIN, Role.USER)  # should not raise


def test_check_role_raises_forbidden_for_insufficient_role() -> None:
    with pytest.raises(ForbiddenError):
        check_role(Role.VIEWER, Role.ADMIN)


async def test_require_role_calls_through_when_authorized() -> None:
    @require_role(Role.USER)
    async def do_thing(*, role: Role, value: int) -> int:
        return value * 2

    result = await do_thing(role=Role.ADMIN, value=21)
    assert result == 42


async def test_require_role_raises_forbidden_when_underprivileged() -> None:
    @require_role(Role.ADMIN)
    async def delete_everything(*, role: Role) -> None:
        raise AssertionError("must not be called")

    with pytest.raises(ForbiddenError):
        await delete_everything(role=Role.USER)


async def test_require_role_raises_unauthorized_when_role_missing() -> None:
    @require_role(Role.VIEWER)
    async def read_thing(*, role: Role) -> None:
        raise AssertionError("must not be called")

    with pytest.raises(UnauthorizedError):
        await read_thing()  # type: ignore[call-arg]  # intentionally omitting required `role`
