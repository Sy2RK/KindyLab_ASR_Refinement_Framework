from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Metrics:
    counters: Counter[str] = field(default_factory=Counter)

    def inc(self, key: str, amount: int = 1) -> None:
        self.counters[key] += amount

    def update_llm_usage(self, usage: dict[str, Any]) -> None:
        if not usage:
            return
        mapping = {
            "prompt_tokens": "llm_input_tokens",
            "completion_tokens": "llm_output_tokens",
            "total_tokens": "llm_total_tokens",
        }
        for source, target in mapping.items():
            value = usage.get(source)
            if isinstance(value, int):
                self.inc(target, value)

    def as_dict(self) -> dict[str, int]:
        return dict(self.counters)

