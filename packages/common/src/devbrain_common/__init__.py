"""DevBrain shared package: config, DB session, schema, logging, auth, audit, rate limiting.

This package is imported by every MCP service and the backend. Keep it free of
service-specific business logic — only cross-cutting primitives belong here.
"""

from __future__ import annotations

__all__: list[str] = []
