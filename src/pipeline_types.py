from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Edit:
    source: str
    target: str
    edit_type: str
    reason: str = ""

    def to_error_note(self) -> str:
        if self.source or self.target:
            return f"{self.source}->{self.target}[{self.edit_type}]"
        return f"[{self.edit_type}]"


@dataclass
class CleanResult:
    text: str
    edits: list[Edit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.edits or self.notes)


@dataclass
class SegmentClassification:
    primary_label: str
    issue_tags: set[str] = field(default_factory=set)
    skip_llm: bool = False
    skip_all_cleaning: bool = False
    need_human_review: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class LLMCandidate:
    row_id: int
    text: str
    score: float
    reason: str


@dataclass
class LLMRefinement:
    row_id: int
    refined_text: str
    edits: list[Edit] = field(default_factory=list)
    confidence: float = 0.0
    raw: dict[str, Any] | None = None


@dataclass
class GuardDecision:
    accepted: bool
    reason: str
    issue_tags: set[str] = field(default_factory=set)

