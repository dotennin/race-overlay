import json
from datetime import datetime, timezone
from pathlib import Path

from race_overlay.video_probe import probe_video


def test_probe_video_reads_creation_time_and_duration(monkeypatch) -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 3840,
                "height": 2160,
                "avg_frame_rate": "30000/1001",
                "pix_fmt": "yuv420p",
                "bit_rate": "16000000",
                "color_space": "bt709",
                "color_transfer": "bt709",
                "color_primaries": "bt709",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "bit_rate": "192000",
            },
        ],
        "format": {
            "duration": "39.96",
            "tags": {"creation_time": "2026-04-19T00:06:00.000000Z"},
        },
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
    assert clip.video_codec == "h264"
    assert clip.pixel_format == "yuv420p"
    assert clip.video_bitrate == 16_000_000
    assert clip.color_space == "bt709"
    assert clip.color_transfer == "bt709"
    assert clip.color_primaries == "bt709"
    assert clip.audio_codec == "aac"
    assert clip.audio_bitrate == 192_000


def test_probe_video_includes_source_encoding_metadata(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30000/1001",
                "pix_fmt": "yuv420p",
                "bit_rate": "16000000",
                "color_space": "bt709",
                "color_transfer": "bt709",
                "color_primaries": "bt709",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "bit_rate": "192000",
            },
        ],
        "format": {
            "duration": "12.5",
            "tags": {"creation_time": "2026-04-19T09:05:59Z"},
        },
    }
    monkeypatch.setattr(
        "race_overlay.video_probe.subprocess.check_output",
        lambda *args, **kwargs: json.dumps(payload),
    )

    clip = probe_video(tmp_path / "clip.MP4")

    assert clip.creation_time == datetime(2026, 4, 19, 9, 5, 59, tzinfo=timezone.utc)
    assert clip.video_codec == "h264"
    assert clip.pixel_format == "yuv420p"
    assert clip.video_bitrate == 16_000_000
    assert clip.color_space == "bt709"
    assert clip.color_transfer == "bt709"
    assert clip.color_primaries == "bt709"
    assert clip.audio_codec == "aac"
    assert clip.audio_bitrate == 192_000
