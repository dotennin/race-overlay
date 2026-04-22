from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True, frozen=True)
class ActivitySample:
    timestamp: datetime
    latitude: float | None
    longitude: float | None
    altitude_m: float | None
    distance_m: float | None
    speed_mps: float | None
    heart_rate_bpm: int | None
    cadence_spm: int | None


@dataclass(slots=True, frozen=True)
class ActivityTrack:
    sport: str
    samples: list[ActivitySample]


@dataclass(slots=True, frozen=True)
class VideoClip:
    path: Path
    creation_time: datetime
    duration_seconds: float
    width: int
    height: int
    fps: float
    video_codec: str | None = None
    pixel_format: str | None = None
    video_bitrate: int | None = None
    color_space: str | None = None
    color_primaries: str | None = None
    color_transfer: str | None = None
    audio_codec: str | None = None
    audio_bitrate: int | None = None


@dataclass(slots=True, frozen=True)
class ClipAlignment:
    clip: VideoClip
    status: str
    clip_start: datetime
    clip_end: datetime
    overlay_start: datetime | None
    overlay_end: datetime | None


@dataclass(slots=True, frozen=True)
class HudSample:
    timestamp: datetime
    latitude: float | None
    longitude: float | None
    altitude_m: float | None
    distance_m: float | None
    speed_mps: float | None
    pace_seconds_per_km: float | None
    heart_rate_bpm: int | None
    cadence_spm: int | None
