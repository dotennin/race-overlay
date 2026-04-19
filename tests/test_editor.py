import json
import socket
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
