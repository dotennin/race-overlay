import json
import mimetypes
import subprocess
from json import JSONDecodeError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from race_overlay.editor_preview import (
    StaleHudSaveError,
    StaleProjectSaveError,
    _validate_preview_dimensions,
    build_editor_state,
    editor_render_snapshot,
    load_editor_config,
    render_preview_payload,
    render_preview_png,
    save_editor_preset_payload,
    save_editor_project_payload,
    save_video_rotation_payload,
    save_editor_payload,
    select_editor_preset,
)
from race_overlay.editor_render import EditorRenderJobManager, RenderJobAlreadyRunningError
from race_overlay.editor_render import RenderPreviewToggleInactiveError
from race_overlay.pipeline import run_pipeline
from race_overlay.video_library import project_video_map

_ACTIVE_SERVERS: list[ThreadingHTTPServer] = []
_ACTIVE_THREADS: list[Thread] = []
_RENDER_JOB_MANAGER = EditorRenderJobManager()


class NativePickerUnavailableError(RuntimeError):
    """Raised when the local environment cannot open a native picker."""


def _run_osascript(script: str) -> str:
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - macOS-specific dependency
        raise NativePickerUnavailableError("native picker is unavailable in this environment") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        if "User canceled" in stderr:
            return ""
        raise NativePickerUnavailableError(stderr or "native picker is unavailable in this environment") from exc
    return completed.stdout.strip()


def _pick_single_path(prompt: str, script_body: str) -> str | None:
    output = _run_osascript(
        f'try\nset pickedItem to ({script_body})\nreturn POSIX path of pickedItem\non error errMsg number errNum\nerror errMsg number errNum\nend try'
    )
    if not output:
        return None
    return output.splitlines()[0].strip().strip('"')


def _pick_multiple_paths(prompt: str) -> list[str]:
    output = _run_osascript(
        f'try\nset chosenFiles to choose file with prompt "{prompt}" multiple selections allowed true\nset outputLines to {{}}\nrepeat with chosenFile in chosenFiles\nset end of outputLines to POSIX path of chosenFile\nend repeat\nset AppleScript\'s text item delimiters to linefeed\nreturn outputLines as text\non error errMsg number errNum\nerror errMsg number errNum\nend try'
    )
    if not output:
        return []
    return [line.strip().strip('"') for line in output.splitlines() if line.strip()]


def pick_project_config_value(field: str) -> dict[str, object]:
    if field == "activity_file":
        value = _pick_single_path(
            "Choose activity file",
            'choose file with prompt "Choose activity file"',
        )
    elif field == "video_globs":
        value = _pick_multiple_paths("Choose video files")
    elif field == "output_dir":
        value = _pick_single_path(
            "Choose output folder",
            'choose folder with prompt "Choose output folder"',
        )
    else:
        raise ValueError(f"unsupported picker field: {field}")
    return {"field": field, "value": value}


def _parse_byte_range(value: str, size: int) -> tuple[int, int]:
    if size <= 0:
        raise ValueError("invalid byte range")
    if not value.startswith("bytes=") or "," in value:
        raise ValueError("unsupported byte range")
    spec = value[6:]
    if "-" not in spec:
        raise ValueError("invalid byte range")
    start_text, end_text = spec.split("-", 1)
    if not start_text:
        try:
            suffix_length = int(end_text)
        except ValueError as exc:
            raise ValueError("invalid byte range") from exc
        if suffix_length <= 0:
            raise ValueError("invalid byte range")
        start = max(size - suffix_length, 0)
        return start, size - 1
    try:
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
    except ValueError as exc:
        raise ValueError("invalid byte range") from exc
    if start < 0 or start >= size or end < start:
        raise ValueError("invalid byte range")
    return start, min(end, size - 1)


def _build_handler(config_path: Path, width: int, height: int) -> type[BaseHTTPRequestHandler]:
    class EditorHandler(BaseHTTPRequestHandler):
        def _write_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_project_video(self, request_path: str, *, head_only: bool) -> bool:
            prefix = "/api/videos/"
            if not request_path.startswith(prefix):
                return False
            video_identifier = request_path[len(prefix):]
            if not video_identifier or "/" in video_identifier:
                self.send_response(404)
                self.end_headers()
                return True
            try:
                config = load_editor_config(config_path)
                video_path = project_video_map(
                    config_path,
                    config.video_globs,
                ).get(video_identifier)
            except (OSError, ValueError):
                video_path = None
            if video_path is None:
                self.send_response(404)
                self.end_headers()
                return True
            size = video_path.stat().st_size
            range_header = self.headers.get("Range")
            status = 200
            start = 0
            end = size - 1
            if range_header:
                try:
                    start, end = _parse_byte_range(range_header, size)
                except ValueError:
                    self.send_response(416)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return True
                status = 206
            length = size if status == 200 else end - start + 1
            content_type = mimetypes.guess_type(video_path.name)[0] or "application/octet-stream"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if not head_only and length:
                with video_path.open("rb") as source:
                    source.seek(start)
                    remaining = length
                    while remaining:
                        chunk = source.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            return True

        def do_GET(self) -> None:
            request_path = urlparse(self.path).path
            if self._serve_project_video(request_path, head_only=False):
                return
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
            if request_path == "/api/render/preview.png":
                payload = _RENDER_JOB_MANAGER.latest_preview()
                if payload is None:
                    self.send_response(204)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

        def do_HEAD(self) -> None:
            request_path = urlparse(self.path).path
            if self._serve_project_video(request_path, head_only=True):
                return
            self.send_response(404)
            self.end_headers()

        def do_PUT(self) -> None:
            request_path = urlparse(self.path).path
            prefix = "/api/videos/"
            suffix = "/rotation"
            if not request_path.startswith(prefix) or not request_path.endswith(suffix):
                self.send_response(404)
                self.end_headers()
                return
            video_identifier = request_path[len(prefix):-len(suffix)]
            if not video_identifier or "/" in video_identifier:
                self.send_response(404)
                self.end_headers()
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length < 0:
                    raise ValueError
            except ValueError:
                self._write_json(400, {"error": "invalid Content-Length header"})
                return
            try:
                payload = json.loads(
                    self.rfile.read(content_length) or b"{}",
                    parse_constant=_reject_invalid_json_constant,
                )
            except (JSONDecodeError, ValueError):
                self._write_json(400, {"error": "invalid JSON payload"})
                return
            try:
                result = save_video_rotation_payload(
                    config_path,
                    video_identifier,
                    payload,
                )
            except StaleProjectSaveError as exc:
                project = build_editor_state(
                    load_editor_config(config_path),
                    width,
                    height,
                    config_path=config_path,
                )["project"]
                self._write_json(
                    409,
                    {"error": str(exc), "project": project},
                )
                return
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                return
            except (TypeError, ValueError) as exc:
                self._write_json(400, {"error": str(exc)})
                return
            except OSError as exc:
                self._write_json(500, {"error": str(exc)})
                return
            self._write_json(200, result)

        def do_POST(self) -> None:
            request_path = urlparse(self.path).path
            if request_path not in {
                "/api/config",
                "/api/preview",
                "/api/project",
                "/api/project/picker",
                "/api/presets/save",
                "/api/presets/select",
                "/api/render",
                "/api/render/preview",
                "/api/render/cancel",
            }:
                self.send_response(404)
                self.end_headers()
                return
            if request_path == "/api/render/cancel":
                try:
                    state = _RENDER_JOB_MANAGER.cancel()
                except ValueError as exc:
                    self._write_json(409, {"error": str(exc)})
                    return
                self._write_json(200, state)
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
            if request_path == "/api/render/preview":
                try:
                    if not isinstance(payload, dict):
                        raise ValueError("preview payload must be a JSON object")
                    enabled = payload.get("enabled")
                    if not isinstance(enabled, bool):
                        raise ValueError("preview enabled flag must be a boolean")
                    state = _RENDER_JOB_MANAGER.set_preview_enabled(enabled)
                except RenderPreviewToggleInactiveError as exc:
                    self._write_json(409, {"error": str(exc)})
                    return
                except ValueError as exc:
                    self._write_json(400, {"error": str(exc)})
                    return
                self._write_json(200, state)
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
            if request_path == "/api/presets/save":
                try:
                    if not isinstance(payload, dict):
                        raise ValueError("preset payload must be a JSON object")
                    save_editor_preset_payload(config_path, payload)
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
                return
            if request_path == "/api/presets/select":
                try:
                    if not isinstance(payload, dict):
                        raise ValueError("preset selection payload must be a JSON object")
                    select_editor_preset(config_path, payload)
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
    handler = _build_handler(config_path, width, height)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 10086), handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    _ACTIVE_SERVERS.append(server)
    _ACTIVE_THREADS.append(thread)
    return f"http://127.0.0.1:{server.server_port}"
