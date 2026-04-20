import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from threading import Event, Thread
from urllib.parse import urlparse

import pytest
import yaml

from race_overlay.config import ProjectConfig, load_config, save_config
from race_overlay.editor_preview import build_editor_state, load_editor_config, save_editor_payload
from race_overlay.editor_server import _ACTIVE_SERVERS, _ACTIVE_THREADS, launch_editor
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig, serialize_hud_config


def test_build_editor_state_exposes_widgets_for_preview() -> None:
    state = build_editor_state(
        config=ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()),
        width=1280,
        height=720,
    )

    assert state["hud"]["preset"] == "broadcast-runner"
    assert any(widget["id"] == "hero-pace" for widget in state["hud"]["widgets"])
    assert state["preview"]["width"] == 1280
    assert isinstance(state["revision"], str)
    assert state["revision"]


def test_save_editor_payload_updates_overlay_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["note_text"] = "Kasumigaura"
    hero_pace = next(widget for widget in payload["widgets"] if widget["id"] == "hero-pace")
    hero_pace["x"] = 48

    save_editor_payload(config_path, payload)
    reloaded = load_config(config_path)

    assert reloaded.hud.theme.note_text == "Kasumigaura"
    hero_widget = next(widget for widget in reloaded.hud.widgets if widget.id == "hero-pace")
    assert hero_widget.x == 48
    assert len(reloaded.hud.widgets) == len(broadcast_runner_preset().widgets)


def test_save_editor_payload_preserves_schema_when_legacy_fields_are_also_present(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    schema_hud = broadcast_runner_preset()
    schema_hud.theme.note_text = "Schema wins"
    route_map = next(widget for widget in schema_hud.widgets if widget.id == "route-map")
    hero_pace = next(widget for widget in schema_hud.widgets if widget.id == "hero-pace")
    route_map.visible = True
    hero_pace.visible = False
    hero_pace.x = 144
    mixed_payload = {
        "activity_file": "activity_22577902433.tcx",
        "video_globs": ["*.MP4", "*.mov"],
        "output_dir": "rendered",
        "cache_dir": "cache",
        "timeline": {"global_offset_seconds": 0.0, "outside_activity": "no_data"},
        "hud": {
            "fields": {
                "pace": True,
                "elapsed": True,
                "distance": True,
                "speed": True,
                "heart_rate": True,
                "cadence": True,
                "mini_map": False,
            },
            **serialize_hud_config(schema_hud),
        },
        "overrides": {},
    }
    config_path.write_text(yaml.safe_dump(mixed_payload, sort_keys=False))

    editor_state = build_editor_state(load_config(config_path), width=1280, height=720)
    payload = json.loads(json.dumps(editor_state["hud"]))
    payload["revision"] = editor_state["revision"]
    payload["theme"]["note_text"] = "Saved schema HUD"

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    saved_payload = yaml.safe_load(config_path.read_text())
    route_map_reloaded = next(widget for widget in reloaded.hud.widgets if widget.id == "route-map")
    hero_pace_reloaded = next(widget for widget in reloaded.hud.widgets if widget.id == "hero-pace")

    assert reloaded.hud.theme.note_text == "Saved schema HUD"
    assert route_map_reloaded.visible is True
    assert hero_pace_reloaded.visible is False
    assert hero_pace_reloaded.x == 144
    assert "fields" not in saved_payload["hud"]


def test_save_editor_payload_allows_missing_widget_label(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            hud=HudConfig(
                preset="route-only",
                theme=HudThemeConfig(),
                widgets=[
                    HudWidgetConfig(
                        id="route-map",
                        type="route_map",
                        bindings={"value": "route_points"},
                        anchor="top-left",
                        x=24,
                        y=24,
                        width=176,
                        height=128,
                    )
                ],
            ),
        ),
    )

    payload = serialize_hud_config(load_config(config_path).hud)
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["widgets"][0]["style"]["label"] = ""

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert reloaded.hud.widgets[0].style == {"label": ""}


def test_save_editor_payload_allows_empty_widget_list_when_existing_hud_is_empty(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(
        config_path,
        ProjectConfig(
            activity_file="activity_22577902433.tcx",
            hud=HudConfig(
                preset="empty",
                theme=HudThemeConfig(),
                widgets=[],
            ),
        ),
    )

    payload = serialize_hud_config(load_config(config_path).hud)
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["note_text"] = "No widgets"

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert reloaded.hud.theme.note_text == "No widgets"
    assert reloaded.hud.widgets == []


def test_save_editor_payload_does_not_run_two_load_modify_write_cycles_concurrently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    original_save_config = save_editor_payload.__globals__["save_config"]
    first_save_entered = Event()
    release_first_save = Event()
    second_save_entered = Event()
    call_count = 0

    def blocking_save_config(path: Path, config: ProjectConfig) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            first_save_entered.set()
            release_first_save.wait(timeout=1)
        else:
            second_save_entered.set()
        original_save_config(path, config)

    monkeypatch.setattr("race_overlay.editor_preview.save_config", blocking_save_config)

    payload_one = serialize_hud_config(broadcast_runner_preset())
    payload_one["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload_one["theme"]["note_text"] = "first"
    payload_two = serialize_hud_config(broadcast_runner_preset())
    payload_two["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload_two["theme"]["note_text"] = "second"

    errors: list[BaseException] = []

    def save_payload(payload: dict[str, object]) -> None:
        try:
            save_editor_payload(config_path, payload)
        except BaseException as exc:  # pragma: no cover - captured for assertion
            errors.append(exc)

    first_thread = Thread(target=save_payload, args=(payload_one,))
    second_thread = Thread(target=save_payload, args=(payload_two,))
    first_thread.start()
    assert first_save_entered.wait(timeout=1)
    second_thread.start()

    assert not second_save_entered.wait(timeout=0.1)
    release_first_save.set()
    first_thread.join(timeout=1)
    second_thread.join(timeout=1)

    assert second_save_entered.is_set() is False
    assert len(errors) == 1
    assert "stale HUD" in str(errors[0])


def test_save_editor_payload_preserves_newer_non_hud_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["note_text"] = "Kasumigaura"

    original_validate = save_editor_payload.__globals__["_validate_complete_hud_payload"]

    def validate_then_apply_external_non_hud_changes(existing_hud: HudConfig, candidate_payload: dict[str, object]) -> None:
        original_validate(existing_hud, candidate_payload)
        updated = load_config(config_path)
        updated.timeline.global_offset_seconds = 12.5
        updated.overrides["clip.mp4"] = {"offset_seconds": 3.0, "outside_activity": "freeze"}
        save_config(config_path, updated)

    monkeypatch.setattr(
        "race_overlay.editor_preview._validate_complete_hud_payload",
        validate_then_apply_external_non_hud_changes,
    )

    save_editor_payload(config_path, payload)

    reloaded = load_config(config_path)
    assert reloaded.hud.theme.note_text == "Kasumigaura"
    assert reloaded.timeline.global_offset_seconds == 12.5
    assert reloaded.overrides == {"clip.mp4": {"offset_seconds": 3.0, "outside_activity": "freeze"}}


def test_save_editor_payload_rejects_stale_hud_revision(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    initial_state = build_editor_state(load_config(config_path), width=1280, height=720)
    payload = dict(initial_state["hud"])
    payload["theme"] = dict(initial_state["hud"]["theme"])
    payload["widgets"] = [
        {**widget, "bindings": dict(widget["bindings"]), "style": dict(widget["style"])}
        for widget in initial_state["hud"]["widgets"]
    ]
    payload["revision"] = initial_state["revision"]

    updated = load_config(config_path)
    updated.hud.theme.note_text = "newer edit"
    save_config(config_path, updated)

    payload["theme"]["note_text"] = "older edit"

    with pytest.raises(ValueError, match="stale HUD"):
        save_editor_payload(config_path, payload)

    assert load_config(config_path).hud.theme.note_text == "newer edit"


def test_save_editor_payload_rejects_external_concurrent_save_from_another_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    state = build_editor_state(load_config(config_path), width=1280, height=720)
    payload_one = json.loads(json.dumps(state["hud"]))
    payload_one["revision"] = state["revision"]
    payload_one["theme"]["note_text"] = "first"
    payload_two = json.loads(json.dumps(state["hud"]))
    payload_two["revision"] = state["revision"]
    payload_two["theme"]["note_text"] = "second"

    original_save_config = save_editor_payload.__globals__["save_config"]
    first_save_entered = Event()
    release_first_save = Event()
    errors: list[BaseException] = []

    def blocking_save_config(path: Path, config: ProjectConfig) -> None:
        first_save_entered.set()
        assert release_first_save.wait(timeout=5)
        original_save_config(path, config)

    monkeypatch.setattr("race_overlay.editor_preview.save_config", blocking_save_config)

    def save_first_payload() -> None:
        try:
            save_editor_payload(config_path, payload_one)
        except BaseException as exc:  # pragma: no cover - captured for assertion
            errors.append(exc)

    first_thread = Thread(target=save_first_payload)
    first_thread.start()
    assert first_save_entered.wait(timeout=1)

    payload_path = tmp_path / "payload-two.json"
    payload_path.write_text(json.dumps(payload_two))

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import json, sys\n"
                "from pathlib import Path\n"
                "from race_overlay.editor_preview import save_editor_payload\n"
                "config_path = Path(sys.argv[1])\n"
                "payload = json.loads(Path(sys.argv[2]).read_text())\n"
                "save_editor_payload(config_path, payload)\n"
            ),
            str(config_path),
            str(payload_path),
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    time.sleep(0.2)
    assert process.poll() is None

    release_first_save.set()
    stdout, stderr = process.communicate(timeout=5)
    first_thread.join(timeout=5)

    assert not errors
    assert process.returncode != 0
    assert "stale HUD save rejected" in stderr
    assert stdout == ""
    assert load_config(config_path).hud.theme.note_text == "first"


def test_save_editor_payload_rejects_invalid_numeric_widget_values(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
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
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
    payload["theme"]["panel_rgba"] = "oops"
    payload["theme"]["note_text"] = "Kasumigaura"

    with pytest.raises(ValueError, match="panel_rgba must be a list of 4 integers"):
        save_editor_payload(config_path, payload)

    assert load_config(config_path).hud.theme.panel_rgba == [12, 18, 28, 168]


def test_save_editor_payload_rejects_partial_widget_objects(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
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
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
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
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
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


def test_api_config_rejects_stale_hud_save_with_409(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request("GET", "/api/state")
            state_response = connection.getresponse()
            state = json.loads(state_response.read().decode("utf-8"))
        finally:
            connection.close()

        updated = load_config(config_path)
        updated.hud.theme.note_text = "newer edit"
        save_config(config_path, updated)

        stale_payload = dict(state["hud"])
        stale_payload["theme"] = dict(state["hud"]["theme"])
        stale_payload["widgets"] = [
            {**widget, "bindings": dict(widget["bindings"]), "style": dict(widget["style"])}
            for widget in state["hud"]["widgets"]
        ]
        stale_payload["revision"] = state["revision"]
        stale_payload["theme"]["note_text"] = "older edit"

        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(stale_payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 409
    assert "stale HUD" in json.loads(body.decode("utf-8"))["error"]
    assert load_config(config_path).hud.theme.note_text == "newer edit"


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
                body=json.dumps(
                    {
                        **serialize_hud_config(broadcast_runner_preset()),
                        "revision": build_editor_state(load_config(config_path), width=1280, height=720)["revision"],
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 500
    assert "read-only filesystem" in json.loads(body.decode("utf-8"))["error"]
    assert load_config(config_path).hud.preset == "broadcast-runner"


def test_api_config_returns_structured_error_when_save_reload_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    original_load_config = load_config
    call_count = 0

    def raise_yaml_error(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise yaml.YAMLError("concurrent write truncated file")
        return original_load_config(*args, **kwargs)

    monkeypatch.setattr("race_overlay.editor_preview.load_config", raise_yaml_error)

    with running_editor(config_path) as base_url:
        parts = urlparse(base_url)
        connection = HTTPConnection(parts.hostname, parts.port)
        try:
            connection.request(
                "POST",
                "/api/config",
                body=json.dumps(
                    {
                        **serialize_hud_config(broadcast_runner_preset()),
                        "revision": build_editor_state(load_config(config_path), width=1280, height=720)["revision"],
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = response.read()
        finally:
            connection.close()

    assert response.status == 400
    assert "config file is not valid YAML" in json.loads(body.decode("utf-8"))["error"]
    assert load_config(config_path).hud.preset == "broadcast-runner"


def test_api_config_rejects_nan_values_with_400(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    save_config(config_path, ProjectConfig(activity_file="activity_22577902433.tcx", hud=broadcast_runner_preset()))
    payload = serialize_hud_config(broadcast_runner_preset())
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
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
    payload["revision"] = build_editor_state(load_config(config_path), width=1280, height=720)["revision"]
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
