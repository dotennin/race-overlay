from datetime import datetime, timezone
from pathlib import Path

from race_overlay.alignment import align_clip
from race_overlay.models import ActivitySample, ActivityTrack, VideoClip


def test_align_clip_marks_partial_overlap() -> None:
    activity = ActivityTrack(
        sport="Running",
        samples=[
            ActivitySample(datetime(2026, 4, 19, 0, 45, 5, tzinfo=timezone.utc), None, None, None, 0.0, 4.0, 120, 90),
            ActivitySample(datetime(2026, 4, 19, 0, 45, 15, tzinfo=timezone.utc), None, None, None, 40.0, 4.0, 122, 92),
        ],
    )
    clip = VideoClip(Path("before-start.MP4"), datetime(2026, 4, 19, 0, 45, 0, tzinfo=timezone.utc), 10.0, 1920, 1080, 30.0)
    alignment = align_clip(activity, clip, global_offset_seconds=0.0, per_video_offset_seconds=0.0)

    assert alignment.status == "partial"
    assert alignment.overlay_start == datetime(2026, 4, 19, 0, 45, 5, tzinfo=timezone.utc)
