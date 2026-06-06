from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "model": {
        "provider": "deepseek",
        "model_name": "deepseek-v4-flash",
        "api_base": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_aliases": {
            "flash": "deepseek-v4-flash",
            "pro": "deepseek-v4-pro",
        },
        "batch_size": 30,
        "timeout": 60,
        "max_retries": 3,
        "temperature": 0,
    },
    "paths": {
        "input_csv": "input.csv",
        "output_csv": "outputs/output_cleaned.csv",
        "quality_report": "outputs/quality_report.csv",
        "llm_cache": "outputs/llm_cache.json",
        "llm_log": "outputs/llm_calls.jsonl",
        "env_file": ".env",
    },
    "columns": {
        "text_column": "text_edited",
        "error_column": "recognition_errors",
    },
    "rules": {
        "skip_empty_text": True,
        "skip_short_text": True,
        "short_text_max_length": 4,
        "enable_punctuation_fix": True,
        "enable_domain_dictionary": True,
        "enable_correction_dictionary": True,
        "enable_name_dictionary": True,
        "add_terminal_punctuation": True,
    },
    "dictionaries": {
        "domain_terms": "dictionaries/domain_terms.yaml",
        "name_aliases": "dictionaries/name_aliases.yaml",
        "correction_map": "dictionaries/correction_map.yaml",
    },
    "classifier": {
        "hallucination_student_length": 140,
        "segment_too_long_length": 220,
        "media_keywords": [
            "儿歌",
            "动画片",
            "播放",
            "歌词",
            "广播",
            "音频",
            "音乐",
            "故事机",
            "火箭发射",
            "即将关闭",
            "谨防夹伤",
        ],
    },
    "selector": {
        "min_text_length": 12,
        "max_text_length": 220,
        "max_llm_row_ratio": 0.25,
        "blocked_issue_tags": [
            "EMPTY_TEXT",
            "SHORT_BACKCHANNEL",
            "NOISE_ONLY",
            "MEDIA_MATERIAL",
            "MULTI_SPEAKER_OVERLAP",
            "HALLUCINATION_RISK",
            "NEEDS_HUMAN_REVIEW",
        ],
    },
    "guard": {
        "max_added_ratio": 0.2,
        "max_deleted_ratio": 0.3,
        "max_edit_distance_ratio": 0.4,
        "min_confidence": 0.7,
    },
    "llm": {
        "enable": True,
        "conservative_mode": True,
        "prompt_file": "prompts/conservative_refinement_prompt.txt",
        "cache_enabled": True,
    },
}


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    if config_path:
        path = Path(config_path)
        if path.exists():
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError(
                    "PyYAML is required to read config.yaml. Install requirements.txt first."
                ) from exc
            with path.open("r", encoding="utf-8") as file:
                loaded = yaml.safe_load(file) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"Config file must contain a YAML mapping: {path}")
            config = deep_merge(config, loaded)
    return config


def resolve_project_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


def get_api_key(config: dict[str, Any]) -> str:
    model = config.get("model", {})
    explicit = model.get("api_key") or ""
    if explicit:
        return str(explicit)
    env_name = str(model.get("api_key_env") or "DEEPSEEK_API_KEY")
    return os.getenv(env_name, "")


def load_env_file(path: str | Path) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_model_alias(config: dict[str, Any], requested: str) -> str:
    aliases = config.get("model", {}).get("model_aliases", {}) or {}
    return str(aliases.get(requested, requested))
