from pathlib import Path

from race_overlay.activity.loader import load_activity


def test_load_activity_normalizes_running_tcx_run_cadence(tmp_path: Path) -> None:
    tcx_path = tmp_path / "cadence.tcx"
    tcx_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap StartTime="2026-04-19T00:45:05Z">
        <Track>
          <Trackpoint>
            <Time>2026-04-19T00:45:05Z</Time>
            <Extensions><ns3:TPX><ns3:RunCadence>92</ns3:RunCadence></ns3:TPX></Extensions>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>""",
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.sport == "Running"
    assert activity.samples[0].cadence_spm == 184


def test_load_activity_reads_tcx_trackpoints() -> None:
    fixture = Path("tests/fixtures/sample_activity.tcx")
    activity = load_activity(fixture)

    assert activity.sport == "Running"
    assert len(activity.samples) == 3
    assert activity.samples[0].distance_m == 2.9
    assert activity.samples[1].heart_rate_bpm == 102
    assert round(activity.samples[2].speed_mps, 3) == 2.809
