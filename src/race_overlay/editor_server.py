import json
from json import JSONDecodeError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from threading import Thread
from tkinter import Tk, filedialog
from urllib.parse import urlparse

from race_overlay.editor_preview import (
    StaleHudSaveError,
    _validate_preview_dimensions,
    build_editor_state,
    editor_render_snapshot,
    load_editor_config,
    render_preview_payload,
    render_preview_png,
    save_editor_project_payload,
    save_editor_payload,
)
from race_overlay.editor_render import EditorRenderJobManager, RenderJobAlreadyRunningError
from race_overlay.pipeline import run_pipeline

_ACTIVE_SERVERS: list[ThreadingHTTPServer] = []
_ACTIVE_THREADS: list[Thread] = []
_RENDER_JOB_MANAGER = EditorRenderJobManager()


class NativePickerUnavailableError(RuntimeError):
    """Raised when the local environment cannot open a native picker."""


def _native_picker_root() -> Tk:
    try:
        root = Tk()
    except Exception as exc:  # pragma: no cover - platform-specific UI failure
        raise NativePickerUnavailableError("native picker is unavailable in this environment") from exc
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    return root


def pick_project_config_value(field: str) -> dict[str, object]:
    root = _native_picker_root()
    try:
        if field == "activity_file":
            value = filedialog.askopenfilename(
                title="Choose activity file",
                filetypes=[("Activity files", "*.fit *.tcx"), ("All files", "*.*")],
            )
        elif field == "video_globs":
            value = list(
                filedialog.askopenfilenames(
                    title="Choose video files",
                    filetypes=[
                        ("Video files", "*.mp4 *.mov *.m4v *.mkv *.avi *.mpeg *.mpg *.mts *.m2ts"),
                        ("All files", "*.*"),
                    ],
                )
            )
        elif field == "output_dir":
            value = filedialog.askdirectory(title="Choose output folder", mustexist=False)
        else:
            raise ValueError(f"unsupported picker field: {field}")
    finally:
        root.destroy()
    return {"field": field, "value": value}


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
                    state = json.dumps(
                        build_editor_state(load_editor_config(config_path), width, height, config_path=config_path)
                    ).encode("utf-8")
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
                    payload = render_preview_png(load_editor_config(config_path), width, height)
                except ValueError as exc:
                    self._write_json(400, {"error": str(exc)})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                self.wfile.write(payload)
                return
            if request_path == "/api/render":
                self._write_json(200, _RENDER_JOB_MANAGER.snapshot())
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:
            request_path = urlparse(self.path).path
            if request_path not in {"/api/config", "/api/preview", "/api/project", "/api/project/picker", "/api/render"}:
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
            if request_path == "/api/preview":
                try:
                    if not isinstance(payload, dict):
                        raise ValueError("HUD config payload must be a JSON object")
                    preview = render_preview_payload(config_path, payload, width, height)
                except (TypeError, ValueError) as exc:
                    self._write_json(400, {"error": str(exc)})
                    return

                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(preview)
                return
            if request_path == "/api/project":
                try:
                    if not isinstance(payload, dict):
                        raise ValueError("project config payload must be a JSON object")
                    save_editor_project_payload(config_path, payload)
                except (TypeError, ValueError) as exc:
                    self._write_json(400, {"error": str(exc)})
                    return
                except OSError as exc:
                    self._write_json(500, {"error": str(exc)})
                    return
                self.send_response(204)
                self.end_headers()
                return
            if request_path == "/api/project/picker":
                try:
                    if not isinstance(payload, dict):
                        raise ValueError("picker payload must be a JSON object")
                    field = payload.get("field")
                    if not isinstance(field, str) or not field:
                        raise ValueError("picker field must be a non-empty string")
                    selection = pick_project_config_value(field)
                except NativePickerUnavailableError as exc:
                    self._write_json(501, {"error": str(exc)})
                    return
                except (TypeError, ValueError) as exc:
                    self._write_json(400, {"error": str(exc)})
                    return
                self._write_json(200, selection)
                return
            if request_path == "/api/render":
                try:
                    if not isinstance(payload, dict):
                        raise ValueError("HUD config payload must be a JSON object")
                    state = _RENDER_JOB_MANAGER.start(
                        payload,
                        build_snapshot=lambda draft_payload: editor_render_snapshot(config_path, draft_payload),
                        run_pipeline=run_pipeline,
                    )
                except RenderJobAlreadyRunningError as exc:
                    self._write_json(409, {"error": str(exc)})
                    return
                except (TypeError, ValueError) as exc:
                    self._write_json(400, {"error": str(exc)})
                    return
                self._write_json(202, state)
                return
            try:
                load_editor_config(config_path)
                if not isinstance(payload, dict):
                    raise ValueError("HUD config payload must be a JSON object")
                save_editor_payload(config_path, payload)
            except StaleHudSaveError as exc:
                self._write_json(409, {"error": str(exc)})
                return
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


def launch_editor(config_path: Path, width: int, height: int) -> str:
    _validate_preview_dimensions(width, height)
    load_editor_config(config_path)
    server = ThreadingHTTPServer(("127.0.0.1", 10086), _build_handler(config_path, width, height))
    thread = Thread(target=server.serve_forever)
    thread.start()
    _ACTIVE_SERVERS.append(server)
    _ACTIVE_THREADS.append(thread)
    return f"http://127.0.0.1:{server.server_port}"
