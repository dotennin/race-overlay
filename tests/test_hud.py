from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from race_overlay.hud import HudLayout, render_hud_frame
from race_overlay.models import HudSample


def test_render_hud_frame_creates_transparent_rgba_image(tmp_path: Path) -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 0, 45, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        distance_m=12000.0,
        speed_mps=4.5,
        pace_seconds_per_km=222.2,
        heart_rate_bpm=158,
        cadence_spm=182,
    )
    route = [(36.0832, 140.2106), (36.0834, 140.2108)]
    image = render_hud_frame(
        width=1280,
        height=720,
        hud_value=hud_value,
        route_points=route,
        layout=HudLayout.default(),
        elapsed_seconds=3600,
    )

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (1280, 720)
    assert image.getbbox() is not None
