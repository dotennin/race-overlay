from dataclasses import dataclass
from datetime import datetime, timedelta

from race_overlay.models import ActivityLap, ActivityTrack, HudSample


@dataclass(slots=True, frozen=True)
class LapWaterfallRow:
    lap: ActivityLap
    lap_index: int
    is_dimmed: bool


@dataclass(slots=True, frozen=True)
class LapWaterfallState:
    completed_laps: list[ActivityLap]
    visible_rows: list[LapWaterfallRow]
    newest_lap_index: int | None
    oldest_row_dimmed: bool
    opacity: float


def lap_waterfall_state(
    laps: list[ActivityLap],
    when: datetime,
    *,
    visible_rows: int = 5,
    always_show: bool = False,
    fade_after_seconds: float = 10.0,
) -> LapWaterfallState:
    if visible_rows < 1:
        raise ValueError(f"visible_rows must be >= 1, got {visible_rows}")

    completed = [
        (i, lap)
        for i, lap in enumerate(laps)
        if lap.start_time + timedelta(seconds=lap.total_time_seconds) <= when
    ]

    if not completed:
        return LapWaterfallState(
            completed_laps=[],
            visible_rows=[],
            newest_lap_index=None,
            oldest_row_dimmed=False,
            opacity=0.0,
        )

    newest_index, newest_lap = completed[-1]
    newest_lap_end = newest_lap.start_time + timedelta(seconds=newest_lap.total_time_seconds)

    if always_show:
        opacity = 1.0
    else:
        elapsed_since_end = (when - newest_lap_end).total_seconds()
        if elapsed_since_end >= fade_after_seconds:
            opacity = 0.0
        else:
            opacity = max(0.0, 1.0 - elapsed_since_end / fade_after_seconds)

    completed_laps = [lap for _, lap in completed]
    window = completed[-visible_rows:]
    window_full = len(completed) >= visible_rows

    rows = [
        LapWaterfallRow(
            lap=lap,
            lap_index=i,
            is_dimmed=(window_full and pos == 0),
        )
        for pos, (i, lap) in enumerate(window)
    ]

    return LapWaterfallState(
        completed_laps=completed_laps,
        visible_rows=rows,
        newest_lap_index=newest_index,
        oldest_row_dimmed=window_full,
        opacity=opacity,
    )


def _lerp(start: float | int | None, end: float | int | None, ratio: float) -> float | None:
    if start is None or end is None:
        return None
    return float(start) + (float(end) - float(start)) * ratio


def _bounding_samples(samples, when):
    for before, after in zip(samples, samples[1:]):
        if before.timestamp <= when <= after.timestamp:
            return before, after
    return samples[-2], samples[-1]


def sample_at(activity: ActivityTrack, when):
    before, after = _bounding_samples(activity.samples, when)
    ratio = (when - before.timestamp).total_seconds() / (after.timestamp - before.timestamp).total_seconds()
    speed_mps = _lerp(before.speed_mps, after.speed_mps, ratio)
    return HudSample(
        timestamp=when,
        latitude=_lerp(before.latitude, after.latitude, ratio),
        longitude=_lerp(before.longitude, after.longitude, ratio),
        altitude_m=_lerp(before.altitude_m, after.altitude_m, ratio),
        distance_m=_lerp(before.distance_m, after.distance_m, ratio),
        speed_mps=speed_mps,
        pace_seconds_per_km=(1000.0 / speed_mps) if speed_mps else None,
        heart_rate_bpm=round(_lerp(before.heart_rate_bpm, after.heart_rate_bpm, ratio)),
        cadence_spm=round(_lerp(before.cadence_spm, after.cadence_spm, ratio)),
    )
