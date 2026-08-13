"""MCP prompt templates — reusable instruction text a client can select
before invoking tools. Registration only; no orchestration logic lives
here (that boundary is deliberate, see `services/knowledge_mcp/README.md`'s
tool vs. skill vs. agent section). The actual multi-step weekly-digest
*workflow* (fetch -> summarize via Claude -> create digest note -> link
back -> audit) is Phase 7's `weekly_digest` agent, not this file — this
module only registers the `weekly-digest` prompt *template* the plan calls
for."""

from __future__ import annotations
