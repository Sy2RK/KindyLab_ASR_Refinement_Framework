from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.config import get_api_key, load_config, load_env_file, resolve_model_alias, resolve_project_path
from src.csv_io import CsvData, read_csv, write_csv
from src.deepseek_client import DeepSeekClient
from src.dictionary_corrector import DictionaryCorrector
from src.error_type_detector import ErrorTypeDetector
from src.error_notes import merge_error_notes
from src.llm_selector import CandidatePolicySelector
from src.metrics import Metrics
from src.pipeline_types import CandidatePolicyDecision, LLMCandidate
from src.refinement_guard import RefinementGuard
from src.report_writer import ReportRow, write_quality_report
from src.rule_cleaner import RuleCleaner
from src.segment_classifier import SegmentValueClassifier
from src.validators import validate_input_columns, validate_output_integrity


ACTION_PRIORITY = {
    "SKIP": 0,
    "UNCHANGED": 1,
    "RULE_FIXED": 2,
    "DICT_FIXED": 3,
    "NAME_FIXED": 4,
    "LLM_REJECTED": 5,
    "LLM_FIXED": 6,
    "HUMAN_REVIEW_REQUIRED": 7,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Conservative ASR CSV refinement agent.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--input", dest="input_csv", help="Input CSV path")
    parser.add_argument("--output", dest="output_csv", help="Cleaned output CSV path")
    parser.add_argument("--report", dest="quality_report", help="Quality report CSV path")
    parser.add_argument("--model", help="Model alias or concrete model name. Built-in aliases: flash, pro")
    parser.add_argument("--disable-llm", action="store_true", help="Disable DeepSeek/LLM refinement")
    parser.add_argument("--metrics", dest="metrics_path", help="Optional JSON metrics output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    config = load_config(resolve_project_path(project_root, args.config))
    if args.input_csv:
        config["paths"]["input_csv"] = args.input_csv
    if args.output_csv:
        config["paths"]["output_csv"] = args.output_csv
    if args.quality_report:
        config["paths"]["quality_report"] = args.quality_report
    if args.model:
        config["model"]["model_name"] = resolve_model_alias(config, args.model)
    if args.disable_llm:
        config["llm"]["enable"] = False

    summary = run_pipeline(config, project_root)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    metrics_path = args.metrics_path
    if metrics_path:
        path = resolve_project_path(project_root, metrics_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def run_pipeline(config: dict[str, Any], project_root: Path) -> dict[str, Any]:
    paths = config.get("paths", {})
    columns = config.get("columns", {})
    text_column = str(columns.get("text_column", "text_edited"))
    error_column = str(columns.get("error_column", "recognition_errors"))

    input_path = resolve_project_path(project_root, paths.get("input_csv", "input.csv"))
    output_path = resolve_project_path(project_root, paths.get("output_csv", "outputs/output_cleaned.csv"))
    report_path = resolve_project_path(project_root, paths.get("quality_report", "outputs/quality_report.csv"))
    env_path = resolve_project_path(project_root, paths.get("env_file", ".env"))
    load_env_file(env_path)

    csv_data = read_csv(input_path)
    validate_input_columns(csv_data.fieldnames, text_column, error_column)
    original_rows = [dict(row) for row in csv_data.rows]
    output_rows = [dict(row) for row in csv_data.rows]

    metrics = Metrics()
    metrics.inc("total_rows", len(output_rows))
    classifier = SegmentValueClassifier(config)
    rule_cleaner = RuleCleaner(config)
    dictionaries = build_dictionaries(config, project_root)
    error_detector = ErrorTypeDetector(config, project_root)
    selector = CandidatePolicySelector(config)
    guard = RefinementGuard(config)

    reports: list[ReportRow] = []
    candidate_map: dict[int, LLMCandidate] = {}
    decision_map: dict[int, CandidatePolicyDecision] = {}

    for row_id, row in enumerate(output_rows, start=1):
        original_text = row.get(text_column, "") or ""
        report = ReportRow(
            row_id=row_id,
            audio_file=row.get("audio_file", ""),
            timestamp=row.get("timestamp", ""),
            label_type=row.get("label_type", ""),
            original_text=original_text,
            final_text=original_text,
        )
        classification = classifier.classify(row, text_column)
        report.issue_tags.update(classification.issue_tags)
        report.need_human_review = classification.need_human_review
        report.notes.extend(classification.notes)
        error_analysis = error_detector.detect(row, original_text, classification, error_column)
        report.issue_tags.update(error_analysis.issue_tags)
        report.notes.extend(error_analysis.notes)

        if classification.skip_all_cleaning:
            decision = selector.assess(row_id, row, original_text, original_text, classification, error_analysis, False)
            decision_map[row_id] = decision
            apply_candidate_decision(report, decision)
            report.action = "SKIP"
            reports.append(report)
            metrics.inc("skipped_rows")
            record_policy_metrics(metrics, decision)
            for tag in classification.issue_tags:
                metrics.inc(f"tag_{tag}")
            for tag in error_analysis.issue_tags:
                metrics.inc(f"tag_{tag}")
            continue

        current_text = original_text
        changed_by_rules = False
        if current_text.strip():
            clean_result = rule_cleaner.clean(current_text)
            if clean_result.text != current_text:
                current_text = clean_result.text
                row[text_column] = current_text
                row[error_column] = merge_error_notes(row.get(error_column, ""), clean_result.edits, clean_result.notes)
                changed_by_rules = True
                set_action(report, "RULE_FIXED")
                metrics.inc("rule_fixed_rows")

            for action_name, corrector in dictionaries:
                result = corrector.correct(current_text)
                if result.text != current_text:
                    current_text = result.text
                    row[text_column] = current_text
                    row[error_column] = merge_error_notes(row.get(error_column, ""), result.edits, result.notes)
                    changed_by_rules = True
                    set_action(report, action_name)
                    metrics.inc(action_name.lower() + "_rows")

        report.final_text = current_text
        if report.action == "UNCHANGED" and current_text == original_text:
            metrics.inc("unchanged_rows")

        decision = selector.assess(row_id, row, original_text, current_text, classification, error_analysis, changed_by_rules)
        decision_map[row_id] = decision
        apply_candidate_decision(report, decision)
        if decision.llm_policy == "HUMAN_REVIEW_ONLY":
            report.need_human_review = True
            report.issue_tags.add("NEEDS_HUMAN_REVIEW")
            set_action(report, "HUMAN_REVIEW_REQUIRED")
        if decision.candidate:
            candidate_map[row_id] = decision.candidate
        record_policy_metrics(metrics, decision)

        for tag in classification.issue_tags:
            metrics.inc(f"tag_{tag}")
        for tag in error_analysis.issue_tags:
            metrics.inc(f"tag_{tag}")
        reports.append(report)

    selected_candidates, capped_candidates = selector.cap_candidates(len(output_rows), list(candidate_map.values()))
    mark_capped_candidates(capped_candidates, reports, decision_map, metrics, selector.llm_cap_exceeded_action)
    llm_enabled = bool(config.get("llm", {}).get("enable", True))
    api_key = get_api_key(config)
    if llm_enabled and api_key and selected_candidates:
        run_llm_refinement(
            config=config,
            project_root=project_root,
            api_key=api_key,
            candidates=selected_candidates,
            output_rows=output_rows,
            reports=reports,
            text_column=text_column,
            error_column=error_column,
            guard=guard,
            metrics=metrics,
        )
    else:
        if not llm_enabled:
            metrics.inc("llm_disabled")
        elif not api_key:
            metrics.inc("llm_missing_api_key")
        metrics.inc("llm_candidate_rows", len(selected_candidates))

    for report, row in zip(reports, output_rows):
        report.final_text = row.get(text_column, "") or ""
        if report.need_human_review and report.action in {"UNCHANGED", "SKIP"}:
            set_action(report, "HUMAN_REVIEW_REQUIRED")
            metrics.inc("human_review_rows")

    validate_output_integrity(original_rows, output_rows, csv_data.fieldnames, csv_data.fieldnames)
    write_csv(output_path, CsvData(output_rows, csv_data.fieldnames, csv_data.encoding, csv_data.lineterminator), output_rows)
    written = read_csv(output_path)
    validate_output_integrity(original_rows, written.rows, csv_data.fieldnames, written.fieldnames)
    write_quality_report(report_path, reports)

    summary = metrics.as_dict()
    summary.update(
        {
            "input_csv": str(input_path),
            "output_csv": str(output_path),
            "quality_report": str(report_path),
            "llm_selected_rows": len(selected_candidates),
            "llm_selected_ratio": round(len(selected_candidates) / max(len(output_rows), 1), 4),
            "model_name": str(config.get("model", {}).get("model_name", "")),
        }
    )
    return summary


def build_dictionaries(config: dict[str, Any], project_root: Path) -> list[tuple[str, DictionaryCorrector]]:
    rules = config.get("rules", {})
    paths = config.get("dictionaries", {})
    correctors: list[tuple[str, DictionaryCorrector]] = []
    if rules.get("enable_correction_dictionary", True):
        correctors.append(
            (
                "DICT_FIXED",
                DictionaryCorrector(resolve_project_path(project_root, paths.get("correction_map", "")), "常见错词修正"),
            )
        )
    if rules.get("enable_domain_dictionary", True):
        correctors.append(
            (
                "DICT_FIXED",
                DictionaryCorrector(resolve_project_path(project_root, paths.get("domain_terms", "")), "领域词修正"),
            )
        )
    if rules.get("enable_name_dictionary", True):
        correctors.append(
            (
                "NAME_FIXED",
                DictionaryCorrector(resolve_project_path(project_root, paths.get("name_aliases", "")), "姓名修正"),
            )
        )
    return correctors


def run_llm_refinement(
    config: dict[str, Any],
    project_root: Path,
    api_key: str,
    candidates: list[LLMCandidate],
    output_rows: list[dict[str, str]],
    reports: list[ReportRow],
    text_column: str,
    error_column: str,
    guard: RefinementGuard,
    metrics: Metrics,
) -> None:
    paths = config.get("paths", {})
    prompt_path = resolve_project_path(project_root, config.get("llm", {}).get("prompt_file", ""))
    prompt = prompt_path.read_text(encoding="utf-8")
    client = DeepSeekClient(
        config=config,
        api_key=api_key,
        prompt=prompt,
        cache_path=resolve_project_path(project_root, paths.get("llm_cache", "outputs/llm_cache.json")),
        log_path=resolve_project_path(project_root, paths.get("llm_log", "outputs/llm_calls.jsonl")),
        metrics=metrics,
    )
    refinements = client.refine(candidates)
    report_by_id = {report.row_id: report for report in reports}
    candidate_by_id = {candidate.row_id: candidate for candidate in candidates}

    for row_id, candidate in candidate_by_id.items():
        report = report_by_id[row_id]
        report.used_llm = True
        metrics.inc("llm_candidate_rows")
        refinement = refinements.get(row_id)
        if not refinement:
            set_action(report, "LLM_REJECTED")
            report.need_human_review = True
            report.issue_tags.update({"OVER_REFINEMENT_RISK", "NEEDS_HUMAN_REVIEW"})
            report.notes.append("LLM returned no parseable result")
            metrics.inc("llm_rejected_rows")
            continue
        report.confidence = f"{refinement.confidence:.2f}"
        decision = guard.evaluate(candidate.text, refinement.refined_text, refinement.confidence)
        report.guard_decision = decision.reason
        if decision.accepted:
            row = output_rows[row_id - 1]
            if refinement.refined_text != row.get(text_column, ""):
                row[text_column] = refinement.refined_text
                notes = [] if refinement.edits else ["[LLM保守修正]"]
                row[error_column] = merge_error_notes(row.get(error_column, ""), refinement.edits, notes)
                set_action(report, "LLM_FIXED")
                metrics.inc("llm_fixed_rows")
            else:
                report.notes.append("LLM kept text unchanged")
        else:
            set_action(report, "LLM_REJECTED")
            report.need_human_review = True
            report.issue_tags.update(decision.issue_tags)
            report.notes.append(f"LLM rejected: {decision.reason}")
            metrics.inc("llm_rejected_rows")


def set_action(report: ReportRow, action: str) -> None:
    if ACTION_PRIORITY[action] >= ACTION_PRIORITY.get(report.action, 0):
        report.action = action


def apply_candidate_decision(report: ReportRow, decision: CandidatePolicyDecision) -> None:
    report.sop_label = decision.sop_label
    report.error_types = set(decision.error_types)
    report.primary_error_type = decision.primary_error_type
    report.llm_policy = decision.llm_policy
    report.selector_reason = decision.selector_reason
    report.selection_score = f"{decision.selection_score:.4f}" if decision.selection_score else ""


def record_policy_metrics(metrics: Metrics, decision: CandidatePolicyDecision) -> None:
    metrics.inc(f"sop_label_{decision.sop_label}_rows")
    metrics.inc(f"llm_policy_{decision.llm_policy.lower()}_rows")
    for error_type in decision.error_types:
        metrics.inc(f"error_type_{error_type}_rows")


def mark_capped_candidates(
    capped_candidates: list[LLMCandidate],
    reports: list[ReportRow],
    decisions: dict[int, CandidatePolicyDecision],
    metrics: Metrics,
    cap_action: str,
) -> None:
    if not capped_candidates:
        return
    report_by_id = {report.row_id: report for report in reports}
    for candidate in capped_candidates:
        report = report_by_id.get(candidate.row_id)
        decision = decisions.get(candidate.row_id)
        if not report or not decision:
            continue
        decision.llm_policy = "LLM_CAP_EXCEEDED"
        report.llm_policy = "LLM_CAP_EXCEEDED"
        report.need_human_review = True
        report.issue_tags.update({"LLM_CAP_EXCEEDED", "NEEDS_HUMAN_REVIEW"})
        report.notes.append("LLM candidate exceeded configured cap")
        set_action(report, cap_action if cap_action in ACTION_PRIORITY else "HUMAN_REVIEW_REQUIRED")
        metrics.inc("llm_cap_exceeded_rows")


if __name__ == "__main__":
    main()
