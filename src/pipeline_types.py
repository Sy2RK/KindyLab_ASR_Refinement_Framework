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
class ErrorTypeAnalysis:
    error_types: set[str] = field(default_factory=set)
    primary_error_type: str = ""
    issue_tags: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    severity: int = 0


@dataclass
class CandidatePolicyDecision:
    row_id: int
    sop_label: str
    error_types: set[str] = field(default_factory=set)
    primary_error_type: str = ""
    llm_policy: str = "KEEP"
    selector_reason: str = ""
    selection_score: float = 0.0
    candidate: "LLMCandidate | None" = None


@dataclass
class LLMCandidate:
    row_id: int
    text: str
    score: float
    reason: str
    sop_label: str = "1"
    error_types: set[str] = field(default_factory=set)
    primary_error_type: str = ""
    llm_policy: str = "OPTIONAL_LLM"
    selection_score: float = 0.0


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
