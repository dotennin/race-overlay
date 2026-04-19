from pathlib import Path

from race_overlay.activity.fit_reader import read_fit
from race_overlay.activity.tcx_reader import read_tcx
from race_overlay.models import ActivityTrack


def load_activity(path: Path) -> ActivityTrack:
    suffix = path.suffix.lower()
    if suffix == ".fit":
        return read_fit(path)
    if suffix == ".tcx":
        return read_tcx(path)
    raise ValueError(f"Unsupported activity file: {path}")
