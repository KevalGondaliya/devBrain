"""DevBrain backend package.

`agents/` (Phase 7) holds the agent orchestrators — plain async Python that
calls the five services' `services/*.py` functions directly (no MCP
transport hop, no tool-schema layer) plus an LLM call for the
reasoning/synthesis step. `api/` (Phase 8) is the FastAPI HTTP surface that
will sit in front of these.
"""

from __future__ import annotations
