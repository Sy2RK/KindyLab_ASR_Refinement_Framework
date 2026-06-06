from __future__ import annotations

from pathlib import Path
from typing import Any

from .pipeline_types import CleanResult, Edit


class DictionaryCorrector:
    def __init__(self, dictionary_path: str | Path, default_type: str):
        self.dictionary_path = Path(dictionary_path)
        self.default_type = default_type
        self.entries = self._load_entries()

    def correct(self, text: str) -> CleanResult:
        current = text or ""
        edits: list[Edit] = []
        for entry in self.entries:
            wrong = str(entry.get("wrong", ""))
            correct = str(entry.get("correct", ""))
            if not wrong or wrong == correct or wrong not in current:
                continue
            current = current.replace(wrong, correct)
            edits.append(
                Edit(
                    source=wrong,
                    target=correct,
                    edit_type=str(entry.get("type") or self.default_type),
                    reason=str(entry.get("reason") or self.default_type),
                )
            )
        return CleanResult(text=current, edits=edits)

    def _load_entries(self) -> list[dict[str, Any]]:
        if not self.dictionary_path.exists():
            return []
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required for dictionary YAML files.") from exc
        with self.dictionary_path.open("r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
        if isinstance(loaded, list):
            entries = loaded
        elif isinstance(loaded, dict):
            entries = loaded.get("corrections") or loaded.get("aliases") or []
        else:
            entries = []
        enabled_entries = [entry for entry in entries if isinstance(entry, dict) and entry.get("enabled", True)]
        return sorted(enabled_entries, key=lambda item: len(str(item.get("wrong", ""))), reverse=True)

