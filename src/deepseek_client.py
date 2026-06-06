from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .metrics import Metrics
from .pipeline_types import Edit, LLMCandidate, LLMRefinement


class LLMCache:
    def __init__(self, path: str | Path, enabled: bool = True):
        self.path = Path(path)
        self.enabled = enabled
        self.values: dict[str, dict[str, Any]] = {}
        if self.enabled and self.path.exists():
            try:
                self.values = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.values = {}

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return self.values.get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self.values[key] = value

    def save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.values, ensure_ascii=False, indent=2), encoding="utf-8")


class DeepSeekClient:
    def __init__(
        self,
        config: dict[str, Any],
        api_key: str,
        prompt: str,
        cache_path: str | Path,
        log_path: str | Path,
        metrics: Metrics,
    ):
        model_config = config.get("model", {})
        llm_config = config.get("llm", {})
        self.model_name = str(model_config.get("model_name", "deepseek-v4-flash"))
        self.api_base = str(model_config.get("api_base", "https://api.deepseek.com")).rstrip("/")
        self.api_key = api_key
        self.batch_size = int(model_config.get("batch_size", 30))
        self.timeout = int(model_config.get("timeout", 60))
        self.max_retries = int(model_config.get("max_retries", 3))
        self.temperature = float(model_config.get("temperature", 0))
        self.prompt = prompt
        self.cache = LLMCache(cache_path, bool(llm_config.get("cache_enabled", True)))
        self.log_path = Path(log_path)
        self.metrics = metrics

    def refine(self, candidates: list[LLMCandidate]) -> dict[int, LLMRefinement]:
        results: dict[int, LLMRefinement] = {}
        missing: list[LLMCandidate] = []
        for candidate in candidates:
            cached = self.cache.get(self._cache_key(candidate.text))
            if cached:
                self.metrics.inc("llm_cache_hits")
                parsed = self._result_from_payload(candidate.row_id, cached)
                if parsed:
                    results[candidate.row_id] = parsed
                    continue
            missing.append(candidate)

        for start in range(0, len(missing), self.batch_size):
            batch = missing[start : start + self.batch_size]
            batch_results = self._call_batch(batch)
            expected_text_by_row_id = {candidate.row_id: candidate.text for candidate in batch}
            for result in batch_results:
                candidate_text = expected_text_by_row_id.get(result.row_id)
                if candidate_text is None:
                    self.metrics.inc("llm_unexpected_row_ids")
                    continue
                results[result.row_id] = result
                self.cache.set(self._cache_key(candidate_text), self._payload_from_result(result))
        self.cache.save()
        return results

    def _call_batch(self, batch: list[LLMCandidate]) -> list[LLMRefinement]:
        self.metrics.inc("llm_calls")
        self.metrics.inc("llm_processed_rows", len(batch))
        payload = self._request_payload(batch)
        last_error = ""
        for attempt in range(self.max_retries + 1):
            if attempt:
                self.metrics.inc("llm_retries")
                time.sleep(min(2**attempt, 10))
            try:
                response = self._post_json(payload)
                usage = response.get("usage") or {}
                self.metrics.update_llm_usage(usage)
                content = response["choices"][0]["message"]["content"]
                parsed = self._parse_content(content)
                self._log_call(batch, True, usage, "")
                return parsed
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
        self.metrics.inc("llm_failed_calls")
        self._log_call(batch, False, {}, last_error)
        return []

    def _request_payload(self, batch: list[LLMCandidate]) -> dict[str, Any]:
        rows = [{"row_id": item.row_id, "text": item.text} for item in batch]
        return {
            "model": self.model_name,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": self.prompt},
                {
                    "role": "user",
                    "content": "请按要求保守清洗以下 ASR 文本，输出严格 JSON 数组：\n"
                    + json.dumps(rows, ensure_ascii=False),
                },
            ],
        }

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = self.api_base
        if not endpoint.endswith("/chat/completions"):
            endpoint = endpoint.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek HTTP {exc.code}: {body}") from exc

    def _parse_content(self, content: str) -> list[LLMRefinement]:
        raw = content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.metrics.inc("llm_json_parse_failures")
            raise RuntimeError(f"Failed to parse LLM JSON: {exc}") from exc
        if isinstance(parsed, dict) and "results" in parsed:
            parsed = parsed["results"]
        if not isinstance(parsed, list):
            self.metrics.inc("llm_json_parse_failures")
            raise RuntimeError("LLM JSON must be a list or an object containing results")
        results: list[LLMRefinement] = []
        for item in parsed:
            result = self._result_from_payload(None, item)
            if result:
                results.append(result)
        return results

    def _result_from_payload(self, fallback_row_id: int | None, item: dict[str, Any]) -> LLMRefinement | None:
        if not isinstance(item, dict):
            return None
        row_id_value = fallback_row_id if fallback_row_id is not None else item.get("row_id")
        try:
            row_id = int(row_id_value)
        except (TypeError, ValueError):
            return None
        edits: list[Edit] = []
        raw_edits = item.get("edits") or []
        if isinstance(raw_edits, list):
            for edit in raw_edits:
                if not isinstance(edit, dict):
                    continue
                edits.append(
                    Edit(
                        source=str(edit.get("from", "")),
                        target=str(edit.get("to", "")),
                        edit_type=self._normalize_edit_type(str(edit.get("type") or "")),
                        reason=str(edit.get("reason") or "LLM保守修正"),
                    )
                )
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        return LLMRefinement(
            row_id=row_id,
            refined_text=str(item.get("refined_text", "")),
            edits=edits,
            confidence=confidence,
            raw=item,
        )

    def _payload_from_result(self, result: LLMRefinement) -> dict[str, Any]:
        return {
            "refined_text": result.refined_text,
            "edits": [
                {"from": edit.source, "to": edit.target, "type": edit.edit_type, "reason": edit.reason}
                for edit in result.edits
            ],
            "confidence": result.confidence,
        }

    def _normalize_edit_type(self, value: str) -> str:
        mapping = {
            "replace": "LLM替换",
            "insert": "LLM插入",
            "delete": "LLM删除",
            "punctuation": "标点修正",
            "punctuation_fix": "标点修正",
            "asr_error": "ASR错词修正",
        }
        return mapping.get(value.strip(), value.strip() or "LLM保守修正")

    def _cache_key(self, text: str) -> str:
        digest = hashlib.sha256()
        digest.update(self.model_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(self.prompt.encode("utf-8")).hexdigest().encode("ascii"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        return digest.hexdigest()

    def _log_call(self, batch: list[LLMCandidate], success: bool, usage: dict[str, Any], error: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "model": self.model_name,
            "row_ids": [item.row_id for item in batch],
            "success": success,
            "usage": usage,
            "error": error,
            "timestamp": int(time.time()),
        }
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
