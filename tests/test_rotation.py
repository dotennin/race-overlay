from datetime import datetime, timezone
from pathlib import Path

import pytest

from race_overlay.config import (
    ProjectConfig,
    resolve_video_override,
    video_override_key,
)
from race_overlay.models import VideoClip
from race_overlay.rotation import RotationSpec


def make_clip(*, width: int = 1920, height: int = 1080, source_rotation: int = 0) -> VideoClip:
    return VideoClip(
        path=Path("camera/clip.mp4"),
        creation_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        duration_seconds=10,
        width=width,
        height=height,
        fps=30,
        source_rotation_degrees=source_rotation,
    )


@pytest.mark.parametrize(
    ("source", "user", "effective", "display_size"),
    [
        (0, 0, 0, (1920, 1080)),
        (90, 0, 90, (1080, 1920)),
        (90, 90, 180, (1920, 1080)),
        (90, 180, 270, (1080, 1920)),
        (90, 270, 0, (1920, 1080)),
    ],
)
def test_rotation_spec_combines_source_and_user_rotation(
    source: int,
    user: int,
    effective: int,
    display_size: tuple[int, int],
) -> None:
    spec = RotationSpec.from_clip(make_clip(source_rotation=source), user)

    assert spec.effective_degrees == effective
    assert (spec.display_width, spec.display_height) == display_size


@pytest.mark.parametrize("degrees", [-90, 45, 360])
def test_rotation_spec_rejects_non_canonical_rotation(degrees: int) -> None:
    with pytest.raises(ValueError, match="0, 90, 180, or 270"):
        RotationSpec.from_clip(make_clip(), degrees)


def test_video_override_key_uses_relative_posix_path_inside_project(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    video_path = tmp_path / "camera-a" / "clip.mp4"

    assert video_override_key(config_path, video_path) == "camera-a/clip.mp4"


def test_same_basename_videos_resolve_independent_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    first = tmp_path / "camera-a" / "clip.mp4"
    second = tmp_path / "camera-b" / "clip.mp4"
    config = ProjectConfig(
        activity_file="activity.tcx",
        overrides={
            "camera-a/clip.mp4": {"rotation_degrees": 90},
            "camera-b/clip.mp4": {"rotation_degrees": 270},
        },
    )

    first_override = resolve_video_override(config, config_path, first, [first, second])
    second_override = resolve_video_override(config, config_path, second, [first, second])

    assert first_override.rotation_degrees == 90
    assert second_override.rotation_degrees == 270


def test_unique_legacy_basename_override_remains_readable(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    video_path = tmp_path / "camera-a" / "clip.mp4"
    config = ProjectConfig(
        activity_file="activity.tcx",
        overrides={"clip.mp4": {"offset_seconds": 1.5, "rotation_degrees": 180}},
    )

    override = resolve_video_override(config, config_path, video_path, [video_path])

    assert override.offset_seconds == 1.5
    assert override.rotation_degrees == 180


def test_ambiguous_legacy_basename_override_is_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    first = tmp_path / "camera-a" / "clip.mp4"
    second = tmp_path / "camera-b" / "clip.mp4"
    config = ProjectConfig(
        activity_file="activity.tcx",
        overrides={"clip.mp4": {"rotation_degrees": 90}},
    )

    with pytest.raises(ValueError, match="ambiguous legacy override"):
        resolve_video_override(config, config_path, first, [first, second])
