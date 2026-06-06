from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from .pipeline_types import GuardDecision


PROTECTED_PHRASES = [
    "好不好",
    "对不对",
    "是不是",
    "可不可以",
    "行不行",
    "嗯",
    "啊",
    "呀",
    "吧",
    "啦",
    "哦",
    "呃",
]

FORBIDDEN_SPEAKER_PREFIXES = ["老师：", "教师：", "幼儿：", "儿童：", "学生：", "T：", "S："]


class RefinementGuard:
    def __init__(self, config: dict[str, Any]):
        guard = config.get("guard", {})
        self.max_added_ratio = float(guard.get("max_added_ratio", 0.2))
        self.max_deleted_ratio = float(guard.get("max_deleted_ratio", 0.3))
        self.max_edit_distance_ratio = float(guard.get("max_edit_distance_ratio", 0.4))
        self.min_confidence = float(guard.get("min_confidence", 0.7))

    def evaluate(self, original: str, refined: str, confidence: float) -> GuardDecision:
        if not isinstance(refined, str) or not refined.strip():
            return GuardDecision(False, "empty or invalid LLM output", {"OVER_REFINEMENT_RISK"})
        if confidence < self.min_confidence:
            return GuardDecision(False, "low confidence", {"OVER_REFINEMENT_RISK", "NEEDS_HUMAN_REVIEW"})
        if original.strip() == refined.strip():
            return GuardDecision(True, "unchanged")

        added, deleted = self._added_deleted_counts(original, refined)
        base_len = max(len(original), 1)
        added_ratio = added / base_len
        deleted_ratio = deleted / base_len
        edit_ratio = 1 - SequenceMatcher(None, original, refined).ratio()

        if added_ratio > self.max_added_ratio:
            return GuardDecision(False, "added content ratio too high", {"OVER_REFINEMENT_RISK", "NEEDS_HUMAN_REVIEW"})
        if deleted_ratio > self.max_deleted_ratio:
            return GuardDecision(False, "deleted content ratio too high", {"OVER_REFINEMENT_RISK", "NEEDS_HUMAN_REVIEW"})
        if edit_ratio > self.max_edit_distance_ratio:
            return GuardDecision(False, "edit distance ratio too high", {"OVER_REFINEMENT_RISK", "NEEDS_HUMAN_REVIEW"})
        if self._removed_protected_language(original, refined):
            return GuardDecision(False, "protected classroom speech was removed", {"OVER_REFINEMENT_RISK", "NEEDS_HUMAN_REVIEW"})
        if self._introduced_speaker_prefix(original, refined):
            return GuardDecision(False, "introduced speaker labels", {"OVER_REFINEMENT_RISK", "NEEDS_HUMAN_REVIEW"})
        return GuardDecision(True, "accepted")

    def _added_deleted_counts(self, original: str, refined: str) -> tuple[int, int]:
        added = 0
        deleted = 0
        matcher = SequenceMatcher(None, original, refined)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "insert":
                added += j2 - j1
            elif tag == "delete":
                deleted += i2 - i1
            elif tag == "replace":
                added += j2 - j1
                deleted += i2 - i1
        return added, deleted

    def _removed_protected_language(self, original: str, refined: str) -> bool:
        for phrase in PROTECTED_PHRASES:
            if original.count(phrase) > refined.count(phrase):
                return True
        return False

    def _introduced_speaker_prefix(self, original: str, refined: str) -> bool:
        if any(prefix in original for prefix in FORBIDDEN_SPEAKER_PREFIXES):
            return False
        return any(prefix in refined for prefix in FORBIDDEN_SPEAKER_PREFIXES)

