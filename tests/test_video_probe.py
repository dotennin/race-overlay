import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from race_overlay.video_probe import probe_video


def test_probe_video_reads_creation_time_and_duration(monkeypatch) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
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
                "index": 1,
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
    assert clip.fps == 30000 / 1001
    assert clip.video_codec == "h264"
    assert clip.pixel_format == "yuv420p"
    assert clip.video_bitrate == 16_000_000
    assert clip.color_space == "bt709"
    assert clip.color_transfer == "bt709"
    assert clip.color_primaries == "bt709"
    assert clip.audio_codec == "aac"
    assert clip.audio_bitrate == 192_000


def test_probe_video_detects_attached_thumbnail_stream(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30000/1001",
                "pix_fmt": "yuv420p",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
            },
            {
                "index": 2,
                "codec_type": "video",
                "codec_name": "mjpeg",
                "disposition": {"attached_pic": 1},
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

    assert clip.has_attached_pic is True
    assert clip.attached_pic_stream_index == 2


def test_probe_video_includes_source_encoding_metadata(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
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
                "index": 1,
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
    assert clip.fps == 30000 / 1001
    assert clip.video_codec == "h264"
    assert clip.pixel_format == "yuv420p"
    assert clip.video_bitrate == 16_000_000
    assert clip.color_space == "bt709"
    assert clip.color_transfer == "bt709"
    assert clip.color_primaries == "bt709"
    assert clip.audio_codec == "aac"
    assert clip.audio_bitrate == 192_000
    assert clip.has_attached_pic is False
    assert clip.attached_pic_stream_index is None


def test_probe_video_treats_na_bitrate_as_missing(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30000/1001",
                "bit_rate": "N/A",
            }
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

    assert clip.video_bitrate is None


def test_probe_video_handles_missing_optional_metadata(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30000/1001",
            },
            {
                "codec_type": "audio",
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

    assert clip.video_codec is None
    assert clip.pixel_format is None
    assert clip.video_bitrate is None
    assert clip.color_space is None
    assert clip.color_transfer is None
    assert clip.color_primaries is None
    assert clip.audio_codec is None
    assert clip.audio_bitrate is None
    assert clip.has_attached_pic is False
    assert clip.attached_pic_stream_index is None


def test_probe_video_handles_zero_zero_avg_frame_rate(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "0/0",
            }
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

    assert clip.fps == 0.0


def test_probe_video_reads_display_matrix_rotation(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
                "side_data_list": [{"side_data_type": "Display Matrix", "rotation": 90}],
            }
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

    assert probe_video(tmp_path / "phone.mov").source_rotation_degrees == 270


def test_probe_video_falls_back_to_rotate_tag(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
                "tags": {"rotate": "270"},
            }
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

    assert probe_video(tmp_path / "phone.mov").source_rotation_degrees == 270


def test_probe_video_rejects_non_quarter_turn_rotation(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
                "side_data_list": [{"side_data_type": "Display Matrix", "rotation": 45}],
            }
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

    with pytest.raises(ValueError, match="quarter-turn"):
        probe_video(tmp_path / "phone.mov")
