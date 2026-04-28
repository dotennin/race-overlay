from dataclasses import dataclass
from datetime import datetime, timedelta

from race_overlay.hud_schema import HudConfig, HudWidgetConfig
from race_overlay.models import ActivityLap, ActivityTrack, HudSample

LAP_WATERFALL_DEFAULT_VISIBLE_ROWS = 5
LAP_WATERFALL_DEFAULT_FADE_AFTER_SECONDS = 5.0
LAP_WATERFALL_SCROLL_SECONDS = 0.45


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
    transition_previous_rows: list[LapWaterfallRow] | None = None
    transition_progress: float = 1.0


def lap_waterfall_state(
    laps: list[ActivityLap],
    when: datetime,
    *,
    visible_rows: int = LAP_WATERFALL_DEFAULT_VISIBLE_ROWS,
    always_show: bool = False,
    fade_after_seconds: float = LAP_WATERFALL_DEFAULT_FADE_AFTER_SECONDS,
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
    transition_previous_rows: list[LapWaterfallRow] | None = None
    transition_progress = 1.0

    if window_full and len(completed) > visible_rows:
        elapsed_since_end = (when - newest_lap_end).total_seconds()
        if 0.0 <= elapsed_since_end < LAP_WATERFALL_SCROLL_SECONDS:
            transition_progress = max(0.0, min(elapsed_since_end / LAP_WATERFALL_SCROLL_SECONDS, 1.0))
            previous_window = completed[-visible_rows - 1:-1]
            transition_previous_rows = [
                LapWaterfallRow(
                    lap=lap,
                    lap_index=i,
                    is_dimmed=(pos == 0),
                )
                for pos, (i, lap) in enumerate(previous_window)
            ]

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
        transition_previous_rows=transition_previous_rows,
        transition_progress=transition_progress,
    )


def lap_waterfall_state_for_widget(
    widget: HudWidgetConfig,
    laps: list[ActivityLap],
    when: datetime,
) -> LapWaterfallState:
    return lap_waterfall_state(
        laps,
        when,
        visible_rows=_lap_waterfall_visible_rows(widget),
        always_show=_lap_waterfall_always_show(widget),
        fade_after_seconds=_lap_waterfall_fade_after_seconds(widget),
    )


def lap_waterfall_states_for_widgets(
    hud_config: HudConfig,
    laps: list[ActivityLap],
    when: datetime,
) -> dict[str, LapWaterfallState]:
    return {
        widget.id: lap_waterfall_state_for_widget(widget, laps, when)
        for widget in hud_config.widgets
        if widget.visible and widget.type == "lap_waterfall"
    }


def _lap_waterfall_visible_rows(widget: HudWidgetConfig) -> int:
    value = widget.style.get("visible_rows", LAP_WATERFALL_DEFAULT_VISIBLE_ROWS)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"widget '{widget.id}' style.visible_rows must be a positive integer")
    return value


def _lap_waterfall_always_show(widget: HudWidgetConfig) -> bool:
    value = widget.style.get("always_show", False)
    if not isinstance(value, bool):
        raise ValueError(f"widget '{widget.id}' style.always_show must be a boolean")
    return value


def _lap_waterfall_fade_after_seconds(widget: HudWidgetConfig) -> float:
    value = widget.style.get("fade_after_seconds", LAP_WATERFALL_DEFAULT_FADE_AFTER_SECONDS)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"widget '{widget.id}' style.fade_after_seconds must be a positive number")
    return float(value)


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
