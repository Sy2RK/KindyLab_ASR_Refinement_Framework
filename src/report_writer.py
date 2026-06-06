from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


REPORT_FIELDS = [
    "row_id",
    "audio_file",
    "timestamp",
    "label_type",
    "original_text",
    "final_text",
    "sop_label",
    "error_types",
    "primary_error_type",
    "llm_policy",
    "selector_reason",
    "selection_score",
    "guard_decision",
    "action",
    "issue_tags",
    "used_llm",
    "confidence",
    "need_human_review",
    "notes",
]


@dataclass
class ReportRow:
    row_id: int
    audio_file: str
    timestamp: str
    label_type: str
    original_text: str
    final_text: str
    sop_label: str = "0"
    error_types: set[str] = field(default_factory=set)
    primary_error_type: str = ""
    llm_policy: str = "KEEP"
    selector_reason: str = ""
    selection_score: str = ""
    guard_decision: str = ""
    action: str = "UNCHANGED"
    issue_tags: set[str] = field(default_factory=set)
    used_llm: bool = False
    confidence: str = ""
    need_human_review: bool = False
    notes: list[str] = field(default_factory=list)

    def to_csv_row(self) -> dict[str, str]:
        return {
            "row_id": str(self.row_id),
            "audio_file": self.audio_file,
            "timestamp": self.timestamp,
            "label_type": self.label_type,
            "original_text": self.original_text,
            "final_text": self.final_text,
            "sop_label": self.sop_label,
            "error_types": "|".join(sorted(self.error_types)),
            "primary_error_type": self.primary_error_type,
            "llm_policy": self.llm_policy,
            "selector_reason": self.selector_reason,
            "selection_score": self.selection_score,
            "guard_decision": self.guard_decision,
            "action": self.action,
            "issue_tags": "|".join(sorted(self.issue_tags)),
            "used_llm": "true" if self.used_llm else "false",
            "confidence": self.confidence,
            "need_human_review": "true" if self.need_human_review else "false",
            "notes": "; ".join(self.notes),
        }


def write_quality_report(path: str | Path, rows: list[ReportRow]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REPORT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())
