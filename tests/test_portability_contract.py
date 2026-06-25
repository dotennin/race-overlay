from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from race_overlay.activity.tcx_reader import read_tcx
from race_overlay.alignment import align_clip
from race_overlay.hud import _resolve_route_projection, _split_route_points
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.hud_schema import serialize_hud_config
from race_overlay.models import HudSample, VideoClip
from race_overlay.sampling import lap_waterfall_state, sample_at

ROOT = Path(__file__).resolve().parents[1]


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part.title() for part in rest)


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    return value


def _convert(value: Any) -> Any:
    if is_dataclass(value):
        return {_camel(key): _convert(item) for key, item in asdict(value).items()}
    if isinstance(value, list | tuple):
        return [_convert(item) for item in value]
    if isinstance(value, dict):
        return {_camel(key): _convert(item) for key, item in value.items()}
    return _iso(value)


def _route_projection_example(route_points: list[tuple[float, float]], hud_sample: HudSample) -> dict[str, object]:
    projection = _resolve_route_projection(route_points, hud_sample)
    assert projection is not None
    completed, remaining = _split_route_points(route_points, projection)
    return {
        "sample": _convert(hud_sample),
        "projection": _convert(projection),
        "split": {
            "completed": _convert(completed),
            "remaining": _convert(remaining),
        },
    }


def _build_contract() -> dict[str, Any]:
    activity = read_tcx(ROOT / "tests/fixtures/sample_activity.tcx")
    lap_activity = read_tcx(ROOT / "tests/fixtures/portable_laps.tcx")
    sample_times = [
        datetime(2026, 4, 19, 0, 45, 5, tzinfo=timezone.utc),
        datetime(2026, 4, 19, 0, 45, 5, 500000, tzinfo=timezone.utc),
        datetime(2026, 4, 19, 0, 45, 6, 500000, tzinfo=timezone.utc),
    ]
    clips = [
        VideoClip(Path("inside.mp4"), datetime(2026, 4, 19, 0, 45, 5, tzinfo=timezone.utc), 1.0, 1920, 1080, 30.0),
        VideoClip(Path("partial.mp4"), datetime(2026, 4, 19, 0, 45, 4, tzinfo=timezone.utc), 2.0, 1920, 1080, 30.0),
        VideoClip(Path("outside.mp4"), datetime(2026, 4, 19, 0, 45, 8, tzinfo=timezone.utc), 1.0, 1920, 1080, 30.0),
    ]
    lap_state_times = [
        datetime(2026, 4, 19, 0, 46, 35, tzinfo=timezone.utc),
        datetime(2026, 4, 19, 0, 52, 5, 225000, tzinfo=timezone.utc),
    ]
    route_points = [
        (sample.latitude, sample.longitude)
        for sample in activity.samples
        if sample.latitude is not None and sample.longitude is not None
    ]
    route_samples = [
        sample_at(activity, datetime(2026, 4, 19, 0, 45, 5, 500000, tzinfo=timezone.utc)),
        sample_at(activity, datetime(2026, 4, 19, 0, 45, 6, 500000, tzinfo=timezone.utc)),
    ]
    return {
        "activity": _convert(activity),
        "lapActivity": _convert(lap_activity),
        "sampleAt": [
            {"when": _iso(when), "sample": _convert(sample_at(activity, when))}
            for when in sample_times
        ],
        "alignClip": [_convert(align_clip(activity, clip, 0, 0)) for clip in clips],
        "hudPreset": serialize_hud_config(broadcast_runner_preset()),
        "lapWaterfallState": [
            {
                "when": _iso(when),
                "state": _convert(lap_waterfall_state(lap_activity.laps, when, visible_rows=2, always_show=True)),
            }
            for when in lap_state_times
        ],
        "routeProjection": [
            _route_projection_example(route_points, hud_sample)
            for hud_sample in route_samples
        ],
    }


def test_portability_contract_matches_python_core_behavior() -> None:
    expected = json.loads((ROOT / "tests/fixtures/portability_contract.json").read_text())

    assert _build_contract() == expected
