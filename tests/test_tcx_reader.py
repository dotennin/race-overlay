from pathlib import Path

from race_overlay.activity.loader import load_activity


def test_load_activity_reads_tcx_trackpoints() -> None:
    fixture = Path("tests/fixtures/sample_activity.tcx")
    activity = load_activity(fixture)

    assert activity.sport == "Running"
    assert len(activity.samples) == 3
    assert activity.samples[0].distance_m == 2.9
    assert activity.samples[1].heart_rate_bpm == 102
    assert round(activity.samples[2].speed_mps, 3) == 2.809
