from datetime import datetime, timezone
from pathlib import Path

import pytest

from race_overlay.activity.loader import load_activity
from race_overlay.models import ActivityLap


def _make_lap_tcx(*, laps_xml: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
  <Activities>
    <Activity Sport="Running">
      {laps_xml}
    </Activity>
  </Activities>
</TrainingCenterDatabase>"""


def test_activity_track_has_laps_attribute() -> None:
    """ActivityTrack must expose a laps list (may be empty)."""
    fixture = Path("tests/fixtures/sample_activity.tcx")
    activity = load_activity(fixture)
    assert hasattr(activity, "laps")
    assert isinstance(activity.laps, list)


def test_laps_parsed_from_tcx_lap_nodes(tmp_path: Path) -> None:
    tcx_path = tmp_path / "laps.tcx"
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap StartTime="2026-04-19T00:45:05Z">
        <TotalTimeSeconds>220.0</TotalTimeSeconds>
        <DistanceMeters>1000.0</DistanceMeters>
        <AverageHeartRateBpm><Value>121</Value></AverageHeartRateBpm>
        <MaximumHeartRateBpm><Value>157</Value></MaximumHeartRateBpm>
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:05Z</Time><AltitudeMeters>10.0</AltitudeMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:45:30Z</Time><AltitudeMeters>15.0</AltitudeMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:48:45Z</Time><AltitudeMeters>20.0</AltitudeMeters></Trackpoint>
        </Track>
      </Lap>
      <Lap StartTime="2026-04-19T00:48:45Z">
        <TotalTimeSeconds>195.0</TotalTimeSeconds>
        <DistanceMeters>900.0</DistanceMeters>
        <Track>
          <Trackpoint><Time>2026-04-19T00:48:45Z</Time><AltitudeMeters>20.0</AltitudeMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:52:00Z</Time><AltitudeMeters>18.0</AltitudeMeters></Trackpoint>
        </Track>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert len(activity.laps) == 2

    lap0 = activity.laps[0]
    assert isinstance(lap0, ActivityLap)
    assert lap0.total_time_seconds == 220.0
    assert lap0.distance_m == 1000.0
    assert lap0.avg_heart_rate_bpm == 121
    assert lap0.max_heart_rate_bpm == 157

    lap1 = activity.laps[1]
    assert lap1.total_time_seconds == 195.0
    assert lap1.distance_m == 900.0
    assert lap1.avg_heart_rate_bpm is None
    assert lap1.max_heart_rate_bpm is None


def test_lap_elevation_delta_derived_from_first_last_trackpoints(tmp_path: Path) -> None:
    """elevation_delta_m is last-minus-first trackpoint altitude (signed net delta, not cumulative gain)."""
    tcx_path = tmp_path / "elev.tcx"
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap StartTime="2026-04-19T00:45:05Z">
        <TotalTimeSeconds>100.0</TotalTimeSeconds>
        <DistanceMeters>500.0</DistanceMeters>
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:05Z</Time><AltitudeMeters>10.0</AltitudeMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:46:00Z</Time><AltitudeMeters>15.0</AltitudeMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:46:30Z</Time><AltitudeMeters>12.0</AltitudeMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:47:45Z</Time><AltitudeMeters>18.0</AltitudeMeters></Trackpoint>
        </Track>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    lap = activity.laps[0]
    # net delta: last (18.0) - first (10.0) = +8.0, NOT cumulative +11.0
    assert lap.elevation_delta_m == pytest.approx(8.0, abs=0.01)


def test_lap_elevation_delta_negative_for_descending_lap(tmp_path: Path) -> None:
    """A lap that ends lower than it started yields a negative elevation_delta_m."""
    tcx_path = tmp_path / "descent.tcx"
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap StartTime="2026-04-19T00:45:05Z">
        <TotalTimeSeconds>60.0</TotalTimeSeconds>
        <DistanceMeters>300.0</DistanceMeters>
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:05Z</Time><AltitudeMeters>20.0</AltitudeMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:45:35Z</Time><AltitudeMeters>14.0</AltitudeMeters></Trackpoint>
        </Track>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.laps[0].elevation_delta_m == pytest.approx(-6.0, abs=0.01)


def test_lap_elevation_delta_none_when_no_altitude(tmp_path: Path) -> None:
    """If no trackpoints have altitude, elevation_delta_m must be None."""
    tcx_path = tmp_path / "no_elev.tcx"
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap StartTime="2026-04-19T00:45:05Z">
        <TotalTimeSeconds>60.0</TotalTimeSeconds>
        <DistanceMeters>200.0</DistanceMeters>
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:05Z</Time></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:45:35Z</Time></Trackpoint>
        </Track>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.laps[0].elevation_delta_m is None


def test_existing_fixture_laps_empty_for_legacy_format() -> None:
    """The sample_activity.tcx fixture has no <Lap> wrapper => laps list is empty."""
    fixture = Path("tests/fixtures/sample_activity.tcx")
    activity = load_activity(fixture)
    assert activity.laps == []


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


def test_load_activity_reads_cycling_tcx_trackpoint_cadence(tmp_path: Path) -> None:
    tcx_path = tmp_path / "cycling_cadence.tcx"
    tcx_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
  <Activities>
    <Activity Sport="Biking">
      <Lap StartTime="2026-04-19T00:45:05Z">
        <Track>
          <Trackpoint>
            <Time>2026-04-19T00:45:05Z</Time>
            <Cadence>88</Cadence>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>""",
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.sport == "Biking"
    assert activity.samples[0].cadence_spm == 88


def test_lap_total_time_derived_from_trackpoints_when_summary_absent(tmp_path: Path) -> None:
    """total_time_seconds is derived from first/last trackpoint timestamps when the summary field is absent."""
    tcx_path = tmp_path / "no_time.tcx"
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap StartTime="2026-04-19T00:45:05Z">
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:05Z</Time></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:45:35Z</Time></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:47:05Z</Time></Trackpoint>
        </Track>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    # 2 minutes = 120 seconds from first to last trackpoint
    assert activity.laps[0].total_time_seconds == pytest.approx(120.0)


def test_lap_distance_derived_from_trackpoint_delta_when_summary_absent(tmp_path: Path) -> None:
    """distance_m is derived as last minus first trackpoint DistanceMeters (lap delta, not absolute total)."""
    tcx_path = tmp_path / "no_dist.tcx"
    # Lap trackpoints carry cumulative activity distance: 1000m, 1250m, 1900m.
    # Lap distance must be the delta: 1900 - 1000 = 900m, NOT the absolute 1900m.
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap StartTime="2026-04-19T00:45:05Z">
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:05Z</Time><DistanceMeters>1000.0</DistanceMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:45:35Z</Time><DistanceMeters>1250.0</DistanceMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:47:05Z</Time><DistanceMeters>1900.0</DistanceMeters></Trackpoint>
        </Track>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.laps[0].distance_m == pytest.approx(900.0)


def test_lap_max_speed_derived_from_trackpoints_when_summary_absent(tmp_path: Path) -> None:
    """max_speed_mps is derived from the max trackpoint speed when the lap summary field is absent."""
    tcx_path = tmp_path / "no_speed.tcx"
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
            <Extensions><ns3:TPX><ns3:Speed>2.5</ns3:Speed></ns3:TPX></Extensions>
          </Trackpoint>
          <Trackpoint>
            <Time>2026-04-19T00:45:35Z</Time>
            <Extensions><ns3:TPX><ns3:Speed>3.8</ns3:Speed></ns3:TPX></Extensions>
          </Trackpoint>
          <Trackpoint>
            <Time>2026-04-19T00:47:05Z</Time>
            <Extensions><ns3:TPX><ns3:Speed>3.1</ns3:Speed></ns3:TPX></Extensions>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>""",
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.laps[0].max_speed_mps == pytest.approx(3.8)


def test_lap_summary_fields_preferred_over_trackpoint_fallback(tmp_path: Path) -> None:
    """When summary fields are present, they take priority over trackpoint-derived values."""
    tcx_path = tmp_path / "with_summary.tcx"
    tcx_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap StartTime="2026-04-19T00:45:05Z">
        <TotalTimeSeconds>300.0</TotalTimeSeconds>
        <DistanceMeters>1500.0</DistanceMeters>
        <MaximumSpeed>4.5</MaximumSpeed>
        <Track>
          <Trackpoint>
            <Time>2026-04-19T00:45:05Z</Time>
            <DistanceMeters>0.0</DistanceMeters>
            <Extensions><ns3:TPX><ns3:Speed>2.0</ns3:Speed></ns3:TPX></Extensions>
          </Trackpoint>
          <Trackpoint>
            <Time>2026-04-19T00:46:05Z</Time>
            <DistanceMeters>100.0</DistanceMeters>
            <Extensions><ns3:TPX><ns3:Speed>2.5</ns3:Speed></ns3:TPX></Extensions>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>""",
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    lap = activity.laps[0]
    assert lap.total_time_seconds == pytest.approx(300.0)
    assert lap.distance_m == pytest.approx(1500.0)
    assert lap.max_speed_mps == pytest.approx(4.5)


def test_load_activity_reads_tcx_trackpoints() -> None:
    fixture = Path("tests/fixtures/sample_activity.tcx")
    activity = load_activity(fixture)

    assert activity.sport == "Running"
    assert len(activity.samples) == 3
    assert activity.samples[0].distance_m == 2.9
    assert activity.samples[1].heart_rate_bpm == 102
    assert round(activity.samples[2].speed_mps, 3) == 2.809


def test_derive_total_time_returns_zero_when_no_trackpoints(tmp_path: Path) -> None:
    """_derive_total_time fallback: 0.0 when lap has no timestamped trackpoints at all."""
    tcx_path = tmp_path / "no_tp.tcx"
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap StartTime="2026-04-19T00:45:05Z">
        <Track/>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.laps[0].total_time_seconds == 0.0


def test_derive_total_time_returns_zero_when_single_trackpoint(tmp_path: Path) -> None:
    """_derive_total_time fallback: 0.0 when only one timestamped trackpoint exists (no interval to measure)."""
    tcx_path = tmp_path / "one_tp.tcx"
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap StartTime="2026-04-19T00:45:05Z">
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:05Z</Time></Trackpoint>
        </Track>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.laps[0].total_time_seconds == 0.0


def test_lap_missing_start_time_raises_value_error(tmp_path: Path) -> None:
    """A <Lap> element without a StartTime attribute must raise a clear ValueError."""
    tcx_path = tmp_path / "no_start_time.tcx"
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap>
        <TotalTimeSeconds>60.0</TotalTimeSeconds>
        <DistanceMeters>200.0</DistanceMeters>
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:05Z</Time></Trackpoint>
        </Track>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="StartTime"):
        load_activity(tcx_path)


def test_laps_parsed_start_time(tmp_path: Path) -> None:
    """start_time is parsed from the Lap StartTime attribute."""
    tcx_path = tmp_path / "start_time.tcx"
    tcx_path.write_text(
        _make_lap_tcx(
            laps_xml="""
      <Lap StartTime="2026-04-19T00:45:05Z">
        <TotalTimeSeconds>60.0</TotalTimeSeconds>
        <DistanceMeters>200.0</DistanceMeters>
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:05Z</Time></Trackpoint>
        </Track>
      </Lap>"""
        ),
        encoding="utf-8",
    )

    activity = load_activity(tcx_path)

    assert activity.laps[0].start_time == datetime(2026, 4, 19, 0, 45, 5, tzinfo=timezone.utc)
