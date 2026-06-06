from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.config import DEFAULT_CONFIG
from src.csv_io import read_csv
from src.deepseek_client import DeepSeekClient
from src.dictionary_corrector import DictionaryCorrector
from src.metrics import Metrics
from src.pipeline_types import Edit, LLMCandidate, LLMRefinement
from src.refinement_guard import RefinementGuard
from src.rule_cleaner import RuleCleaner
from src.validators import validate_output_integrity


class FakeDeepSeekClient(DeepSeekClient):
    def _call_batch(self, batch):  # type: ignore[no-untyped-def]
        return [
            LLMRefinement(row_id=999, refined_text="污染缓存", confidence=0.99),
            LLMRefinement(row_id=batch[0].row_id, refined_text="我在积木区吗？", confidence=0.99),
        ]


class ComponentTests(unittest.TestCase):
    def test_rule_cleaner_keeps_oral_text_and_adds_punctuation(self) -> None:
        cleaner = RuleCleaner(DEFAULT_CONFIG)
        result = cleaner.clean("  你们坐好了没有吗  ")
        self.assertEqual(result.text, "你们坐好了没有吗？")
        self.assertIn("[空格清理]", result.notes)
        self.assertIn("[标点修正]", result.notes)

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


if __name__ == "__main__":
    unittest.main()
