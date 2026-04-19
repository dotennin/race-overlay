from datetime import datetime, timezone
import os
from pathlib import Path
import time

from PIL import Image
import pytest

from race_overlay.hud import HudLayout, render_hud_frame
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig
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


def test_render_hud_frame_requires_explicit_hud_config_or_legacy_layout() -> None:
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

    with pytest.raises(TypeError, match="hud_config"):
        render_hud_frame(
            width=1280,
            height=720,
            hud_value=hud_value,
            route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
            elapsed_seconds=6852,
        )


def test_render_hud_frame_rejects_unknown_widget_types() -> None:
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

    with pytest.raises(ValueError, match="unknown widget type"):
        render_hud_frame(
            width=1280,
            height=720,
            hud_value=hud_value,
            route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
            hud_config=HudConfig(
                preset="broken",
                theme=HudThemeConfig(),
                widgets=[
                    HudWidgetConfig(
                        id="mystery-widget",
                        type="mystery_widget",
                        bindings={"value": "distance_m"},
                        anchor="top-left",
                        x=24,
                        y=24,
                        width=160,
                        height=96,
                    )
                ],
            ),
            elapsed_seconds=6852,
        )


def test_render_hud_frame_rejects_hidden_unknown_widget_types() -> None:
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

    with pytest.raises(ValueError, match="unknown widget type"):
        render_hud_frame(
            width=1280,
            height=720,
            hud_value=hud_value,
            route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
            hud_config=HudConfig(
                preset="broken",
                theme=HudThemeConfig(),
                widgets=[
                    HudWidgetConfig(
                        id="hidden-mystery-widget",
                        type="mystery_widget",
                        bindings={"value": "distance_m"},
                        anchor="top-left",
                        x=24,
                        y=24,
                        width=160,
                        height=96,
                        visible=False,
                    )
                ],
            ),
            elapsed_seconds=6852,
        )


def test_render_hud_frame_rejects_unsupported_metric_bindings() -> None:
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

    with pytest.raises(ValueError, match="unsupported binding"):
        render_hud_frame(
            width=1280,
            height=720,
            hud_value=hud_value,
            route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
            hud_config=HudConfig(
                preset="broken",
                theme=HudThemeConfig(),
                widgets=[
                    HudWidgetConfig(
                        id="metric-power",
                        type="metric_card",
                        bindings={"value": "power_watts"},
                        anchor="top-left",
                        x=24,
                        y=24,
                        width=160,
                        height=96,
                    )
                ],
            ),
            elapsed_seconds=6852,
        )


def test_render_hud_frame_rejects_hud_config_and_layout_together() -> None:
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

    with pytest.raises(TypeError, match="hud_config.*layout"):
        render_hud_frame(
            width=1280,
            height=720,
            hud_value=hud_value,
            route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
            hud_config=broadcast_runner_preset(),
            layout=HudLayout.default(),
            elapsed_seconds=6852,
        )


def test_hud_layout_does_not_expose_lossy_hud_config_conversion_helper() -> None:
    assert not hasattr(HudLayout, "to_hud_config")


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
