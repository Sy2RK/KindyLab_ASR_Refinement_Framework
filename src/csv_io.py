from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CsvData:
    rows: list[dict[str, str]]
    fieldnames: list[str]
    encoding: str
    lineterminator: str


def detect_lineterminator(raw: bytes) -> str:
    if b"\r\n" in raw:
        return "\r\n"
    if b"\r" in raw:
        return "\r"
    return "\n"


def read_csv(path: str | Path) -> CsvData:
    csv_path = Path(path)
    raw = csv_path.read_bytes()
    encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    lineterminator = detect_lineterminator(raw[:8192])
    with csv_path.open("r", encoding=encoding, newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {csv_path}")
        fieldnames = list(reader.fieldnames)
        rows = [{key: (value if value is not None else "") for key, value in row.items()} for row in reader]
    return CsvData(rows=rows, fieldnames=fieldnames, encoding=encoding, lineterminator=lineterminator)


def write_csv(path: str | Path, data: CsvData, rows: list[dict[str, str]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding=data.encoding, newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=data.fieldnames,
            extrasaction="ignore",
            lineterminator=data.lineterminator,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in data.fieldnames})

