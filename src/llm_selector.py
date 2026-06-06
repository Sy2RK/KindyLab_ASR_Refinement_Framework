from __future__ import annotations

import re
from typing import Any

from .pipeline_types import CandidatePolicyDecision, ErrorTypeAnalysis, LLMCandidate, SegmentClassification
from .segment_classifier import compact_text


LLM_POLICIES = {"KEEP", "RULE_ONLY", "OPTIONAL_LLM", "MUST_LLM", "HUMAN_REVIEW_ONLY", "LLM_CAP_EXCEEDED"}
MUST_REFINABLE_TYPES = {"E1", "E2", "E3", "E4", "E5"}
HUMAN_ONLY_TYPES = {"E6", "E7"}
HIGH_RISK_TAGS = {"MEDIA_MATERIAL", "MULTI_SPEAKER_OVERLAP", "HALLUCINATION_RISK", "NEEDS_HUMAN_REVIEW"}
LOW_VALUE_TAGS = {"EMPTY_TEXT", "SHORT_BACKCHANNEL", "NOISE_ONLY"}
POLICY_PRIORITY = {"MUST_LLM": 3, "OPTIONAL_LLM": 2, "RULE_ONLY": 1, "KEEP": 0}


class CandidatePolicySelector:
    def __init__(self, config: dict[str, Any]):
        selector = config.get("selector", {})
        self.optional_min_text_length = int(selector.get("min_text_length", 12))
        self.must_min_text_length = int(selector.get("must_min_text_length", 6))
        self.max_text_length = int(selector.get("max_text_length", 220))
        self.max_llm_row_ratio = float(selector.get("max_llm_row_ratio", 0.25))
        self.label1_policy = str(selector.get("label1_policy", "optional_llm")).lower()
        self.label2_policy = str(selector.get("label2_policy", "must_llm")).lower()
        self.must_refine_respects_cap = bool(selector.get("must_refine_respects_cap", True))
        self.llm_cap_exceeded_action = str(selector.get("llm_cap_exceeded_action", "HUMAN_REVIEW_REQUIRED"))

    def assess(
        self,
        row_id: int,
        row: dict[str, str],
        original_text: str,
        current_text: str,
        classification: SegmentClassification,
        error_analysis: ErrorTypeAnalysis,
        changed_by_rules: bool,
    ) -> CandidatePolicyDecision:
        stripped = (current_text or "").strip()
        compact = compact_text(stripped)
        error_types = set(error_analysis.error_types)
        primary = error_analysis.primary_error_type
        score = self._score(row, stripped, error_analysis)
        reasons: list[str] = []

        if classification.issue_tags.intersection(LOW_VALUE_TAGS):
            policy = "KEEP"
            sop_label = "0"
            reasons.append("low-value Label 0 segment")
            return self._decision(row_id, sop_label, error_types, primary, policy, reasons, score)

        if error_types.intersection(HUMAN_ONLY_TYPES) or classification.issue_tags.intersection(HIGH_RISK_TAGS):
            policy = "HUMAN_REVIEW_ONLY"
            sop_label = "2"
            reasons.append("high-risk or non-recoverable segment")
            return self._decision(row_id, sop_label, error_types, primary, policy, reasons, score)

        if not error_types:
            policy = "RULE_ONLY" if changed_by_rules else "KEEP"
            sop_label = "0"
            reasons.append("clear or rule-only Label 0 segment")
            return self._decision(row_id, sop_label, error_types, primary, policy, reasons, score)

        sop_label = "2" if error_analysis.severity >= 2 else "1"
        if changed_by_rules and sop_label == "1":
            policy = "RULE_ONLY"
            reasons.append("Label 1 issue resolved by rules or dictionaries")
        elif sop_label == "2" and error_types.intersection(MUST_REFINABLE_TYPES):
            policy = "MUST_LLM" if self._has_enough_context(compact, self.must_min_text_length, stripped) else "HUMAN_REVIEW_ONLY"
            reasons.append("Label 2 refinable ASR error")
        elif sop_label == "1" and self.label1_policy == "optional_llm":
            policy = "OPTIONAL_LLM" if self._has_enough_context(compact, self.optional_min_text_length, stripped) else "RULE_ONLY"
            reasons.append("Label 1 optional refinement candidate")
        else:
            policy = "RULE_ONLY"
            reasons.append("configured as rule-only")

        decision = self._decision(row_id, sop_label, error_types, primary, policy, reasons, score)
        if policy in {"OPTIONAL_LLM", "MUST_LLM"}:
            decision.candidate = LLMCandidate(
                row_id=row_id,
                text=stripped,
                score=score,
                reason=decision.selector_reason,
                sop_label=sop_label,
                error_types=error_types,
                primary_error_type=primary,
                llm_policy=policy,
                selection_score=score,
            )
        return decision

    def cap_candidates(self, total_rows: int, candidates: list[LLMCandidate]) -> tuple[list[LLMCandidate], list[LLMCandidate]]:
        if not candidates:
            return [], []
        limit = max(1, int(total_rows * self.max_llm_row_ratio))
        if not self.must_refine_respects_cap:
            must = [item for item in candidates if item.llm_policy == "MUST_LLM"]
            optional = [item for item in candidates if item.llm_policy != "MUST_LLM"]
            remaining = max(limit - len(must), 0)
            selected_optional = self._rank(optional)[:remaining]
            selected = self._rank(must + selected_optional)
            selected_ids = {item.row_id for item in selected}
            return sorted(selected, key=lambda item: item.row_id), [item for item in candidates if item.row_id not in selected_ids]

        selected = self._rank(candidates)[:limit]
        selected_ids = {item.row_id for item in selected}
        capped = [item for item in candidates if item.row_id not in selected_ids]
        return sorted(selected, key=lambda item: item.row_id), sorted(capped, key=lambda item: item.row_id)

    def _decision(
        self,
        row_id: int,
        sop_label: str,
        error_types: set[str],
        primary_error_type: str,
        llm_policy: str,
        reasons: list[str],
        score: float,
    ) -> CandidatePolicyDecision:
        return CandidatePolicyDecision(
            row_id=row_id,
            sop_label=sop_label,
            error_types=error_types,
            primary_error_type=primary_error_type,
            llm_policy=llm_policy if llm_policy in LLM_POLICIES else "KEEP",
            selector_reason=", ".join(reasons),
            selection_score=score,
        )

    def _rank(self, candidates: list[LLMCandidate]) -> list[LLMCandidate]:
        return sorted(candidates, key=lambda item: (-POLICY_PRIORITY.get(item.llm_policy, 0), -item.selection_score, item.row_id))

    def _score(self, row: dict[str, str], text: str, error_analysis: ErrorTypeAnalysis) -> float:
        base_by_type = {
            "E7": 1.0,
            "E6": 0.96,
            "E2": 0.92,
            "E1": 0.88,
            "E3": 0.82,
            "E4": 0.68,
            "E5": 0.56,
            "E8": 0.4,
        }
        score = base_by_type.get(error_analysis.primary_error_type, 0.0)
        if row.get("label_type", "") == "teacher":
            score += 0.05
        if len(text) >= 35:
            score += 0.05
        if row.get("recognition_errors", "").strip():
            score += 0.03
        if re.search(r"[A-Za-z]{3,}|\d{4,}", text):
            score += 0.02
        if error_analysis.severity >= 2:
            score += 0.08
        return round(min(score, 1.0), 4)

    def _has_enough_context(self, compact: str, min_length: int, text: str) -> bool:
        if len(compact) < min_length:
            return False
        return len(text) <= self.max_text_length


LLMSelector = CandidatePolicySelector
