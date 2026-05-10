import fcntl
import os
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock, local
from uuid import uuid4

import yaml

from race_overlay.hud import validate_hud_config
from race_overlay.hud_presets import apply_legacy_field_visibility, broadcast_runner_preset, migrate_broadcast_runner_config
from race_overlay.hud_schema import HudConfig, deserialize_hud_config, serialize_hud_config


_CONFIG_SAVE_LOCK = RLock()
_CONFIG_SAVE_STATE = local()


@dataclass(slots=True)
class TimelineConfig:
    global_offset_seconds: float = 0.0
    outside_activity: str = "no_data"


@dataclass(slots=True)
class EncodingConfig:
    video_preset: str = "veryfast"


@dataclass(slots=True)
class ProjectConfig:
    activity_file: str
    video_globs: list[str] = field(default_factory=lambda: ["*.MP4", "*.mov"])
    output_dir: str = "rendered"
    cache_dir: str = "cache"
    timeline: TimelineConfig = field(default_factory=TimelineConfig)
    encoding: EncodingConfig = field(default_factory=EncodingConfig)
    hud: HudConfig = field(default_factory=broadcast_runner_preset)
    hud_presets: dict[str, HudConfig] = field(default_factory=dict)
    overrides: dict[str, dict[str, float | str]] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ClipOverride:
    offset_seconds: float = 0.0
    outside_activity: str | None = None


def write_default_config(path: Path, activity_file: str) -> None:
    save_config(
        path,
        ProjectConfig(
            activity_file=_record_path_relative_to_config(path, activity_file),
            video_globs=[_record_path_relative_to_config(path, pattern) for pattern in ["*.MP4", "*.mov"]],
            hud=broadcast_runner_preset(),
        ),
    )


def _strip_legacy_theme_keys(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    theme_payload = normalized.get("theme")
    if isinstance(theme_payload, dict):
        normalized["theme"] = {
            key: value
            for key, value in theme_payload.items()
            if key not in {"panel_rgba", "accent_rgba"}
        }
    return normalized


def _load_hud_config(payload: dict[str, object], *, require_complete: bool = False) -> HudConfig:
    normalized_payload = _strip_legacy_theme_keys(payload)
    if "fields" in normalized_payload:
        if any(key != "fields" for key in normalized_payload):
            hud = deserialize_hud_config(
                {key: value for key, value in normalized_payload.items() if key != "fields"},
                require_complete=require_complete,
            )
            return migrate_broadcast_runner_config(hud)
        if require_complete:
            raise ValueError("editor save requires a complete HUD document with preset, theme, and widgets")
        fields = normalized_payload["fields"]
        if not isinstance(fields, dict):
            raise TypeError("hud.fields must be a mapping")
        return migrate_broadcast_runner_config(apply_legacy_field_visibility(broadcast_runner_preset(), fields))
    return migrate_broadcast_runner_config(deserialize_hud_config(normalized_payload, require_complete=require_complete))


def _clone_hud_config(hud: HudConfig) -> HudConfig:
    return deserialize_hud_config(serialize_hud_config(hud), require_complete=True)


def _normalize_hud_presets(current_hud: HudConfig, presets_payload: object) -> dict[str, HudConfig]:
    presets: dict[str, HudConfig] = {}
    if presets_payload is not None:
        if not isinstance(presets_payload, dict):
            raise TypeError("presets must be a mapping")
        for name, preset_payload in presets_payload.items():
            if not isinstance(name, str) or not name:
                raise ValueError("preset names must be non-empty strings")
            if isinstance(preset_payload, HudConfig):
                preset = _clone_hud_config(preset_payload)
            else:
                if not isinstance(preset_payload, dict):
                    raise TypeError("presets entries must be mappings")
                preset = _load_hud_config(preset_payload, require_complete=True)
            preset.preset = name
            presets[name] = preset
    presets[current_hud.preset] = _clone_hud_config(current_hud)
    return presets


def load_config(path: Path) -> ProjectConfig:
    payload = yaml.safe_load(path.read_text())
    hud = _load_hud_config(payload["hud"])
    return ProjectConfig(
        activity_file=payload["activity_file"],
        video_globs=payload["video_globs"],
        output_dir=payload["output_dir"],
        cache_dir=payload["cache_dir"],
        timeline=TimelineConfig(**payload["timeline"]),
        encoding=EncodingConfig(**payload.get("encoding", {})),
        hud=hud,
        hud_presets=_normalize_hud_presets(hud, payload.get("presets")),
        overrides=payload.get("overrides", {}),
    )


def save_config(path: Path, config: ProjectConfig) -> None:
    with _locked_config_save(path):
        _save_config_unlocked(path, config)


@contextmanager
def _locked_config_save(path: Path):
    current_path = getattr(_CONFIG_SAVE_STATE, "path", None)
    depth = getattr(_CONFIG_SAVE_STATE, "depth", 0)
    if depth and current_path == path:
        _CONFIG_SAVE_STATE.depth = depth + 1
        try:
            yield
        finally:
            _CONFIG_SAVE_STATE.depth -= 1
        return

    lock_path = path.with_name(f".{path.name}.lock")
    with _CONFIG_SAVE_LOCK:
        lock_path.touch(exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            _CONFIG_SAVE_STATE.path = path
            _CONFIG_SAVE_STATE.depth = 1
            try:
                yield
            finally:
                _CONFIG_SAVE_STATE.depth = 0
                _CONFIG_SAVE_STATE.path = None
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _save_config_unlocked(path: Path, config: ProjectConfig) -> None:
    validate_hud_config(config.hud)
    for preset in _normalize_hud_presets(config.hud, config.hud_presets).values():
        validate_hud_config(preset)
    _write_text_atomic(path, yaml.safe_dump(_serialize_config(config), sort_keys=False))


def resolve_override(config: ProjectConfig, filename: str) -> ClipOverride:
    payload = config.overrides.get(filename, {})
    return ClipOverride(
        offset_seconds=float(payload.get("offset_seconds", 0.0)),
        outside_activity=str(payload["outside_activity"]) if "outside_activity" in payload else None,
    )


def resolve_path_from_config(config_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return config_path.resolve().parent / path


def resolve_video_globs_from_config(config_path: Path, patterns: list[str]) -> list[str]:
    return [str(resolve_path_from_config(config_path, pattern)) for pattern in patterns]


def _record_path_relative_to_config(config_path: Path, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return value
    config_dir = config_path.resolve().parent
    target = Path.cwd() / path
    return os.path.relpath(target, config_dir)


def _write_text_atomic(path: Path, contents: str) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(contents)
        temp_path.replace(path)
    except Exception:
        with suppress(FileNotFoundError):
            temp_path.unlink()
        raise


def _serialize_config(config: ProjectConfig) -> dict[str, object]:
    presets = _normalize_hud_presets(config.hud, config.hud_presets)
    return {
        "activity_file": config.activity_file,
        "video_globs": list(config.video_globs),
        "output_dir": config.output_dir,
        "cache_dir": config.cache_dir,
        "timeline": {
            "global_offset_seconds": config.timeline.global_offset_seconds,
            "outside_activity": config.timeline.outside_activity,
        },
        "encoding": {
            "video_preset": config.encoding.video_preset,
        },
        "hud": serialize_hud_config(config.hud),
        "presets": {name: serialize_hud_config(hud) for name, hud in presets.items()},
        "overrides": {filename: dict(values) for filename, values in config.overrides.items()},
    }
