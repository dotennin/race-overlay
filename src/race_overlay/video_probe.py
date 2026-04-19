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
                "format=duration:stream=width,height,r_frame_rate:format_tags=creation_time",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )
    stream = payload["streams"][0]
    return VideoClip(
        path=path,
        creation_time=_parse_time(payload["format"]["tags"]["creation_time"]),
        duration_seconds=float(payload["format"]["duration"]),
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=_parse_rate(stream["r_frame_rate"]),
    )
