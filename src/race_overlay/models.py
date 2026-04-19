from dataclasses import dataclass
from datetime import datetime


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
