from __future__ import annotations

import pytest

from ._helpers import World, build_world


@pytest.fixture(scope="session")
def world() -> World:
    """One deterministic (`seed=42`, `size="small"`) in-memory dataset, built
    once per test session and shared read-only across every unit test.
    """
    return build_world()
