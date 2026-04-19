from dataclasses import dataclass, field
from pathlib import Path

import yaml

from race_overlay.hud_presets import apply_legacy_field_visibility, broadcast_runner_preset
from race_overlay.hud_schema import HudConfig, deserialize_hud_config, serialize_hud_config


@dataclass(slots=True)
class TimelineConfig:
    global_offset_seconds: float = 0.0
    outside_activity: str = "no_data"


@dataclass(slots=True)
class ProjectConfig:
    activity_file: str
    video_globs: list[str] = field(default_factory=lambda: ["*.MP4", "*.mov"])
    output_dir: str = "rendered"
    cache_dir: str = "cache"
    timeline: TimelineConfig = field(default_factory=TimelineConfig)
    hud: HudConfig = field(default_factory=broadcast_runner_preset)
    overrides: dict[str, dict[str, float | str]] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ClipOverride:
    offset_seconds: float = 0.0
    outside_activity: str | None = None


def write_default_config(path: Path, activity_file: str) -> None:
    save_config(path, ProjectConfig(activity_file=activity_file, hud=broadcast_runner_preset()))


def _load_hud_config(payload: dict[str, object], *, require_complete: bool = False) -> HudConfig:
    if "fields" in payload:
        if require_complete:
            raise ValueError("editor save requires a complete HUD document with preset, theme, and widgets")
        fields = payload["fields"]
        if not isinstance(fields, dict):
            raise TypeError("hud.fields must be a mapping")
        return apply_legacy_field_visibility(broadcast_runner_preset(), fields)
    return deserialize_hud_config(payload, require_complete=require_complete)


def load_config(path: Path) -> ProjectConfig:
    payload = yaml.safe_load(path.read_text())
    return ProjectConfig(
        activity_file=payload["activity_file"],
        video_globs=payload["video_globs"],
        output_dir=payload["output_dir"],
        cache_dir=payload["cache_dir"],
        timeline=TimelineConfig(**payload["timeline"]),
        hud=_load_hud_config(payload["hud"]),
        overrides=payload.get("overrides", {}),
    )


def save_config(path: Path, config: ProjectConfig) -> None:
    payload = {
        "activity_file": config.activity_file,
        "video_globs": list(config.video_globs),
        "output_dir": config.output_dir,
        "cache_dir": config.cache_dir,
        "timeline": {
            "global_offset_seconds": config.timeline.global_offset_seconds,
            "outside_activity": config.timeline.outside_activity,
        },
        "hud": serialize_hud_config(config.hud),
        "overrides": {filename: dict(values) for filename, values in config.overrides.items()},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def resolve_override(config: ProjectConfig, filename: str) -> ClipOverride:
    payload = config.overrides.get(filename, {})
    return ClipOverride(
        offset_seconds=float(payload.get("offset_seconds", 0.0)),
        outside_activity=str(payload["outside_activity"]) if "outside_activity" in payload else None,
    )
