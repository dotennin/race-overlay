import json
import subprocess
from datetime import datetime
from pathlib import Path

from race_overlay.models import VideoClip


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_rate(value: str) -> float:
    numerator, denominator = value.split("/")
    return float(numerator) / float(denominator)


def probe_video(path: Path) -> VideoClip:
    payload = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                (
                    "format=duration:format_tags=creation_time:"
                    "stream=codec_type,codec_name,width,height,avg_frame_rate,"
                    "pix_fmt,bit_rate,color_space,color_transfer,color_primaries"
                ),
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )
    video_stream = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
    audio_stream = next((stream for stream in payload["streams"] if stream["codec_type"] == "audio"), {})
    return VideoClip(
        path=path,
        creation_time=_parse_time(payload["format"]["tags"]["creation_time"]),
        duration_seconds=float(payload["format"]["duration"]),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=_parse_rate(video_stream["avg_frame_rate"]),
        video_codec=video_stream.get("codec_name"),
        pixel_format=video_stream.get("pix_fmt"),
        video_bitrate=int(video_stream["bit_rate"]) if video_stream.get("bit_rate") is not None else None,
        color_space=video_stream.get("color_space"),
        color_primaries=video_stream.get("color_primaries"),
        color_transfer=video_stream.get("color_transfer"),
        audio_codec=audio_stream.get("codec_name"),
        audio_bitrate=int(audio_stream["bit_rate"]) if audio_stream.get("bit_rate") is not None else None,
    )
