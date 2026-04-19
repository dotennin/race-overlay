import json
import socket
import subprocess
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlparse

import pytest

from race_overlay.config import ProjectConfig, load_config, save_config
from race_overlay.editor_preview import build_editor_state, save_editor_payload
from race_overlay.editor_server import _ACTIVE_SERVERS, _ACTIVE_THREADS, launch_editor
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.hud_schema import serialize_hud_config


def test_build_editor_state_exposes_widgets_for_preview() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    assert state["hud"]["preset"] == "broadcast-runner"
    assert any(widget["id"] == "hero-pace" for widget in state["hud"]["widgets"])
    assert state["preview"]["width"] == 1280


def test_save_editor_payload_updates_overlay_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["theme"]["note_text"] = "Kasumigaura"
    hero_pace = next(widget for widget in payload["widgets"] if widget["id"] == "hero-pace")
    hero_pace["x"] = 48

    save_editor_payload(config_path, payload)
    reloaded = load_config(config_path)

    assert reloaded.hud.theme.note_text == "Kasumigaura"
    hero_widget = next(widget for widget in reloaded.hud.widgets if widget.id == "hero-pace")
    assert hero_widget.x == 48
    assert len(reloaded.hud.widgets) == len(broadcast_runner_preset().widgets)


def test_save_editor_payload_rejects_invalid_numeric_widget_values(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    hero_pace = next(widget for widget in payload["widgets"] if widget["id"] == "hero-pace")
    hero_pace["x"] = None

    with pytest.raises(ValueError, match="x must be a finite integer"):
        save_editor_payload(config_path, payload)

    hero_widget = next(widget for widget in load_config(config_path).hud.widgets if widget.id == "hero-pace")
    assert hero_widget.x == 24


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"preset": "broadcast-runner"},
        {"theme": {"note_text": "Kasumigaura"}},
        {"preset": "broadcast-runner", "theme": serialize_hud_config(broadcast_runner_preset())["theme"], "widgets": []},
        {
            "preset": "broadcast-runner",
            "theme": {"note_text": "Kasumigaura"},
            "widgets": serialize_hud_config(broadcast_runner_preset())["widgets"],
        },
        {
            "preset": "broadcast-runner",
            "theme": serialize_hud_config(broadcast_runner_preset())["theme"],
            "widgets": [serialize_hud_config(broadcast_runner_preset())["widgets"][0]],
        },
    ],
)
def test_save_editor_payload_rejects_incomplete_hud_documents(tmp_path: Path, payload: dict[str, object]) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with pytest.raises(ValueError, match="complete HUD document"):
        save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert len(reloaded.hud.widgets) == len(broadcast_runner_preset().widgets)


def test_save_editor_payload_rejects_invalid_theme_values(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["theme"]["panel_rgba"] = "oops"
    payload["theme"]["note_text"] = "Kasumigaura"

    with pytest.raises(ValueError, match="panel_rgba must be a list of 4 integers"):
        save_editor_payload(config_path, payload)

    assert load_config(config_path).hud.theme.panel_rgba == [12, 18, 28, 168]


def test_save_editor_payload_rejects_partial_widget_objects(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    hero_pace = next(widget for widget in payload["widgets"] if widget["id"] == "hero-pace")
    hero_pace.pop("visible")

    with pytest.raises(ValueError, match="complete HUD document"):
        save_editor_payload(config_path, payload)

    hero_widget = next(widget for widget in load_config(config_path).hud.widgets if widget.id == "hero-pace")
    assert hero_widget.visible is True


def test_save_editor_payload_rejects_partial_widget_bindings(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    hero_pace = next(widget for widget in payload["widgets"] if widget["id"] == "hero-pace")
    hero_pace["bindings"] = {}

    with pytest.raises(ValueError, match="complete HUD document"):
        save_editor_payload(config_path, payload)

    hero_widget = next(widget for widget in load_config(config_path).hud.widgets if widget.id == "hero-pace")
    assert hero_widget.bindings == {"value": "pace_seconds_per_km"}


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: next(widget for widget in payload["widgets"] if widget["id"] == "hero-pace").update(anchor="center"),
            "unsupported anchor",
        ),
        (
            lambda payload: next(widget for widget in payload["widgets"] if widget["id"] == "distance-progress").update(width=160),
            "minimum width",
        ),
    ],
)
def test_save_editor_payload_rejects_renderer_invalid_widgets_before_persisting(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_text = config_path.read_text()

    payload = serialize_hud_config(broadcast_runner_preset())
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        save_editor_payload(config_path, payload)

    assert config_path.read_text() == original_text
    assert load_config(config_path).hud.preset == "broadcast-runner"


@contextmanager
def running_editor(config_path: Path) -> str:
    base_url = launch_editor(config_path, width=1280, height=720)
    server = _ACTIVE_SERVERS[-1]
    thread = _ACTIVE_THREADS[-1]
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        _ACTIVE_SERVERS.remove(server)
        _ACTIVE_THREADS.remove(thread)


def test_api_config_rejects_malformed_json_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=b"{",
                headers={"Content-Type": "application/json", "Content-Length": "1"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert json.loads(body.decode("utf-8"))["error"] == "invalid JSON payload"


def test_api_config_rejects_partial_payload_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps({"preset": "broadcast-runner"}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "complete HUD document" in json.loads(body.decode("utf-8"))["error"]
    assert len(load_config(config_path).hud.widgets) == len(broadcast_runner_preset().widgets)


def test_api_config_returns_structured_error_when_save_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    def raise_permission_error(*args, **kwargs) -> None:
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr("race_overlay.editor_preview.save_config", raise_permission_error)

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(serialize_hud_config(broadcast_runner_preset())),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 500
    assert "read-only filesystem" in json.loads(body.decode("utf-8"))["error"]
    assert load_config(config_path).hud.preset == "broadcast-runner"


def test_api_config_rejects_nan_values_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    payload = serialize_hud_config(broadcast_runner_preset())
    hero_pace = next(widget for widget in payload["widgets"] if widget["id"] == "hero-pace")
    hero_pace["style"]["label"] = float("nan")

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert json.loads(body.decode("utf-8"))["error"] == "invalid JSON payload"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: next(widget for widget in payload["widgets"] if widget["id"] == "hero-pace").update(anchor="center"),
            "unsupported anchor",
        ),
        (
            lambda payload: next(widget for widget in payload["widgets"] if widget["id"] == "distance-progress").update(width=160),
            "minimum width",
        ),
    ],
)
def test_api_config_rejects_renderer_invalid_widgets_with_400(
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_text = config_path.read_text()

    payload = serialize_hud_config(broadcast_runner_preset())
    mutate(payload)

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert message in json.loads(body.decode("utf-8"))["error"]
    assert config_path.read_text() == original_text

def test_api_config_rejects_invalid_content_length_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        with socket.create_connection((parts.hostname, parts.port), timeout=5) as connection:
            connection.sendall(
                b"POST /api/config HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: abc\r\n"
                b"Connection: close\r\n\r\n"
                b"{}"
            )
            response = b""
            while chunk := connection.recv(4096):
                response += chunk

    assert b" 400 " in response.splitlines()[0]
    assert b'"error": "invalid Content-Length header"' in response


def test_api_config_rejects_negative_content_length_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        with socket.create_connection((parts.hostname, parts.port), timeout=5) as connection:
            connection.sendall(
                b"POST /api/config HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: -1\r\n"
                b"Connection: close\r\n\r\n"
                b"{}"
            )
            response = b""
            while chunk := connection.recv(4096):
                response += chunk

    assert b" 400 " in response.splitlines()[0]
    assert b'"error": "invalid Content-Length header"' in response


def test_api_state_returns_structured_error_when_config_becomes_malformed(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        config_path.write_text("hud: [\n")
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "config" in json.loads(body.decode("utf-8"))["error"]


def test_launch_editor_rejects_directory_config_path(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    config_path.mkdir()

    with pytest.raises(ValueError, match="config file"):
        launch_editor(config_path, width=1280, height=720)


def test_api_state_returns_structured_error_when_config_path_becomes_directory(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        config_path.unlink()
        config_path.mkdir()
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/api/state")
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "config file" in json.loads(body.decode("utf-8"))["error"]


def test_editor_app_surfaces_api_state_errors_without_throwing() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    app_path = repo_root / "src" / "race_overlay" / "editor_assets" / "app.js"
    script = f"""
import fs from "node:fs";
import vm from "node:vm";

const elements = new Map();

function createElement(id) {{
  return {{
    id,
    value: "",
    checked: false,
    hidden: true,
    disabled: false,
    innerHTML: "",
    textContent: "",
    src: "",
    className: "",
    dataset: {{}},
    appendChild() {{}},
    addEventListener() {{}},
    removeAttribute(name) {{
      this[name] = "";
    }},
  }};
}}

const document = {{
  createElement(tagName) {{
    return createElement(tagName);
  }},
  getElementById(id) {{
    if (!elements.has(id)) {{
      elements.set(id, createElement(id));
    }}
    return elements.get(id);
  }},
  querySelectorAll() {{
    return [];
  }},
}};

let unhandled = null;
process.on("unhandledRejection", (error) => {{
  unhandled = error instanceof Error ? error.message : String(error);
}});

globalThis.document = document;
globalThis.window = {{ alert() {{}} }};
globalThis.fetch = async () => ({{
  ok: false,
  async json() {{
    return {{ error: "config file is not readable: permission denied" }};
  }},
}});

const source = fs.readFileSync({json.dumps(str(app_path))}, "utf8");
vm.runInThisContext(source, {{ filename: {json.dumps(str(app_path))} }});
await new Promise((resolve) => setTimeout(resolve, 0));

console.log(JSON.stringify({{
  statusText: document.getElementById("status-message").textContent,
  statusHidden: document.getElementById("status-message").hidden,
  previewSrc: document.getElementById("preview").src,
  widgetList: document.getElementById("widget-list").innerHTML,
  saveDisabled: document.getElementById("save-button").disabled,
  unhandled,
}}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    payload = json.loads(result.stdout.strip())

    assert payload["unhandled"] is None
    assert payload["statusText"] == "config file is not readable: permission denied"
    assert payload["statusHidden"] is False
    assert payload["previewSrc"] == ""
    assert payload["widgetList"] == ""
    assert payload["saveDisabled"] is True
