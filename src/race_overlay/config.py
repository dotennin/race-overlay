from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


@dataclass(slots=True)
class TimelineConfig:
    global_offset_seconds: float = 0.0
    outside_activity: str = "no_data"


@dataclass(slots=True)
class HudFieldConfig:
    pace: bool = True
    elapsed: bool = True
    distance: bool = True
    speed: bool = True
    heart_rate: bool = True
    cadence: bool = True
    mini_map: bool = True


@dataclass(slots=True)
class HudConfig:
    fields: HudFieldConfig = field(default_factory=HudFieldConfig)


@dataclass(slots=True)
class ProjectConfig:
    activity_file: str
    video_globs: list[str] = field(default_factory=lambda: ["*.MP4", "*.mov"])
    output_dir: str = "rendered"
    cache_dir: str = "cache"
    timeline: TimelineConfig = field(default_factory=TimelineConfig)
    hud: HudConfig = field(default_factory=HudConfig)
    overrides: dict[str, dict[str, float | str]] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ClipOverride:
    offset_seconds: float = 0.0
    outside_activity: str | None = None


def write_default_config(path: Path, activity_file: str) -> None:
    save_config(path, ProjectConfig(activity_file=activity_file))


def load_config(path: Path) -> ProjectConfig:
    payload = yaml.safe_load(path.read_text())
    return ProjectConfig(
        activity_file=payload["activity_file"],
        video_globs=payload["video_globs"],
        output_dir=payload["output_dir"],
        cache_dir=payload["cache_dir"],
        timeline=TimelineConfig(**payload["timeline"]),
        hud=HudConfig(fields=HudFieldConfig(**payload["hud"]["fields"])),
        overrides=payload.get("overrides", {}),
    )


def save_config(path: Path, config: ProjectConfig) -> None:
    path.write_text(yaml.safe_dump(asdict(config), sort_keys=False))


def resolve_override(config: ProjectConfig, filename: str) -> ClipOverride:
    payload = config.overrides.get(filename, {})
    return ClipOverride(
        offset_seconds=float(payload.get("offset_seconds", 0.0)),
        outside_activity=str(payload["outside_activity"]) if "outside_activity" in payload else None,
    )
