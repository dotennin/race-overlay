from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from race_overlay.config import ProjectConfig, _load_hud_config, load_config, save_config
from race_overlay.hud import render_hud_frame
from race_overlay.hud_schema import serialize_hud_config
from race_overlay.models import HudSample


def _sample_hud_value() -> HudSample:
    return HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )


def build_editor_state(config: ProjectConfig, width: int, height: int) -> dict[str, object]:
    return {
        "hud": serialize_hud_config(config.hud),
        "preview": {
            "width": width,
            "height": height,
            "route_points": [[36.0832, 140.2106], [36.0834, 140.2108]],
        },
    }


def save_editor_payload(config_path: Path, payload: dict[str, object]) -> None:
    config = load_config(config_path)
    config.hud = _load_hud_config(payload)
    save_config(config_path, config)


def render_preview_png(config: ProjectConfig, width: int, height: int) -> bytes:
    image = render_hud_frame(
        width,
        height,
        _sample_hud_value(),
        [(36.0832, 140.2106), (36.0834, 140.2108)],
        config.hud,
        6852,
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
