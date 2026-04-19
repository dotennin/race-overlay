import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

from race_overlay.config import load_config
from race_overlay.editor_preview import build_editor_state, render_preview_png, save_editor_payload

_ACTIVE_SERVERS: list[ThreadingHTTPServer] = []
_ACTIVE_THREADS: list[Thread] = []


def _build_handler(config_path: Path, width: int, height: int) -> type[BaseHTTPRequestHandler]:
    class EditorHandler(BaseHTTPRequestHandler):
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
                state = json.dumps(build_editor_state(load_config(config_path), width, height)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(state)
                return
            if request_path == "/api/preview.png":
                payload = render_preview_png(load_config(config_path), width, height)
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
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length) or b"{}")
            save_editor_payload(config_path, payload)
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    return EditorHandler


def launch_editor(config_path: Path, width: int, height: int) -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _build_handler(config_path, width, height))
    thread = Thread(target=server.serve_forever)
    thread.start()
    _ACTIVE_SERVERS.append(server)
    _ACTIVE_THREADS.append(thread)
    return f"http://127.0.0.1:{server.server_port}"
