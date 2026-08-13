"""Phase 7 agent orchestrators — the "agent" leg of the tool vs. skill vs.
agent tripod (`docs/planning/second-brain-mcp-plan.md` §4's closing
paragraph; `docs/planning/DevBrain_vision.md` §19 "Phase 19 — Agent").

- A **tool** is one deterministic, single-purpose call (e.g.
  `task_mcp.tools.tasks_tools.create_task`) — thin schema validation over
  exactly one service function.
- A **skill** is a documented, reusable instruction bundle for a human or a
  Claude session to follow — shipped as a real `SKILL.md`
  (`services/knowledge_mcp/src/knowledge_mcp/skills/summarize-note/SKILL.md`).
- An **agent** (this package) strings several of those same *services*
  together with judgment and state across steps, plus an LLM call for the
  reasoning/synthesis step — multi-step, stateful, judgment-driven, versus
  a tool's single deterministic call. Every function here calls
  `<service>_mcp.services.*` functions directly (no MCP transport hop, no
  tool-schema layer) — the same functions the MCP tool layer calls — per
  second-brain-mcp-plan.md §4: "a standalone orchestrator that *calls the
  same services the tools call*".

Modules:
  - `daily_briefing.py` — DevBrain_vision.md §27, Daily Developer Briefing.
  - `project_health.py` — DevBrain_vision.md §10/§29, Project Health
    Analysis (ON_TRACK/AT_RISK/BLOCKED verdict).
  - `weekly_digest.py` — second-brain-mcp-plan.md §4's flagship: pulls
    recent notes, summarizes via the LLM client, creates + links a digest
    note through the same `notes_service.create_note` the `notes.create`
    MCP tool calls.
  - `cross_system_investigation.py` — DevBrain_vision.md §7/§8/§31,
    "why is my project blocked?" — Project -> Task -> Knowledge -> GitHub.
  - `safe_write.py` — DevBrain_vision.md §9/§30, "Safe AI Action": proposes
    a write via Phase 6's `devbrain_common.approvals` gate instead of ever
    executing one directly — never runs as `Role.ADMIN`.
  - `_common.py` — small shared glue (e.g. the GitHub-repository-slug
    heuristic) used by more than one orchestrator above.

LLM calls in every module above go through
`devbrain_common.llm.get_llm_client()` — never a concrete `LLMClient`
implementation directly — so `DEVBRAIN_LLM_MODE=stub` (the default; every
automated test) makes every orchestrator here fully network-free and
deterministic. See `devbrain_common.llm`'s module docstring for the
prompt-injection defense contract (`build_prompt`'s trusted `data` vs.
untrusted `untrusted_sections`) every orchestrator here follows.
"""

from __future__ import annotations
