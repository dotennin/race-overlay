from datetime import datetime, timezone

from race_overlay.models import ActivitySample, ActivityTrack
from race_overlay.sampling import sample_at


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
