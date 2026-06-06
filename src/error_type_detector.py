from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import resolve_project_path
from .pipeline_types import ErrorTypeAnalysis, SegmentClassification
from .segment_classifier import compact_text


ERROR_TYPE_TAGS = {
    "E1": "DOMAIN_TERM_ERROR",
    "E2": "CHILD_UNCLEAR",
    "E3": "HOMOPHONE_ERROR",
    "E4": "REPEATED_WORDS",
    "E5": "PUNCTUATION_ERROR",
    "E6": "MULTI_SPEAKER_OVERLAP",
    "E7": "UNREADABLE_SENTENCE",
    "E8": "OTHER_ASR_ERROR",
}

DEFAULT_ERROR_TYPE_PRIORITY = ["E7", "E6", "E2", "E1", "E3", "E4", "E5", "E8"]
COMMON_REPEATED_TOKENS = ["老师", "今天", "开始", "小朋友", "孩子", "你们", "我们", "排队", "材料"]
SEVERE_DOMAIN_PATTERNS = ["建狗区", "建够区", "建构狗", "低狗区"]
CHILD_SPEECH_PATTERNS = ["滑花梯", "还花花体", "花花体", "滑滑体"]
UNREADABLE_PATTERNS = ["无法识别", "听不清", "不清楚", "今天们", "积积老师", "好了去"]


class ErrorTypeDetector:
    def __init__(self, config: dict[str, Any], project_root: Path):
        selector = config.get("selector", {})
        self.priority = list(selector.get("error_type_priority") or DEFAULT_ERROR_TYPE_PRIORITY)
        self.domain_wrong_terms = self._load_wrong_terms(config, project_root, "domain_terms")
        self.correction_wrong_terms = self._load_wrong_terms(config, project_root, "correction_map")
        self.punctuation_min_length = int(selector.get("punctuation_error_min_length", 18))

    def detect(
        self,
        row: dict[str, str],
        text: str,
        classification: SegmentClassification,
        error_column: str,
    ) -> ErrorTypeAnalysis:
        stripped = (text or "").strip()
        recognition_errors = row.get(error_column, "") or ""
        types: set[str] = set()
        notes: list[str] = []
        severity = 0

        if "MULTI_SPEAKER_OVERLAP" in classification.issue_tags or self._looks_overlap(stripped):
            types.add("E6")
            severity = max(severity, 2)
            notes.append("E6 overlap speech")

        if self._looks_unreadable(stripped, classification):
            types.add("E7")
            severity = max(severity, 2)
            notes.append("E7 unreadable sentence")

        if self._looks_domain_error(stripped, recognition_errors):
            types.add("E1")
            severity = max(severity, 2 if any(pattern in stripped for pattern in SEVERE_DOMAIN_PATTERNS) else 1)
            notes.append("E1 domain vocabulary")

        if self._looks_child_speech_error(row, stripped, recognition_errors):
            types.add("E2")
            severity = max(severity, 2 if any(pattern in stripped for pattern in ["还花花体", "花花体"]) else 1)
            notes.append("E2 child speech recognition")

        if self._looks_homophone_error(stripped, recognition_errors):
            types.add("E3")
            severity = max(severity, 1)
            notes.append("E3 homophone error")

        repeat_severity = self._repeat_severity(stripped)
        if repeat_severity:
            types.add("E4")
            severity = max(severity, repeat_severity)
            notes.append("E4 repeated words")

        if self._looks_punctuation_error(stripped):
            types.add("E5")
            severity = max(severity, 1)
            notes.append("E5 punctuation or segmentation")

        if not types and recognition_errors.strip():
            types.add("E8")
            severity = max(severity, 1)
            notes.append("E8 existing recognition error note")

        issue_tags = {ERROR_TYPE_TAGS[item] for item in types if item in ERROR_TYPE_TAGS}
        primary = self.primary_error_type(types)
        return ErrorTypeAnalysis(
            error_types=types,
            primary_error_type=primary,
            issue_tags=issue_tags,
            notes=notes,
            severity=severity,
        )

    def primary_error_type(self, error_types: set[str]) -> str:
        for item in self.priority:
            if item in error_types:
                return item
        return sorted(error_types)[0] if error_types else ""

    def _load_wrong_terms(self, config: dict[str, Any], project_root: Path, key: str) -> set[str]:
        path_value = config.get("dictionaries", {}).get(key, "")
        path = resolve_project_path(project_root, path_value)
        if not path.exists():
            return set()
        try:
            import yaml
        except ImportError:
            return set()
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = loaded.get("corrections") if isinstance(loaded, dict) else []
        if not isinstance(entries, list):
            return set()
        return {str(item.get("wrong", "")) for item in entries if isinstance(item, dict) and item.get("wrong")}

    def _looks_overlap(self, text: str) -> bool:
        speaker_prefixes = len(re.findall(r"(老师|教师|幼儿|儿童|学生)[:：]", text))
        return speaker_prefixes >= 2 or ("同时" in text and ("说话" in text or "讲话" in text))

    def _looks_unreadable(self, text: str, classification: SegmentClassification) -> bool:
        if "HALLUCINATION_RISK" in classification.issue_tags:
            return False
        if any(pattern in text for pattern in UNREADABLE_PATTERNS):
            return True
        compact = compact_text(text)
        if len(compact) < 10:
            return False
        odd_chunks = len(re.findall(r"(那个好了|好了去|们玩那个|去积)", compact))
        return odd_chunks >= 2

    def _looks_domain_error(self, text: str, recognition_errors: str) -> bool:
        if any(term and term in text for term in self.domain_wrong_terms):
            return True
        if any(pattern in text for pattern in SEVERE_DOMAIN_PATTERNS):
            return True
        return any(word in recognition_errors for word in ["领域", "术语", "积木", "建构", "低结构", "纸巾筒"])

    def _looks_child_speech_error(self, row: dict[str, str], text: str, recognition_errors: str) -> bool:
        if any(pattern in text for pattern in CHILD_SPEECH_PATTERNS):
            return True
        label_type = row.get("label_type", "")
        if label_type in {"student", "child", "unknown"} and any(word in recognition_errors for word in ["儿童", "发音", "不清"]):
            return True
        return False

    def _looks_homophone_error(self, text: str, recognition_errors: str) -> bool:
        if any(term and term in text for term in self.correction_wrong_terms):
            return True
        if any(word in recognition_errors for word in ["同音", "近音", "错词", "错字"]):
            return True
        return any(word in text for word in ["兰色", "篮色", "排对", "金木", "收才料"])

    def _repeat_severity(self, text: str) -> int:
        severe_repeats = len(re.findall(r"(.{1,4})\1{2,}", text))
        if severe_repeats:
            return 2
        adjacent_repeats = 0
        for token in COMMON_REPEATED_TOKENS:
            if token + token in text:
                adjacent_repeats += 1
        if adjacent_repeats >= 2:
            return 1
        if adjacent_repeats == 1:
            return 1
        return 0

    def _looks_punctuation_error(self, text: str) -> bool:
        compact = compact_text(text)
        if len(compact) < self.punctuation_min_length:
            return False
        if not re.search(r"[。！？!?]", text):
            return True
        return bool(re.search(r"([。！？；，、])\1+", text))
