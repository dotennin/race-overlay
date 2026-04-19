from datetime import datetime, timezone

from race_overlay.activity.fit_reader import parse_fit_records


class FakeRecord:
    def __init__(self, **values):
        self._values = values

    def get_value(self, name: str):
        return self._values.get(name)


def test_parse_fit_records_normalizes_samples() -> None:
    records = [
        FakeRecord(
            timestamp=datetime(2026, 4, 19, 0, 45, 5, tzinfo=timezone.utc),
            position_lat=430_000_000,
            position_long=1_674_000_000,
            altitude=-1.4,
            distance=2.9,
            enhanced_speed=1.521,
            heart_rate=103,
            cadence=0,
        )
    ]

    activity = parse_fit_records(records)
    assert activity.sport == "Running"
    assert len(activity.samples) == 1
    assert activity.samples[0].heart_rate_bpm == 103
    assert round(activity.samples[0].speed_mps, 3) == 1.521
