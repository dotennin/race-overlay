from pathlib import Path

from fitparse import FitFile

from race_overlay.models import ActivitySample, ActivityTrack

SEMICIRCLE = 180 / 2**31


def _to_degrees(value: int | None) -> float | None:
    if value is None:
        return None
    return value * SEMICIRCLE


def parse_fit_records(records) -> ActivityTrack:
    samples: list[ActivitySample] = []
    for record in records:
        samples.append(
            ActivitySample(
                timestamp=record.get_value("timestamp"),
                latitude=_to_degrees(record.get_value("position_lat")),
                longitude=_to_degrees(record.get_value("position_long")),
                altitude_m=record.get_value("altitude"),
                distance_m=record.get_value("distance"),
                speed_mps=record.get_value("enhanced_speed") or record.get_value("speed"),
                heart_rate_bpm=record.get_value("heart_rate"),
                cadence_spm=record.get_value("cadence"),
            )
        )
    return ActivityTrack(sport="Running", samples=samples)


def read_fit(path: Path) -> ActivityTrack:
    fit_file = FitFile(path)
    records = fit_file.get_messages("record")
    return parse_fit_records(records)
