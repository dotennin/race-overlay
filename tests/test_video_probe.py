from datetime import datetime, timezone
import json
from pathlib import Path

from race_overlay.video_probe import probe_video


def test_probe_video_reads_creation_time_and_duration(monkeypatch) -> None:
    payload = {
        "format": {"duration": "39.96", "tags": {"creation_time": "2026-04-19T00:06:00.000000Z"}},
        "streams": [{"width": 3840, "height": 2160, "r_frame_rate": "30000/1001"}],
    }

    def fake_check_output(*_args, **_kwargs) -> str:
        return json.dumps(payload)

    monkeypatch.setattr("subprocess.check_output", fake_check_output)

    clip = probe_video(Path("DJI_20260419090559_0002_D.MP4"))
    assert clip.path.name == "DJI_20260419090559_0002_D.MP4"
    assert clip.creation_time == datetime(2026, 4, 19, 0, 6, 0, tzinfo=timezone.utc)
    assert clip.duration_seconds == 39.96
    assert clip.width == 3840
    assert clip.height == 2160
