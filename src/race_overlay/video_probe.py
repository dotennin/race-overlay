import json
import subprocess
from datetime import datetime
from pathlib import Path

from race_overlay.models import VideoClip


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_optional_int(value: str | None) -> int | None:
    if value is None or value == "N/A":
        return None
    return int(value)


def _parse_rate(value: str) -> float:
    numerator, denominator = value.split("/")
    denominator_value = float(denominator)
    if denominator_value == 0:
        return 0.0
    return float(numerator) / denominator_value


def _has_attached_pic_disposition(stream: dict[str, object]) -> bool:
    disposition = stream.get("disposition")
    if not isinstance(disposition, dict):
        return False
    return disposition.get("attached_pic") == 1


def _attached_pic_stream_index(streams: list[dict[str, object]]) -> int | None:
    for stream in streams:
        if stream.get("codec_type") == "video" and _has_attached_pic_disposition(stream):
            return int(stream["index"])
    return None


def probe_video(path: Path) -> VideoClip:
    payload = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_entries",
                "format=duration:format_tags=creation_time",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )
    video_stream = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
    audio_stream = next((stream for stream in payload["streams"] if stream["codec_type"] == "audio"), {})
    attached_pic_stream_index = _attached_pic_stream_index(payload["streams"])
    return VideoClip(
        path=path,
        creation_time=_parse_time(payload["format"]["tags"]["creation_time"]),
        duration_seconds=float(payload["format"]["duration"]),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=_parse_rate(video_stream["avg_frame_rate"]),
        video_codec=video_stream.get("codec_name"),
        pixel_format=video_stream.get("pix_fmt"),
        video_bitrate=_parse_optional_int(video_stream.get("bit_rate")),
        color_space=video_stream.get("color_space"),
        color_primaries=video_stream.get("color_primaries"),
        color_transfer=video_stream.get("color_transfer"),
        audio_codec=audio_stream.get("codec_name"),
        audio_bitrate=_parse_optional_int(audio_stream.get("bit_rate")),
        has_attached_pic=attached_pic_stream_index is not None,
        attached_pic_stream_index=attached_pic_stream_index,
    )
