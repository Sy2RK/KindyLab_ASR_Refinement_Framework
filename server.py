from __future__ import annotations

import argparse
import json
import tempfile
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from main import run_pipeline
from src.config import get_api_key, load_config, load_env_file, resolve_model_alias, resolve_project_path


PROJECT_ROOT = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 80 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KindyLab ASR refinement local server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8787, help="Port to bind")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    return parser.parse_args()


def api_status(config_path: str = "config.yaml") -> dict[str, Any]:
    config = load_config(resolve_project_path(PROJECT_ROOT, config_path))
    env_path = resolve_project_path(PROJECT_ROOT, config.get("paths", {}).get("env_file", ".env"))
    load_env_file(env_path)
    model = config.get("model", {})
    return {
        "mode": "real_backend",
        "deepseek_configured": bool(get_api_key(config)),
        "api_key_env": str(model.get("api_key_env") or "DEEPSEEK_API_KEY"),
        "model_name": str(model.get("model_name", "")),
        "model_aliases": model.get("model_aliases", {}),
    }


def run_refinement_job(payload: dict[str, Any], config_path: str = "config.yaml") -> dict[str, Any]:
    csv_text = str(payload.get("csv") or "")
    if not csv_text.strip():
        raise ValueError("CSV content is empty")

    config = load_config(resolve_project_path(PROJECT_ROOT, config_path))
    requested_model = str(payload.get("model") or "").strip()
    if requested_model:
        config["model"]["model_name"] = resolve_model_alias(config, requested_model)

    # The browser uses this endpoint for the real chain, so LLM remains enabled.
    config.setdefault("llm", {})["enable"] = True

    work_root = PROJECT_ROOT / "outputs"
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kindylab_asr_", dir=work_root) as temp_dir:
        job_dir = Path(temp_dir)
        input_path = job_dir / "input.csv"
        output_path = job_dir / "cleaned.csv"
        report_path = job_dir / "quality_report.csv"
        metrics_path = job_dir / "metrics.json"
        input_path.write_text(csv_text, encoding="utf-8")

        config["paths"]["input_csv"] = str(input_path)
        config["paths"]["output_csv"] = str(output_path)
        config["paths"]["quality_report"] = str(report_path)
        config["paths"]["llm_cache"] = str(PROJECT_ROOT / "outputs" / "llm_cache.json")
        config["paths"]["llm_log"] = str(PROJECT_ROOT / "outputs" / "llm_calls.jsonl")

        summary = run_pipeline(config, PROJECT_ROOT)
        metrics_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "summary": summary,
            "output_csv": output_path.read_text(encoding="utf-8-sig"),
            "quality_report_csv": report_path.read_text(encoding="utf-8-sig"),
        }


class KindyLabHandler(SimpleHTTPRequestHandler):
    config_path = "config.yaml"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/status":
            self._send_json(HTTPStatus.OK, api_status(self.config_path))
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/refine":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Invalid request size")
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Request JSON must be an object")
            result = run_refinement_job(payload, self.config_path)
            self._send_json(HTTPStatus.OK, result)
        except Exception as exc:  # noqa: BLE001
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    args = parse_args()
    KindyLabHandler.config_path = args.config
    server = ThreadingHTTPServer((args.host, args.port), KindyLabHandler)
    print(f"KindyLab ASR refinement server: http://{args.host}:{args.port}/frontend/")
    server.serve_forever()


if __name__ == "__main__":
    main()
