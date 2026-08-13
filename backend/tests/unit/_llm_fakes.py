"""Shared LLM test doubles for the Phase 7 orchestrator unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecordingLLMClient:
    """Records every `complete()` call's `prompt`/`system` and returns a
    fixed canned response, so a test can assert on exactly what an
    orchestrator sent the LLM without any network call."""

    response: str = "canned-response"
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        return self.response

    @property
    def last_prompt(self) -> str:
        return self.calls[-1][0]
