from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

from race_overlay.models import ActivityLap, ActivitySample, ActivityTrack

NS = {
    "tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
    "ns3": "http://www.garmin.com/xmlschemas/ActivityExtension/v2",
}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _find_float(point: ET.Element, query: str) -> float | None:
    value = point.findtext(query, namespaces=NS)
    return float(value) if value is not None else None


def _find_int(point: ET.Element, query: str) -> int | None:
    value = point.findtext(query, namespaces=NS)
    return int(value) if value is not None else None


def _normalize_run_cadence(value: int | None, sport: str) -> int | None:
    if value is None:
        return None
    if sport.lower() != "running":
        return value
    return value * 2


def _parse_cadence(point: ET.Element, sport: str) -> int | None:
    run_cadence = _find_int(point, "tcx:Extensions/ns3:TPX/ns3:RunCadence")
    if sport.lower() == "running":
        return _normalize_run_cadence(run_cadence, sport)
    trackpoint_cadence = _find_int(point, "tcx:Cadence")
    if trackpoint_cadence is not None:
        return trackpoint_cadence
    return run_cadence


def _derive_elevation_delta(lap_el: ET.Element) -> float | None:
    """Return signed net elevation delta (last minus first trackpoint altitude) in metres.

    A positive value means the lap ended higher than it started; negative means
    it ended lower.  Returns ``None`` when fewer than two altitude readings are
    available.
    """
    altitudes = [
        float(alt)
        for tp in lap_el.findall("tcx:Track/tcx:Trackpoint", NS)
        if (alt := tp.findtext("tcx:AltitudeMeters", namespaces=NS)) is not None
    ]
    if len(altitudes) < 2:
        return None
    return altitudes[-1] - altitudes[0]


def _derive_total_time(lap_el: ET.Element) -> float:
    """Return elapsed seconds between the first and last timestamped trackpoints.

    Returns 0.0 when fewer than two timestamped trackpoints are present — there
    is no interval to measure, so zero is the intentional sentinel value.
    """
    times = [
        _parse_time(t)
        for tp in lap_el.findall("tcx:Track/tcx:Trackpoint", NS)
        if (t := tp.findtext("tcx:Time", namespaces=NS)) is not None
    ]
    if len(times) < 2:
        # Cannot derive a duration from zero or one timestamp.
        return 0.0
    return (times[-1] - times[0]).total_seconds()


def _derive_distance(lap_el: ET.Element) -> float:
    """Return lap distance in metres derived from trackpoint data.

    TCX ``DistanceMeters`` on a trackpoint is cumulative distance since the
    start of the *activity* (not the lap), so the lap distance is
    ``last - first``.  Returns 0.0 when no distance trackpoints are present.
    """
    distances = [
        float(d)
        for tp in lap_el.findall("tcx:Track/tcx:Trackpoint", NS)
        if (d := tp.findtext("tcx:DistanceMeters", namespaces=NS)) is not None
    ]
    if not distances:
        return 0.0
    return distances[-1] - distances[0]


def _derive_max_speed(lap_el: ET.Element) -> float | None:
    """Return the maximum speed in m/s across all trackpoints in the lap.

    Returns ``None`` when no speed readings are present in the lap's
    trackpoints (e.g. the device did not record the ``Speed`` extension field).
    """
    speeds = [
        float(s)
        for tp in lap_el.findall("tcx:Track/tcx:Trackpoint", NS)
        if (s := tp.findtext("tcx:Extensions/ns3:TPX/ns3:Speed", namespaces=NS)) is not None
    ]
    return max(speeds) if speeds else None


def _parse_lap_start_time(lap_el: ET.Element) -> datetime:
    raw = lap_el.attrib.get("StartTime")
    if raw is None:
        raise ValueError(
            f"<Lap> element is missing the required StartTime attribute: "
            f"{ET.tostring(lap_el, encoding='unicode')[:120]}"
        )
    return _parse_time(raw)


def _parse_lap(lap_el: ET.Element) -> ActivityLap:
    total_time_raw = lap_el.findtext("tcx:TotalTimeSeconds", namespaces=NS)
    distance_raw = lap_el.findtext("tcx:DistanceMeters", namespaces=NS)
    max_speed_raw = lap_el.findtext("tcx:MaximumSpeed", namespaces=NS)

    return ActivityLap(
        start_time=_parse_lap_start_time(lap_el),
        total_time_seconds=float(total_time_raw) if total_time_raw is not None else _derive_total_time(lap_el),
        distance_m=float(distance_raw) if distance_raw is not None else _derive_distance(lap_el),
        avg_heart_rate_bpm=_find_int(lap_el, "tcx:AverageHeartRateBpm/tcx:Value"),
        max_heart_rate_bpm=_find_int(lap_el, "tcx:MaximumHeartRateBpm/tcx:Value"),
        max_speed_mps=float(max_speed_raw) if max_speed_raw is not None else _derive_max_speed(lap_el),
        elevation_delta_m=_derive_elevation_delta(lap_el),
        calories=_find_int(lap_el, "tcx:Calories"),
    )


def read_tcx(path: Path) -> ActivityTrack:
    root = ET.parse(path).getroot()
    activity = root.find(".//tcx:Activity", NS)
    sport = activity.attrib["Sport"]
    samples: list[ActivitySample] = []
    for point in root.findall(".//tcx:Trackpoint", NS):
        samples.append(
            ActivitySample(
                timestamp=_parse_time(point.findtext("tcx:Time", namespaces=NS)),
                latitude=_find_float(point, "tcx:Position/tcx:LatitudeDegrees"),
                longitude=_find_float(point, "tcx:Position/tcx:LongitudeDegrees"),
                altitude_m=_find_float(point, "tcx:AltitudeMeters"),
                distance_m=_find_float(point, "tcx:DistanceMeters"),
                speed_mps=_find_float(point, "tcx:Extensions/ns3:TPX/ns3:Speed"),
                heart_rate_bpm=_find_int(point, "tcx:HeartRateBpm/tcx:Value"),
                cadence_spm=_parse_cadence(point, sport),
            )
        )
    laps = [_parse_lap(lap_el) for lap_el in activity.findall("tcx:Lap", NS)]
    return ActivityTrack(sport=sport, samples=samples, laps=laps)
