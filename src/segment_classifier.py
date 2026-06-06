from __future__ import annotations

import re
from typing import Any

from .pipeline_types import SegmentClassification


BACKCHANNELS = {
    "嗯",
    "恩",
    "啊",
    "哦",
    "噢",
    "呃",
    "诶",
    "哎",
    "唉",
    "好",
    "对",
    "是",
    "不是",
    "没有",
    "可以",
    "行",
}

NOISE_PATTERNS = [
    re.compile(r"^[哈呵嘿嘻]+[。！？!?]*$"),
    re.compile(r"^[啊呀哇呜嗷]+[。！？!?]*$"),
    re.compile(r"^\(?笑声\)?[。！？!?]*$"),
    re.compile(r"^\(?哭声\)?[。！？!?]*$"),
    re.compile(r"^\(?尖叫\)?[。！？!?]*$"),
    re.compile(r"^\(?音乐\)?[。！？!?]*$"),
]


def compact_text(text: str) -> str:
    return re.sub(r"[\s，,。.!！?？；;：:、]+", "", text or "")


class SegmentValueClassifier:
    def __init__(self, config: dict[str, Any]):
        rules = config.get("rules", {})
        classifier = config.get("classifier", {})
        self.short_text_max_length = int(rules.get("short_text_max_length", 4))
        self.skip_empty_text = bool(rules.get("skip_empty_text", True))
        self.skip_short_text = bool(rules.get("skip_short_text", True))
        self.media_keywords = list(classifier.get("media_keywords", []))
        self.hallucination_student_length = int(classifier.get("hallucination_student_length", 140))
        self.segment_too_long_length = int(classifier.get("segment_too_long_length", 220))

    def classify(self, row: dict[str, str], text_column: str) -> SegmentClassification:
        text = row.get(text_column, "") or ""
        stripped = text.strip()
        tags: set[str] = set()
        notes: list[str] = []
        skip_all = False
        skip_llm = False
        need_review = False

        if not stripped:
            tags.add("EMPTY_TEXT")
            return SegmentClassification(
                primary_label="EMPTY_TEXT",
                issue_tags=tags,
                skip_llm=True,
                skip_all_cleaning=self.skip_empty_text,
                notes=["empty text"],
            )

        compact = compact_text(stripped)
        if self._is_noise_only(stripped):
            tags.add("NOISE_ONLY")
            skip_llm = True
            skip_all = True
            notes.append("noise-only text")
        elif self.skip_short_text and len(compact) <= self.short_text_max_length and compact in BACKCHANNELS:
            tags.add("SHORT_BACKCHANNEL")
            skip_llm = True
            skip_all = True
            notes.append("short backchannel")

        if any(keyword and keyword in stripped for keyword in self.media_keywords):
            tags.add("MEDIA_MATERIAL")
            skip_llm = True
            need_review = True
            notes.append("possible multimedia or background material")

        label_type = row.get("label_type", "")
        if len(stripped) > self.segment_too_long_length:
            tags.add("SEGMENT_TOO_LONG")
            need_review = True
            notes.append("very long segment")

        if label_type in {"student", "unknown"} and len(stripped) > self.hallucination_student_length:
            tags.add("HALLUCINATION_RISK")
            skip_llm = True
            need_review = True
            notes.append("long student/unknown segment may be hallucinated or mixed")

        if self._looks_multi_speaker(stripped, label_type):
            tags.add("MULTI_SPEAKER_OVERLAP")
            skip_llm = True
            need_review = True
            notes.append("possible mixed speakers")

        if not tags:
            tags.add("VALID_TEACHING_TEXT")

        primary = "VALID_TEACHING_TEXT"
        for preferred in [
            "EMPTY_TEXT",
            "NOISE_ONLY",
            "SHORT_BACKCHANNEL",
            "MEDIA_MATERIAL",
            "MULTI_SPEAKER_OVERLAP",
            "HALLUCINATION_RISK",
        ]:
            if preferred in tags:
                primary = preferred
                break

        if need_review:
            tags.add("NEEDS_HUMAN_REVIEW")

        return SegmentClassification(
            primary_label=primary,
            issue_tags=tags,
            skip_llm=skip_llm,
            skip_all_cleaning=skip_all,
            need_human_review=need_review,
            notes=notes,
        )

    def _is_noise_only(self, text: str) -> bool:
        compact = compact_text(text)
        if not compact:
            return False
        return any(pattern.match(compact) for pattern in NOISE_PATTERNS)

    def _looks_multi_speaker(self, text: str, label_type: str) -> bool:
        if label_type == "teacher":
            return False
        question_count = text.count("？") + text.count("?")
        answer_markers = len(re.findall(r"(老师|小朋友|孩子|你们|我们|他说|她说)", text))
        if len(text) > 90 and question_count >= 3 and answer_markers >= 2:
            return True
        if "同时" in text and ("说话" in text or "讲话" in text):
            return True
        return False

