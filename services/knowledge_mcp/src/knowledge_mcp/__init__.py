"""Knowledge MCP — DevBrain's flagship MCP server.

Owns notes/tags/links/embeddings (hybrid search, backlinks, graph
traversal) plus read access to meetings and decisions
(`docs/planning/second-brain-mcp-plan.md` §2-6,
`docs/planning/DevBrain_vision.md` §11.1).

Layering (see `ORCHESTRATION.md` golden rules, enforced directory-by-
directory in this package):

    tools/  -> services/  -> repositories/  -> devbrain_common.db

- `tools/` — thin FastMCP `@mcp.tool()` functions: Pydantic/type-hint
  validated inputs, a role check, a call into exactly one `services/`
  function, and a plain-dict/DTO return. No SQLAlchemy import anywhere in
  this directory.
- `services/` — business logic: hybrid search ranking, backlink/graph
  traversal, tag-rename cascading, wikilink parsing. DB-agnostic enough to
  unit test by mocking `repositories/`.
- `repositories/` — SQLAlchemy ORM queries only, no business logic. Only
  `repositories/unit_of_work.py` imports `devbrain_common.db` directly.

See `services/knowledge_mcp/README.md` for the tool vs. skill vs. agent
distinction this package exists partly to demonstrate.
"""

from __future__ import annotations

__version__ = "0.1.0"
