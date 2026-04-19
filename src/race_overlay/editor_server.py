import json
from json import JSONDecodeError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

import yaml

from race_overlay.config import load_config
from race_overlay.editor_preview import (
    _validate_preview_dimensions,
    build_editor_state,
    render_preview_png,
    save_editor_payload,
)

_ACTIVE_SERVERS: list[ThreadingHTTPServer] = []
_ACTIVE_THREADS: list[Thread] = []


def _build_handler(config_path: Path, width: int, height: int) -> type[BaseHTTPRequestHandler]:
    class EditorHandler(BaseHTTPRequestHandler):
        def _write_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            request_path = urlparse(self.path).path
            if request_path == "/":
                body = files("race_overlay.editor_assets").joinpath("index.html").read_text(encoding="utf-8").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if request_path == "/app.js":
                body = files("race_overlay.editor_assets").joinpath("app.js").read_text(encoding="utf-8").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if request_path == "/styles.css":
                body = files("race_overlay.editor_assets").joinpath("styles.css").read_text(encoding="utf-8").encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/css; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            if request_path == "/api/state":
                try:
                    state = json.dumps(build_editor_state(_load_editor_config(config_path), width, height)).encode("utf-8")
                except ValueError as exc:
                    self._write_json(400, {"error": str(exc)})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(state)
                return
            if request_path == "/api/preview.png":
                try:
                    payload = render_preview_png(_load_editor_config(config_path), width, height)
                except ValueError as exc:
                    self._write_json(400, {"error": str(exc)})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:
            request_path = urlparse(self.path).path
            if request_path != "/api/config":
                self.send_response(404)
                self.end_headers()
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._write_json(400, {"error": "invalid Content-Length header"})
                return
            if content_length < 0:
                self._write_json(400, {"error": "invalid Content-Length header"})
                return
            try:
                payload = json.loads(
                    self.rfile.read(content_length) or b"{}",
                    parse_constant=_reject_invalid_json_constant,
                )
            except JSONDecodeError:
                self._write_json(400, {"error": "invalid JSON payload"})
                return
            except ValueError:
                self._write_json(400, {"error": "invalid JSON payload"})
                return
            try:
                _load_editor_config(config_path)
                if not isinstance(payload, dict):
                    raise ValueError("HUD config payload must be a JSON object")
                save_editor_payload(config_path, payload)
            except (TypeError, ValueError) as exc:
                self._write_json(400, {"error": str(exc)})
                return
            except OSError as exc:
                self._write_json(500, {"error": str(exc)})
                return
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    return EditorHandler


def _reject_invalid_json_constant(value: str) -> object:
    raise ValueError(f"invalid constant {value}")


def _load_editor_config(config_path: Path):
    try:
        return load_config(config_path)
    except FileNotFoundError as exc:
        raise ValueError(f"config file not found: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"config file is not valid YAML: {exc}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"config file is invalid: {exc}") from exc


def launch_editor(config_path: Path, width: int, height: int) -> str:
    _validate_preview_dimensions(width, height)
    _load_editor_config(config_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _build_handler(config_path, width, height))
    thread = Thread(target=server.serve_forever)
    thread.start()
    _ACTIVE_SERVERS.append(server)
    _ACTIVE_THREADS.append(thread)
    return f"http://127.0.0.1:{server.server_port}"
