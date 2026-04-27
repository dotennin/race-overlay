from datetime import datetime, timedelta, timezone

import pytest

from race_overlay.models import ActivityLap, ActivitySample, ActivityTrack
from race_overlay.sampling import lap_waterfall_state, sample_at


def _make_lap(start: datetime, duration_s: float, distance_m: float = 1000.0) -> ActivityLap:
    return ActivityLap(
        start_time=start,
        total_time_seconds=duration_s,
        distance_m=distance_m,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        max_speed_mps=None,
        elevation_delta_m=None,
        calories=None,
    )


def test_sample_at_interpolates_distance_heart_rate_and_altitude() -> None:
    activity = ActivityTrack(
        sport="Running",
        samples=[
            ActivitySample(datetime(2026, 4, 19, 0, 45, 5, tzinfo=timezone.utc), 36.0, 140.0, -1.4, 0.0, 4.0, 120, 90),
            ActivitySample(datetime(2026, 4, 19, 0, 45, 15, tzinfo=timezone.utc), 36.1, 140.1, -1.0, 40.0, 5.0, 130, 92),
        ],
    )

    hud_value = sample_at(activity, datetime(2026, 4, 19, 0, 45, 10, tzinfo=timezone.utc))
    assert round(hud_value.distance_m, 1) == 20.0
    assert hud_value.heart_rate_bpm == 125
    assert round(hud_value.speed_mps, 1) == 4.5
    assert round(hud_value.altitude_m, 2) == -1.2


# ── lap_waterfall_state ──────────────────────────────────────────────────────


def test_lap_waterfall_state_no_laps_returns_zero_opacity() -> None:
    when = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    state = lap_waterfall_state([], when)
    assert state.opacity == 0.0
    assert state.completed_laps == []
    assert state.visible_rows == []
    assert state.newest_lap_index is None


def test_lap_waterfall_state_no_completed_laps_returns_zero_opacity() -> None:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    lap = _make_lap(start, duration_s=300.0)
    # "when" is before the lap ends
    when = start + timedelta(seconds=100)
    state = lap_waterfall_state([lap], when)
    assert state.opacity == 0.0
    assert state.completed_laps == []


def test_lap_waterfall_state_completed_lap_always_show_opacity_1() -> None:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    lap = _make_lap(start, duration_s=300.0)
    # "when" is after the lap ends
    when = start + timedelta(seconds=400)
    state = lap_waterfall_state([lap], when, always_show=True)
    assert state.opacity == 1.0
    assert len(state.completed_laps) == 1
    assert state.newest_lap_index == 0


def test_lap_waterfall_state_fade_out_linear() -> None:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    lap = _make_lap(start, duration_s=300.0)
    lap_end = start + timedelta(seconds=300)
    fade_after_seconds = 60.0

    # Immediately after lap ends → opacity 1.0
    state_full = lap_waterfall_state([lap], lap_end, always_show=False, fade_after_seconds=fade_after_seconds)
    assert state_full.opacity == pytest.approx(1.0)

    # Halfway through fade window → opacity ~0.5
    halfway = lap_end + timedelta(seconds=30)
    state_half = lap_waterfall_state([lap], halfway, always_show=False, fade_after_seconds=fade_after_seconds)
    assert state_half.opacity == pytest.approx(0.5)

    # At end of fade window → opacity 0.0
    faded = lap_end + timedelta(seconds=60)
    state_faded = lap_waterfall_state([lap], faded, always_show=False, fade_after_seconds=fade_after_seconds)
    assert state_faded.opacity == pytest.approx(0.0)

    # Beyond fade window → opacity 0.0
    beyond = lap_end + timedelta(seconds=120)
    state_beyond = lap_waterfall_state([lap], beyond, always_show=False, fade_after_seconds=fade_after_seconds)
    assert state_beyond.opacity == pytest.approx(0.0)


def test_lap_waterfall_state_visible_rows_window() -> None:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    laps = [_make_lap(start + timedelta(seconds=i * 300), duration_s=300.0) for i in range(6)]
    # All 6 laps completed
    when = start + timedelta(seconds=6 * 300 + 1)
    state = lap_waterfall_state(laps, when, visible_rows=4, always_show=True)
    assert len(state.completed_laps) == 6
    assert len(state.visible_rows) == 4
    # Visible rows should be the last 4 completed laps (indices 2,3,4,5)
    assert state.visible_rows[-1].lap_index == 5
    assert state.visible_rows[0].lap_index == 2


def test_lap_waterfall_state_window_not_full_no_dimming() -> None:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    laps = [_make_lap(start + timedelta(seconds=i * 300), duration_s=300.0) for i in range(3)]
    when = start + timedelta(seconds=3 * 300 + 1)
    state = lap_waterfall_state(laps, when, visible_rows=4, always_show=True)
    assert len(state.visible_rows) == 3
    # Window is not full → no row is dimmed
    assert not any(row.is_dimmed for row in state.visible_rows)
    assert state.oldest_row_dimmed is False


def test_lap_waterfall_state_window_full_oldest_row_dimmed() -> None:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    laps = [_make_lap(start + timedelta(seconds=i * 300), duration_s=300.0) for i in range(4)]
    when = start + timedelta(seconds=4 * 300 + 1)
    state = lap_waterfall_state(laps, when, visible_rows=4, always_show=True)
    assert len(state.visible_rows) == 4
    assert state.oldest_row_dimmed is True
    assert state.visible_rows[0].is_dimmed is True
    assert all(not row.is_dimmed for row in state.visible_rows[1:])


def test_lap_waterfall_state_newest_lap_index_is_last_completed() -> None:
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    laps = [_make_lap(start + timedelta(seconds=i * 300), duration_s=300.0) for i in range(3)]
    # Only first 2 laps completed
    when = start + timedelta(seconds=2 * 300 + 1)
    state = lap_waterfall_state(laps, when, always_show=True)
    assert state.newest_lap_index == 1


def test_lap_waterfall_state_visible_rows_zero_raises() -> None:
    """visible_rows=0 must raise ValueError; slicing with [-0:] would silently return all rows."""
    when = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="visible_rows"):
        lap_waterfall_state([], when, visible_rows=0)


def test_lap_waterfall_state_visible_rows_negative_raises() -> None:
    """visible_rows < 1 must always raise ValueError."""
    when = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="visible_rows"):
        lap_waterfall_state([], when, visible_rows=-3)


def test_lap_waterfall_state_visible_rows_fewer_than_completed() -> None:
    """Fewer completed laps than visible_rows: all laps are shown, none dimmed."""
    start = datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc)
    laps = [_make_lap(start + timedelta(seconds=i * 300), duration_s=300.0) for i in range(2)]
    when = start + timedelta(seconds=2 * 300 + 1)
    state = lap_waterfall_state(laps, when, visible_rows=5, always_show=True)
    assert len(state.visible_rows) == 2
    assert not state.oldest_row_dimmed
