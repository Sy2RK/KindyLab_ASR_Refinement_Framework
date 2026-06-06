from __future__ import annotations

import csv
import copy
import tempfile
import unittest
from pathlib import Path

from main import run_pipeline
from server import run_refinement_job
from src.config import DEFAULT_CONFIG
from src.csv_io import read_csv
from src.deepseek_client import DeepSeekClient
from src.dictionary_corrector import DictionaryCorrector
from src.error_type_detector import ErrorTypeDetector
from src.llm_selector import CandidatePolicySelector
from src.metrics import Metrics
from src.pipeline_types import Edit, LLMCandidate, LLMRefinement
from src.refinement_guard import RefinementGuard
from src.rule_cleaner import RuleCleaner
from src.segment_classifier import SegmentValueClassifier
from src.validators import validate_output_integrity


class FakeDeepSeekClient(DeepSeekClient):
    def _call_batch(self, batch):  # type: ignore[no-untyped-def]
        return [
            LLMRefinement(row_id=999, refined_text="污染缓存", confidence=0.99),
            LLMRefinement(row_id=batch[0].row_id, refined_text="我在积木区吗？", confidence=0.99),
        ]


class ComponentTests(unittest.TestCase):
    def candidate_decision(self, row: dict[str, str], changed_by_rules: bool = False, current_text: str | None = None):
        classifier = SegmentValueClassifier(DEFAULT_CONFIG)
        detector = ErrorTypeDetector(DEFAULT_CONFIG, Path(__file__).resolve().parents[1])
        selector = CandidatePolicySelector(DEFAULT_CONFIG)
        classification = classifier.classify(row, "text_edited")
        analysis = detector.detect(row, row.get("text_edited", ""), classification, "recognition_errors")
        return selector.assess(1, row, row.get("text_edited", ""), current_text or row.get("text_edited", ""), classification, analysis, changed_by_rules)

    def test_rule_cleaner_keeps_oral_text_and_adds_punctuation(self) -> None:
        cleaner = RuleCleaner(DEFAULT_CONFIG)
        result = cleaner.clean("  你们坐好了没有吗  ")
        self.assertEqual(result.text, "你们坐好了没有吗？")
        self.assertIn("[空格清理]", result.notes)
        self.assertIn("[标点修正]", result.notes)

    def test_sop_label_0_short_backchannel_stays_out_of_llm(self) -> None:
        decision = self.candidate_decision({"text_edited": "嗯", "label_type": "student", "recognition_errors": ""})
        self.assertEqual(decision.sop_label, "0")
        self.assertEqual(decision.llm_policy, "KEEP")
        self.assertIsNone(decision.candidate)

    def test_sop_label_1_punctuation_issue_is_optional_llm(self) -> None:
        row = {
            "text_edited": "老师今天我们认识颜色然后我们一起做游戏最后大家分享",
            "label_type": "teacher",
            "recognition_errors": "",
        }
        decision = self.candidate_decision(row)
        self.assertEqual(decision.sop_label, "1")
        self.assertEqual(decision.primary_error_type, "E5")
        self.assertEqual(decision.llm_policy, "OPTIONAL_LLM")
        self.assertIsNotNone(decision.candidate)

    def test_sop_label_2_refinable_domain_error_goes_to_must_llm(self) -> None:
        decision = self.candidate_decision({"text_edited": "老师今天建狗区", "label_type": "teacher", "recognition_errors": ""})
        self.assertEqual(decision.sop_label, "2")
        self.assertEqual(decision.primary_error_type, "E1")
        self.assertEqual(decision.llm_policy, "MUST_LLM")

    def test_overlap_and_unreadable_are_human_review_only(self) -> None:
        overlap = self.candidate_decision({"text_edited": "老师：现在我们……儿童：我要……老师：", "label_type": "student", "recognition_errors": ""})
        unreadable = self.candidate_decision({"text_edited": "今天们玩那个好了去积积老师。", "label_type": "student", "recognition_errors": ""})
        self.assertEqual(overlap.llm_policy, "HUMAN_REVIEW_ONLY")
        self.assertEqual(overlap.primary_error_type, "E6")
        self.assertEqual(unreadable.llm_policy, "HUMAN_REVIEW_ONLY")
        self.assertEqual(unreadable.primary_error_type, "E7")

    def test_error_type_priority_is_stable(self) -> None:
        decision = self.candidate_decision({"text_edited": "老师今天建狗区老师老师老师", "label_type": "teacher", "recognition_errors": ""})
        self.assertEqual(decision.primary_error_type, "E1")
        self.assertIn("E4", decision.error_types)

    def test_llm_cap_marks_lower_priority_candidates(self) -> None:
        selector = CandidatePolicySelector(DEFAULT_CONFIG)
        selected, capped = selector.cap_candidates(
            4,
            [
                LLMCandidate(row_id=1, text="老师今天建狗区", score=0.9, reason="must", sop_label="2", error_types={"E1"}, primary_error_type="E1", llm_policy="MUST_LLM", selection_score=0.9),
                LLMCandidate(row_id=2, text="老师今天我们认识颜色然后我们一起做游戏最后大家分享", score=0.6, reason="optional", sop_label="1", error_types={"E5"}, primary_error_type="E5", llm_policy="OPTIONAL_LLM", selection_score=0.6),
            ],
        )
        self.assertEqual([item.row_id for item in selected], [1])
        self.assertEqual([item.row_id for item in capped], [2])

    def test_dictionary_corrector_applies_enabled_entries_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dict.yaml"
            path.write_text(
                """
corrections:
  - wrong: 金木
    correct: 积木
    type: 领域词修正
  - wrong: 叔叔
    correct: 书书
    type: 姓名修正
    enabled: false
""",
                encoding="utf-8",
            )
            corrector = DictionaryCorrector(path, "测试")
            result = corrector.correct("我在金木区，叔叔也在。")
            self.assertEqual(result.text, "我在积木区，叔叔也在。")
            self.assertEqual(len(result.edits), 1)

    def test_guard_rejects_over_refinement(self) -> None:
        guard = RefinementGuard(DEFAULT_CONFIG)
        decision = guard.evaluate("你们坐好了没有呀？", "请小朋友们保持良好的坐姿。", 0.95)
        self.assertFalse(decision.accepted)

    def test_csv_integrity_validator_catches_immutable_change(self) -> None:
        original = [{"audio_file": "1.wav", "text_edited": "金木", "recognition_errors": "", "timestamp": "t"}]
        output = [{"audio_file": "2.wav", "text_edited": "积木", "recognition_errors": "", "timestamp": "t"}]
        with self.assertRaises(ValueError):
            validate_output_integrity(original, output, ["audio_file", "text_edited", "recognition_errors", "timestamp"], ["audio_file", "text_edited", "recognition_errors", "timestamp"])

    def test_read_csv_handles_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["text_edited", "recognition_errors"])
                writer.writerow(["金木", ""])
            data = read_csv(path)
            self.assertEqual(data.fieldnames, ["text_edited", "recognition_errors"])
            self.assertEqual(data.encoding, "utf-8-sig")

    def test_llm_cache_reuses_text_without_reusing_row_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            log_path = Path(temp_dir) / "calls.jsonl"
            client = DeepSeekClient(
                DEFAULT_CONFIG,
                api_key="test",
                prompt="prompt",
                cache_path=cache_path,
                log_path=log_path,
                metrics=Metrics(),
            )
            cached = LLMRefinement(
                row_id=1,
                refined_text="我在积木区吗？",
                edits=[Edit("金木", "积木", "常见错词修正")],
                confidence=0.95,
            )
            client.cache.set(client._cache_key("我在金木区吗"), client._payload_from_result(cached))
            results = client.refine([LLMCandidate(row_id=7, text="我在金木区吗", score=1, reason="test")])
            self.assertIn(7, results)
            self.assertEqual(results[7].row_id, 7)
            self.assertNotIn(1, results)

    def test_llm_ignores_unexpected_batch_row_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            metrics = Metrics()
            client = FakeDeepSeekClient(
                DEFAULT_CONFIG,
                api_key="test",
                prompt="prompt",
                cache_path=Path(temp_dir) / "cache.json",
                log_path=Path(temp_dir) / "calls.jsonl",
                metrics=metrics,
            )
            results = client.refine([LLMCandidate(row_id=3, text="我在金木区吗", score=1, reason="test")])
            self.assertEqual(list(results), [3])
            self.assertEqual(metrics.as_dict().get("llm_unexpected_row_ids"), 1)

    def test_pipeline_without_llm_still_writes_candidate_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "input.csv"
            output_path = temp_path / "output.csv"
            report_path = temp_path / "report.csv"
            headers = [
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
            with input_path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=headers)
                writer.writeheader()
                writer.writerow(
                    {
                        "annotator": "tester",
                        "source_file": "classroom",
                        "audio_file": "1.wav",
                        "label": "teacher",
                        "label_display": "T",
                        "label_type": "teacher",
                        "teacher_id": "1",
                        "text_edited": "老师今天建狗区",
                        "recognition_errors": "",
                        "timestamp": "t",
                    }
                )
            config = copy.deepcopy(DEFAULT_CONFIG)
            config["paths"]["input_csv"] = str(input_path)
            config["paths"]["output_csv"] = str(output_path)
            config["paths"]["quality_report"] = str(report_path)
            config["llm"]["enable"] = False
            summary = run_pipeline(config, Path(__file__).resolve().parents[1])
            self.assertEqual(summary["llm_selected_rows"], 1)
            report = read_csv(report_path)
            self.assertEqual(report.rows[0]["sop_label"], "2")
            self.assertEqual(report.rows[0]["primary_error_type"], "E1")
            self.assertEqual(report.rows[0]["llm_policy"], "MUST_LLM")

    def test_server_refinement_job_returns_csv_payloads(self) -> None:
        headers = [
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
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.csv"
            with input_path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=headers)
                writer.writeheader()
                writer.writerow(
                    {
                        "annotator": "tester",
                        "source_file": "classroom",
                        "audio_file": "1.wav",
                        "label": "teacher",
                        "label_display": "T",
                        "label_type": "teacher",
                        "teacher_id": "1",
                        "text_edited": "嗯",
                        "recognition_errors": "",
                        "timestamp": "t",
                    }
                )
            payload = run_refinement_job({"csv": input_path.read_text(encoding="utf-8-sig"), "model": "flash"})
        self.assertIn("output_csv", payload)
        self.assertIn("quality_report_csv", payload)
        self.assertEqual(payload["summary"]["total_rows"], 1)


if __name__ == "__main__":
    unittest.main()
