from datetime import datetime, timezone
import os
from pathlib import Path
import time

from PIL import Image

from race_overlay.hud import HudLayout, render_hud_frame
from race_overlay.hud_presets import broadcast_runner_preset
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
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=3600,
    )

    assert isinstance(image, Image.Image)
    assert image.mode == "RGBA"
    assert image.size == (1280, 720)
    assert image.getbbox() is not None


def test_render_hud_frame_draws_reference_layout_regions() -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    image = render_hud_frame(
        width=1280,
        height=720,
        hud_value=hud_value,
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=6852,
    )

    assert image.getpixel((100, 90))[3] > 0
    assert image.getpixel((700, 70))[3] > 0
    assert image.getpixel((120, 220))[3] > 0
    assert image.getpixel((1080, 170))[3] > 0


def test_render_hud_frame_keeps_right_anchored_widgets_visible_on_narrower_frames() -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    image = render_hud_frame(
        width=1100,
        height=720,
        hud_value=hud_value,
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=6852,
    )

    assert image.getpixel((900, 170))[3] > 0
    assert image.getpixel((1090, 170))[3] == 0


def test_render_hud_frame_accepts_legacy_layout_argument_without_preset_only_widgets() -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    image = render_hud_frame(
        width=1280,
        height=720,
        hud_value=hud_value,
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        layout=HudLayout(
            pace_anchor=(64, 48),
            stats_anchor=(64, 180),
            map_box=(64, 360, 304, 600),
        ),
        elapsed_seconds=6852,
    )

    assert image.getpixel((50, 40))[3] > 0
    assert image.getpixel((160, 480))[3] > 0
    assert image.getpixel((700, 70))[3] == 0
    assert image.getpixel((1080, 170))[3] == 0


def test_render_hud_frame_context_card_uses_sample_timezone(monkeypatch) -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )

    original_tz = os.environ.get("TZ")
    try:
        monkeypatch.setenv("TZ", "UTC")
        time.tzset()
        utc_image = render_hud_frame(
            width=1280,
            height=720,
            hud_value=hud_value,
            route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
            hud_config=broadcast_runner_preset(),
            elapsed_seconds=6852,
        )

        monkeypatch.setenv("TZ", "America/Los_Angeles")
        time.tzset()
        la_image = render_hud_frame(
            width=1280,
            height=720,
            hud_value=hud_value,
            route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
            hud_config=broadcast_runner_preset(),
            elapsed_seconds=6852,
        )
    finally:
        if original_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", original_tz)
        time.tzset()

    assert list(utc_image.getdata()) == list(la_image.getdata())
