from __future__ import annotations


REQUIRED_COLUMNS = [
    "annotator",
    "source_file",
    "audio_file",
    "label",
    "label_display",
    "label_type",
    "teacher_id",
    "text_edited",
    "recognition_errors",
    "timestamp",
]

IMMUTABLE_COLUMNS = [
    "annotator",
    "source_file",
    "audio_file",
    "label",
    "label_display",
    "label_type",
    "teacher_id",
    "timestamp",
]


def validate_input_columns(fieldnames: list[str], text_column: str, error_column: str) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(f"Input CSV is missing required columns: {', '.join(missing)}")
    if text_column not in fieldnames:
        raise ValueError(f"Configured text column is missing: {text_column}")
    if error_column not in fieldnames:
        raise ValueError(f"Configured recognition error column is missing: {error_column}")


def validate_output_integrity(
    original_rows: list[dict[str, str]],
    output_rows: list[dict[str, str]],
    original_fieldnames: list[str],
    output_fieldnames: list[str],
) -> None:
    if len(original_rows) != len(output_rows):
        raise ValueError(f"Output row count changed: {len(original_rows)} -> {len(output_rows)}")
    if original_fieldnames != output_fieldnames:
        raise ValueError("Output column names or column order changed")
    for index, (before, after) in enumerate(zip(original_rows, output_rows), start=1):
        for column in IMMUTABLE_COLUMNS:
            if before.get(column, "") != after.get(column, ""):
                raise ValueError(f"Immutable column changed at row {index}: {column}")

