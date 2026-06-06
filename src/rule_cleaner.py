from __future__ import annotations

import re
from typing import Any

from .pipeline_types import CleanResult


TERMINAL_PUNCTUATION = set("。！？!?…")
QUESTION_ENDINGS = (
    "吗",
    "嘛",
    "好不好",
    "对不对",
    "对吧",
    "是不是",
    "行不行",
    "可以吗",
    "有没有",
    "什么呀",
    "什么啊",
    "什么呢",
    "哪里呢",
    "哪儿呢",
    "怎么呢",
    "怎么做呢",
    "怎么样",
    "怎么做",
    "多少",
    "哪一个",
)

QUESTION_WORDS = ("什么", "哪里", "哪儿", "几", "怎么", "为什么", "谁")


def convert_fullwidth_alnum(text: str) -> str:
    chars: list[str] = []
    for char in text:
        code = ord(char)
        if code == 0x3000:
            chars.append(" ")
        elif 0xFF10 <= code <= 0xFF19 or 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A:
            chars.append(chr(code - 0xFEE0))
        else:
            chars.append(char)
    return "".join(chars)


class RuleCleaner:
    def __init__(self, config: dict[str, Any]):
        rules = config.get("rules", {})
        self.enable_punctuation_fix = bool(rules.get("enable_punctuation_fix", True))
        self.add_terminal_punctuation = bool(rules.get("add_terminal_punctuation", True))
        self.short_text_max_length = int(rules.get("short_text_max_length", 4))

    def clean(self, text: str) -> CleanResult:
        original = text
        current = convert_fullwidth_alnum(text or "")
        notes: list[str] = []

        without_extra_spaces = re.sub(r"[\t\r\n\u00a0]+", " ", current)
        without_extra_spaces = re.sub(r" {2,}", " ", without_extra_spaces).strip()
        without_extra_spaces = re.sub(r"\s*([，。！？；：、])\s*", r"\1", without_extra_spaces)
        without_extra_spaces = re.sub(r"\s+([,.!?;:])", r"\1", without_extra_spaces)
        if without_extra_spaces != current:
            notes.append("[空格清理]")
            current = without_extra_spaces

        if self.enable_punctuation_fix:
            punctuated = self._normalize_punctuation(current)
            if punctuated != current:
                notes.append("[标点修正]")
                current = punctuated

        if current == original:
            return CleanResult(text=original)
        return CleanResult(text=current, notes=notes)

    def _normalize_punctuation(self, text: str) -> str:
        current = text
        current = current.replace("?", "？").replace("!", "！").replace(";", "；")
        current = re.sub(r"([。！？；，、])\1+", r"\1", current)
        current = re.sub(r"，([。！？])", r"\1", current)
        current = re.sub(r"([。！？])，", r"\1", current)
        if self.add_terminal_punctuation:
            current = self._add_terminal_punctuation(current)
        return current

    def _add_terminal_punctuation(self, text: str) -> str:
        stripped = text.strip()
        if not stripped or stripped[-1] in TERMINAL_PUNCTUATION:
            return text
        compact = re.sub(r"[\s，。！？；：、,.!?;:]+", "", stripped)
        if len(compact) <= self.short_text_max_length:
            return text
        if any(compact.endswith(ending) for ending in QUESTION_ENDINGS):
            return stripped + "？"
        if any(compact.endswith(word) for word in QUESTION_WORDS):
            return stripped + "？"
        return text
