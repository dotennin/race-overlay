from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

from race_overlay.models import ActivitySample, ActivityTrack

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
                cadence_spm=_normalize_run_cadence(
                    _find_int(point, "tcx:Extensions/ns3:TPX/ns3:RunCadence"),
                    sport,
                ),
            )
        )
    return ActivityTrack(sport=sport, samples=samples)
