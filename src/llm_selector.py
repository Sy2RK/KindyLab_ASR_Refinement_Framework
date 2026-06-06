from __future__ import annotations

import re
from typing import Any

from .pipeline_types import LLMCandidate, SegmentClassification


class LLMSelector:
    def __init__(self, config: dict[str, Any]):
        selector = config.get("selector", {})
        self.min_text_length = int(selector.get("min_text_length", 12))
        self.max_text_length = int(selector.get("max_text_length", 220))
        self.max_llm_row_ratio = float(selector.get("max_llm_row_ratio", 0.25))
        self.blocked_issue_tags = set(selector.get("blocked_issue_tags", []))

    def assess(
        self,
        row_id: int,
        row: dict[str, str],
        text: str,
        classification: SegmentClassification,
        changed_by_rules: bool,
    ) -> LLMCandidate | None:
        stripped = (text or "").strip()
        compact = re.sub(r"[\s，。！？；：、,.!?;:]+", "", stripped)
        if classification.skip_llm or self.blocked_issue_tags.intersection(classification.issue_tags):
            return None
        if len(compact) < self.min_text_length or len(stripped) > self.max_text_length:
            return None

        score = 0.0
        reasons: list[str] = []
        label_type = row.get("label_type", "")
        if label_type == "teacher":
            score += 0.2
            reasons.append("teacher text")
        if len(stripped) >= 35:
            score += 0.25
            reasons.append("medium/long segment")
        if not re.search(r"[。！？!?]", stripped) and len(compact) >= 18:
            score += 0.3
            reasons.append("missing punctuation")
        if row.get("recognition_errors", "").strip():
            score += 0.15
            reasons.append("has existing recognition error notes")
        if changed_by_rules:
            score += 0.1
            reasons.append("rule changed text")
        if re.search(r"[A-Za-z]{3,}|\d{4,}", stripped):
            score += 0.1
            reasons.append("contains ASR-like token")

        if score < 0.3:
            return None
        return LLMCandidate(row_id=row_id, text=stripped, score=score, reason=", ".join(reasons))

    def cap_candidates(self, total_rows: int, candidates: list[LLMCandidate]) -> list[LLMCandidate]:
        if not candidates:
            return []
        limit = max(1, int(total_rows * self.max_llm_row_ratio))
        ranked = sorted(candidates, key=lambda item: (-item.score, item.row_id))[:limit]
        return sorted(ranked, key=lambda item: item.row_id)

