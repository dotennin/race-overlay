from race_overlay.models import ActivityTrack, HudSample


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
