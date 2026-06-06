from __future__ import annotations

from .pipeline_types import Edit


def split_notes(value: str) -> list[str]:
    if not value:
        return []
    normalized = value.replace("；", ";")
    return [part.strip() for part in normalized.split(";") if part.strip()]


def merge_error_notes(existing: str, edits: list[Edit] | None = None, notes: list[str] | None = None) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for note in split_notes(existing):
        if note not in seen:
            merged.append(note)
            seen.add(note)
    for edit in edits or []:
        note = edit.to_error_note()
        if note not in seen:
            merged.append(note)
            seen.add(note)
    for note in notes or []:
        if note and note not in seen:
            merged.append(note)
            seen.add(note)
    return "; ".join(merged)

