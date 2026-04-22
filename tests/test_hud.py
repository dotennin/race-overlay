from datetime import datetime, timezone
import os
from pathlib import Path
import time

from PIL import Image, ImageDraw
import pytest

import race_overlay.hud as hud_module
import inspect

from race_overlay.hud import (
    HudLayout,
    RenderScale,
    _draw_progress_bar,
    _metric_value,
    _metric_suffix,
    _scaled_font,
    _widget_panel_enabled,
    render_hud_frame,
    validate_hud_config,
)
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.models import HudSample


def _rendered_text_labels(
    monkeypatch: pytest.MonkeyPatch,
    hud_config: HudConfig,
    *,
    total_distance_m: float | None = None,
    hud_value: HudSample | None = None,
    route_points: list[tuple[float, float]] | None = None,
) -> list[str]:
    labels: list[str] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        labels.append(str(text))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)
    render_hud_frame(
        width=1280,
        height=720,
        hud_value=hud_value
        or HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=route_points or [(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=hud_config,
        elapsed_seconds=6852,
        total_distance_m=total_distance_m,
    )
    return labels


def _rendered_text_calls(
    monkeypatch: pytest.MonkeyPatch,
    hud_config: HudConfig,
    *,
    total_distance_m: float | None = None,
    hud_value: HudSample | None = None,
    route_points: list[tuple[float, float]] | None = None,
) -> list[tuple[str, int | None]]:
    calls: list[tuple[str, int | None]] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        calls.append((str(text), getattr(kwargs.get("font"), "size", None)))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)
    render_hud_frame(
        width=1280,
        height=720,
        hud_value=hud_value
        or HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=route_points or [(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=hud_config,
        elapsed_seconds=6852,
        total_distance_m=total_distance_m,
    )
    return calls


def test_render_hud_frame_creates_transparent_rgba_image(tmp_path: Path) -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 0, 45, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
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


def test_render_hud_frame_draws_hud_v2_regions(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(monkeypatch, broadcast_runner_preset())
    image = render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=133,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert "Elevation" in labels
    assert "Distance" in labels
    assert "Heart rate" in labels
    assert image.getpixel((640, 70))[3] > 0
    assert image.getpixel((90, 610))[3] > 0
    assert image.getpixel((58, 167))[3] > 0
    assert image.getpixel((1145, 155))[3] > 0


def test_render_hud_frame_hides_metric_units_when_theme_disables_units(monkeypatch: pytest.MonkeyPatch) -> None:
    preset = broadcast_runner_preset()
    preset.theme.show_units = False

    labels = _rendered_text_labels(monkeypatch, preset)

    assert "KM" not in labels
    assert "BPM" not in labels
    assert "/km" not in labels


def test_render_hud_frame_shows_current_and_total_distance_on_ruler_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(monkeypatch, broadcast_runner_preset(), total_distance_m=10000.0)

    assert any("Distance" in label for label in labels)
    assert any("24.60" in label for label in labels)
    assert any("24.60" in label and "KM" in label for label in labels)
    assert any("24.60" in label and "10.00" in label for label in labels) or any(
        "10.00" in label and "KM" in label for label in labels
    )


def test_validate_hud_config_rejects_unknown_font_family() -> None:
    preset = broadcast_runner_preset()
    preset.theme.font_family = "comic-sans"

    with pytest.raises(ValueError, match="font_family"):
        validate_hud_config(preset)


def test_validate_hud_config_rejects_invalid_theme_text_rgba() -> None:
    config = HudConfig(
        preset="metric-only",
        theme=HudThemeConfig(text_rgba=["x", 255, 255, 255]),
        widgets=[
            HudWidgetConfig(
                id="heart",
                type="metric_card",
                bindings={"value": "heart_rate_bpm"},
                anchor="top-left",
                x=0,
                y=0,
                width=180,
                height=96,
            )
        ],
    )

    with pytest.raises(ValueError, match="text_rgba"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_string_theme_note_text() -> None:
    config = HudConfig(
        preset="metric-only",
        theme=HudThemeConfig(note_text=123),
        widgets=[
            HudWidgetConfig(
                id="heart",
                type="metric_card",
                bindings={"value": "heart_rate_bpm"},
                anchor="top-left",
                x=0,
                y=0,
                width=180,
                height=96,
            )
        ],
    )

    with pytest.raises(ValueError, match="note_text"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_integer_widget_font_size() -> None:
    preset = broadcast_runner_preset()
    preset.widgets[0].style["font_size_px"] = 8.5

    with pytest.raises(ValueError, match="font_size_px"):
        validate_hud_config(preset)


def test_validate_hud_config_rejects_negative_stat_block_decimals() -> None:
    preset = broadcast_runner_preset()
    distance_widget = next(widget for widget in preset.widgets if widget.id == "distance-stat")
    distance_widget.style["decimals"] = -1

    with pytest.raises(ValueError, match="decimals"):
        validate_hud_config(preset)


def test_validate_hud_config_rejects_non_string_context_format() -> None:
    config = HudConfig(
        preset="context-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="time-card",
                type="context_card",
                bindings={"value": "timestamp"},
                anchor="top-left",
                x=0,
                y=0,
                width=200,
                height=72,
                style={"variant": "timestamp_chip", "format": False},
            )
        ],
    )

    with pytest.raises(ValueError, match="style.format"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_boolean_show_panel() -> None:
    config = HudConfig(
        preset="route-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=0,
                y=0,
                width=180,
                height=180,
                style={"show_panel": "false"},
            )
        ],
    )

    with pytest.raises(ValueError, match="style.show_panel"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_boolean_transparent_panel() -> None:
    config = HudConfig(
        preset="metric-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="heart",
                type="metric_card",
                bindings={"value": "heart_rate_bpm"},
                anchor="top-left",
                x=0,
                y=0,
                width=180,
                height=96,
                style={"transparent_panel": "false"},
            )
        ],
    )

    with pytest.raises(ValueError, match="style.transparent_panel"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_medium_font_weight() -> None:
    preset = broadcast_runner_preset()
    preset.theme.font_weight = "medium"

    with pytest.raises(ValueError, match="font_weight"):
        validate_hud_config(preset)


def test_validate_hud_config_rejects_non_positive_widget_dimensions() -> None:
    config = HudConfig(
        preset="route-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=0,
                y=0,
                width=-10,
                height=50,
            )
        ],
    )

    with pytest.raises(ValueError, match="width"):
        validate_hud_config(config)


def test_render_hud_frame_keeps_right_anchored_widgets_visible_on_narrower_frames() -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
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

    assert image.getpixel((965, 155))[3] > 0
    assert image.getpixel((1090, 170))[3] == 0


def test_render_hud_frame_accepts_legacy_layout_argument_without_preset_only_widgets() -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
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
        altitude_m=25.0,
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
        altitude_m=25.0,
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
        altitude_m=25.0,
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


def test_render_hud_frame_rejects_too_narrow_progress_bar_widgets() -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )

    with pytest.raises(ValueError, match="progress_bar.*minimum width"):
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
                        id="distance-progress",
                        type="progress_bar",
                        bindings={"value": "distance_m"},
                        anchor="top-left",
                        x=24,
                        y=24,
                        width=160,
                        height=64,
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
        altitude_m=25.0,
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


def test_render_hud_frame_rejects_unsupported_widget_anchors() -> None:
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )

    with pytest.raises(ValueError, match="unsupported anchor"):
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
                        id="widget-center",
                        type="metric_card",
                        bindings={"value": "heart_rate_bpm"},
                        anchor="center",
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
        altitude_m=25.0,
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
        altitude_m=25.0,
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


def test_render_hud_frame_route_map_marker_tracks_current_sample_position() -> None:
    hud_config = HudConfig(
        preset="route-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=0,
                y=0,
                width=120,
                height=120,
            )
        ],
    )
    route_points = [(35.0, 139.0), (35.5, 139.5), (36.0, 140.0)]
    first_position = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=35.0,
        longitude=139.0,
        altitude_m=25.0,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    later_position = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=35.5,
        longitude=139.5,
        altitude_m=25.0,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )

    first_image = render_hud_frame(
        width=120,
        height=120,
        hud_value=first_position,
        route_points=route_points,
        hud_config=hud_config,
        elapsed_seconds=6852,
    )
    later_image = render_hud_frame(
        width=120,
        height=120,
        hud_value=later_position,
        route_points=route_points,
        hud_config=hud_config,
        elapsed_seconds=6852,
    )

    assert list(first_image.getdata()) != list(later_image.getdata())


def test_render_hud_frame_route_map_skips_marker_when_gps_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ellipse_calls: list[tuple[object, object]] = []
    original_ellipse = ImageDraw.ImageDraw.ellipse

    def record_ellipse(self, xy, *args, **kwargs):
        ellipse_calls.append((xy, kwargs.get("fill")))
        return original_ellipse(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "ellipse", record_ellipse)

    hud_config = HudConfig(
        preset="route-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=0,
                y=0,
                width=120,
                height=120,
            )
        ],
    )
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=None,
        longitude=None,
        altitude_m=None,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )

    render_hud_frame(
        width=120,
        height=120,
        hud_value=hud_value,
        route_points=[(35.0, 139.0), (35.5, 139.5), (36.0, 140.0)],
        hud_config=hud_config,
        elapsed_seconds=6852,
    )

    assert ellipse_calls == []


def test_render_hud_frame_clips_circular_route_map_content_to_circle() -> None:
    hud_config = HudConfig(
        preset="route-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=0,
                y=0,
                width=120,
                height=120,
                style={"label": "", "shape": "circle"},
            )
        ],
    )
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=35.0,
        longitude=139.0,
        altitude_m=25.0,
        distance_m=24600.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )

    image = render_hud_frame(
        width=120,
        height=120,
        hud_value=hud_value,
        route_points=[(36.0, 139.0), (35.0, 140.0)],
        hud_config=hud_config,
        elapsed_seconds=6852,
    )

    assert image.getpixel((15, 15))[3] == 0
    assert image.getpixel((60, 6))[3] > 0


def test_render_hud_frame_route_map_renders_without_private_pillow_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    original_draw = hud_module.ImageDraw.Draw

    class PublicImageDrawProxy:
        def __init__(self, image: Image.Image) -> None:
            self._delegate = original_draw(image)

        def __getattr__(self, name: str):
            if name == "_image":
                raise AttributeError(name)
            return getattr(self._delegate, name)

    monkeypatch.setattr(hud_module.ImageDraw, "Draw", lambda image: PublicImageDrawProxy(image))

    image = render_hud_frame(
        width=120,
        height=120,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=35.5,
            longitude=139.5,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(35.0, 139.0), (35.5, 139.5), (36.0, 140.0)],
        hud_config=HudConfig(
            preset="route-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=120,
                    height=120,
                    style={"label": "", "shape": "circle"},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    assert image.getbbox() is not None


def test_draw_progress_bar_treats_zero_total_distance_as_explicit_goal(monkeypatch: pytest.MonkeyPatch) -> None:
    line_calls: list[tuple[object, object, int]] = []
    original_line = ImageDraw.ImageDraw.line

    def record_line(self, xy, fill=None, width=0, *args, **kwargs):
        line_calls.append((xy, fill, width))
        return original_line(self, xy, fill=fill, width=width, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)

    image = Image.new("RGBA", (320, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    _draw_progress_bar(
        draw,
        HudWidgetConfig(
            id="distance-progress",
            type="progress_bar",
            bindings={"value": "distance_m"},
            anchor="top-left",
            x=0,
            y=0,
            width=280,
            height=64,
        ),
        distance_m=5000.0,
        total_distance_m=0.0,
        theme=HudThemeConfig(),
        frame_width=320,
        frame_height=96,
        scale=RenderScale(x=1.0, y=1.0, draw=1.0),
    )

    assert len(line_calls) == 2


def test_metric_value_returns_placeholder_for_missing_speed() -> None:
    widget = HudWidgetConfig(
        id="metric-speed",
        type="metric_card",
        bindings={"value": "speed_mps"},
        anchor="top-left",
        x=24,
        y=24,
        width=160,
        height=96,
    )
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=24600.0,
        speed_mps=None,
        pace_seconds_per_km=None,
        heart_rate_bpm=162,
        cadence_spm=178,
    )

    assert _metric_value(widget, hud_value, elapsed_seconds=6852) == "--"


def test_render_hud_frame_route_map_uses_widget_label(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(
        monkeypatch,
        HudConfig(
            preset="route-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=24,
                    y=24,
                    width=176,
                    height=128,
                    style={"label": "Course overview"},
                )
            ],
        ),
    )

    assert "Course overview" in labels


def test_render_hud_frame_route_map_renders_navigation_overlays_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(
        monkeypatch,
        HudConfig(
            preset="route-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=24,
                    y=24,
                    width=176,
                    height=128,
                    style={"label": ""},
                )
            ],
        ),
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=35.5,
            longitude=139.5,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(36.0, 140.0), (35.0, 139.0)],
    )

    assert "N" in labels
    assert "225°SW" in labels


def test_render_hud_frame_route_map_respects_heading_arrow_style(monkeypatch: pytest.MonkeyPatch) -> None:
    polygon_calls: list[object] = []
    original_polygon = ImageDraw.ImageDraw.polygon

    def record_polygon(self, xy, *args, **kwargs):
        polygon_calls.append(xy)
        return original_polygon(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "polygon", record_polygon)

    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=35.5,
            longitude=139.5,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(36.0, 140.0), (35.0, 139.0)],
        hud_config=HudConfig(
            preset="route-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=24,
                    y=24,
                    width=176,
                    height=128,
                    style={"label": ""},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    assert polygon_calls, "expected a heading arrow polygon by default"
    polygon_calls.clear()

    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=35.5,
            longitude=139.5,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(36.0, 140.0), (35.0, 139.0)],
        hud_config=HudConfig(
            preset="route-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=24,
                    y=24,
                    width=176,
                    height=128,
                    style={"label": "", "show_heading_arrow": False},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    assert polygon_calls == []


def test_render_hud_frame_route_map_projects_heading_arrow_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_vectors: list[tuple[float, float]] = []
    original_draw_heading_arrow = hud_module._draw_heading_arrow

    def record_heading_arrow(draw, center, vector, theme, scale):
        captured_vectors.append(vector)
        return original_draw_heading_arrow(draw, center, vector, theme, scale)

    monkeypatch.setattr(hud_module, "_draw_heading_arrow", record_heading_arrow)

    render_hud_frame(
        width=180,
        height=180,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=50.0,
            longitude=0.5,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(0.0, 0.0), (100.0, 1.0)],
        hud_config=HudConfig(
            preset="route-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=180,
                    height=180,
                    style={"label": ""},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    vector_x, vector_y = captured_vectors[0]
    assert vector_x > 0
    assert vector_y < 0
    assert abs(vector_y / vector_x) < 1.0


def test_render_hud_frame_route_map_prefers_non_degenerate_segment_for_navigation_overlays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polygon_calls: list[object] = []
    original_polygon = ImageDraw.ImageDraw.polygon

    def record_polygon(self, xy, *args, **kwargs):
        polygon_calls.append(xy)
        return original_polygon(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "polygon", record_polygon)

    labels = _rendered_text_labels(
        monkeypatch,
        HudConfig(
            preset="route-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=180,
                    height=180,
                    style={"label": ""},
                )
            ],
        ),
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=0.0,
            longitude=0.0,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(0.0, 0.0), (0.0, 0.0), (0.0, 1.0)],
    )

    assert "090°E" in labels
    assert polygon_calls, "expected a heading arrow polygon for the non-degenerate segment"


def test_render_hud_frame_scales_widget_regions_for_larger_frames() -> None:
    image = render_hud_frame(
        width=2560,
        height=1440,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=133,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert image.getpixel((1280, 140))[3] > 0
    assert image.getpixel((180, 1220))[3] > 0
    assert image.getpixel((640, 70))[3] == 0
    assert image.getpixel((90, 610))[3] == 0


def test_render_hud_frame_scales_font_sizes_for_larger_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_sizes: list[int] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        font = kwargs.get("font")
        if font is not None and getattr(font, "size", None) is not None:
            seen_sizes.append(int(font.size))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)

    render_hud_frame(
        width=2560,
        height=1440,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=133,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert max(seen_sizes) >= 20


def test_render_hud_frame_context_card_uses_widget_label(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(
        monkeypatch,
        HudConfig(
            preset="context-only",
            theme=HudThemeConfig(note_text="Kasumigaura"),
            widgets=[
                HudWidgetConfig(
                    id="context-card",
                    type="context_card",
                    bindings={"value": "timestamp"},
                    anchor="top-right",
                    x=996,
                    y=120,
                    width=260,
                    height=196,
                    style={"label": "Checkpoint"},
                )
            ],
        ),
    )

    assert "Checkpoint" in labels


def test_render_hud_frame_context_card_compact_variant_uses_default_time_chip_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = _rendered_text_labels(
        monkeypatch,
        HudConfig(
            preset="context-only",
            theme=HudThemeConfig(note_text="Kasumigaura"),
            widgets=[
                HudWidgetConfig(
                    id="context-card",
                    type="context_card",
                    bindings={"value": "timestamp"},
                    anchor="top-right",
                    x=996,
                    y=120,
                    width=260,
                    height=72,
                    style={"label": "Checkpoint", "variant": "compact"},
                )
            ],
        ),
    )

    assert "2026/04/19 09:48:10" in labels


def test_render_hud_frame_context_card_timestamp_chip_variant_renders_compact_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = _rendered_text_labels(
        monkeypatch,
        HudConfig(
            preset="context-only",
            theme=HudThemeConfig(note_text="Kasumigaura"),
            widgets=[
                HudWidgetConfig(
                    id="context-card",
                    type="context_card",
                    bindings={"value": "timestamp"},
                    anchor="top-right",
                    x=996,
                    y=120,
                    width=260,
                    height=72,
                    style={"label": "Checkpoint", "variant": "timestamp_chip"},
                )
            ],
        ),
    )

    assert labels == ["2026/04/19 09:48:10"]


def test_metric_suffix_omits_elapsed_unit_by_default() -> None:
    widget = HudWidgetConfig(
        id="elapsed",
        type="metric_card",
        bindings={"value": "elapsed_seconds"},
        anchor="top-left",
        x=0,
        y=0,
        width=160,
        height=96,
    )

    assert _metric_suffix(widget, HudThemeConfig()) == ""


def test_render_hud_frame_metric_card_respects_legacy_theme_font_overrides_for_role_fonts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _rendered_text_calls(
        monkeypatch,
        HudConfig(
            preset="metric-only",
            theme=HudThemeConfig(font_family="mono", font_weight="bold", font_size_px=30),
            widgets=[
                HudWidgetConfig(
                    id="heart",
                    type="metric_card",
                    bindings={"value": "heart_rate_bpm"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=180,
                    height=96,
                    style={"label": "Heart"},
                )
            ],
        ),
    )

    assert calls == [("Heart", 30), ("162", 30), ("bpm", 30)]


def test_render_hud_frame_metric_card_allows_explicit_default_role_sizes_with_legacy_theme_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _rendered_text_calls(
        monkeypatch,
        HudConfig(
            preset="metric-only",
            theme=HudThemeConfig(font_size_px=30, title_font_size_px=18, value_font_size_px=18, unit_font_size_px=18),
            widgets=[
                HudWidgetConfig(
                    id="heart",
                    type="metric_card",
                    bindings={"value": "heart_rate_bpm"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=180,
                    height=96,
                    style={"label": "Heart"},
                )
            ],
        ),
    )

    assert calls == [("Heart", 18), ("162", 18), ("bpm", 18)]


def test_render_hud_frame_metric_card_respects_widget_font_override_for_role_fonts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _rendered_text_calls(
        monkeypatch,
        HudConfig(
            preset="metric-only",
            theme=HudThemeConfig(title_font_size_px=14, value_font_size_px=28, unit_font_size_px=10),
            widgets=[
                HudWidgetConfig(
                    id="heart",
                    type="metric_card",
                    bindings={"value": "heart_rate_bpm"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=180,
                    height=96,
                    style={"label": "Heart", "font_size_px": 26},
                )
            ],
        ),
    )

    assert calls == [("Heart", 26), ("162", 26), ("bpm", 26)]


def test_render_hud_frame_stat_block_uses_thematic_typography_roles_and_tighter_unit_spacing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_calls: list[tuple[str, tuple[int, int], str | None, int | None]] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        font = kwargs.get("font")
        text_calls.append((str(text), xy, kwargs.get("anchor"), getattr(font, "size", None)))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)

    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=HudConfig(
            preset="stat-only",
            theme=HudThemeConfig(title_font_size_px=12, value_font_size_px=30, unit_font_size_px=9),
            widgets=[
                HudWidgetConfig(
                    id="elevation",
                    type="stat_block",
                    bindings={"value": "altitude_m"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=180,
                    height=96,
                    style={"label": "Elevation", "unit": "M"},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    label_call = next(call for call in text_calls if call[0] == "Elevation")
    value_call = next(call for call in text_calls if call[0] == "25")
    unit_call = next(call for call in text_calls if call[0] == "M")

    assert label_call[3] == 12
    assert value_call[3] == 30
    assert unit_call[3] == 9
    assert unit_call[1][0] > value_call[1][0]
    assert unit_call[1][0] < 100


def test_hero_metric_km_suffix_stays_within_narrow_widget(monkeypatch: pytest.MonkeyPatch) -> None:
    """The /km suffix must be right-anchored relative to widget width, not placed at a hard-coded
    absolute x offset that overflows narrow hero_metric widgets."""
    text_calls: list[tuple[tuple[int, int], str, str | None]] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        text_calls.append((xy, str(text), kwargs.get("anchor")))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)

    widget_width = 160
    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=HudConfig(
            preset="hero-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="hero-pace",
                    type="hero_metric",
                    bindings={"value": "pace_seconds_per_km"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=widget_width,
                    height=96,
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    km_calls = [(xy, anchor) for xy, text, anchor in text_calls if text == "/km"]
    assert km_calls, "expected /km to be drawn"
    xy, anchor = km_calls[0]
    widget_right = widget_width  # widget x=0, so right = widget_width
    # Right-anchored: xy[0] is the right edge of the text; must not exceed widget boundary.
    assert anchor in ("rs", "ra", "rm"), f"/km should use a right anchor, got {anchor!r}"
    assert xy[0] <= widget_right, f"/km x={xy[0]} overflows widget right={widget_right}"


def test_draw_helpers_require_explicit_render_scale() -> None:
    """Private draw helpers must require an explicit RenderScale parameter rather than falling
    back to computing scale internally, keeping the boundary consistent with
    _resolve_widget_origin which already requires RenderScale unconditionally."""
    import race_overlay.hud as hud_module

    helpers = [
        hud_module._draw_progress_bar,
        hud_module._draw_stat_block,
        hud_module._draw_route_map,
        hud_module._draw_hero_metric,
        hud_module._draw_metric_card,
        hud_module._draw_context_card,
    ]
    for fn in helpers:
        sig = inspect.signature(fn)
        scale_param = sig.parameters.get("scale")
        assert scale_param is not None, f"{fn.__name__} missing scale parameter"
        assert scale_param.default is inspect.Parameter.empty, (
            f"{fn.__name__} has optional scale={scale_param.default!r}; "
            "should require explicit RenderScale (no internal fallback)"
        )


def test_render_hud_frame_defaults_non_map_widgets_to_transparent_panels(monkeypatch: pytest.MonkeyPatch) -> None:
    panel_fills: list[tuple[int, int, int, int]] = []
    original_rounded_rectangle = ImageDraw.ImageDraw.rounded_rectangle

    def record_rounded_rectangle(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            panel_fills.append(fill)
        return original_rounded_rectangle(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", record_rounded_rectangle)

    preset = broadcast_runner_preset()
    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=133,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=preset,
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert tuple(preset.theme.panel_rgba) not in panel_fills


def test_render_hud_frame_keeps_route_map_panel_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    ellipse_fills: list[tuple[int, int, int, int]] = []
    original_ellipse = ImageDraw.ImageDraw.ellipse

    def record_ellipse(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            ellipse_fills.append(fill)
        return original_ellipse(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "ellipse", record_ellipse)

    preset = broadcast_runner_preset()
    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=133,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=preset,
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert tuple(preset.theme.panel_rgba) in ellipse_fills


def test_render_hud_frame_honors_explicit_show_panel_override(monkeypatch: pytest.MonkeyPatch) -> None:
    panel_fills: list[tuple[int, int, int, int]] = []
    original_rounded_rectangle = ImageDraw.ImageDraw.rounded_rectangle

    def record_rounded_rectangle(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            panel_fills.append(fill)
        return original_rounded_rectangle(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", record_rounded_rectangle)

    hud_config = HudConfig(
        preset="panel-opt-in",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="pace-chip",
                type="metric_card",
                bindings={"value": "pace_seconds_per_km"},
                anchor="top-left",
                x=24,
                y=24,
                width=160,
                height=96,
                style={"label": "Pace", "show_panel": True},
            )
        ],
    )

    render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=133,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=hud_config,
        elapsed_seconds=6852,
    )

    assert tuple(hud_config.theme.panel_rgba) in panel_fills


def test_widget_panel_enabled_legacy_transparent_panel_disables_panel() -> None:
    """transparent_panel: True is the legacy opt-out; the panel must be suppressed."""
    widget = HudWidgetConfig(
        id="pace-chip",
        type="metric_card",
        bindings={"value": "pace_seconds_per_km"},
        anchor="top-left",
        x=24,
        y=24,
        width=160,
        height=96,
        style={"label": "Pace", "transparent_panel": True},
    )
    assert _widget_panel_enabled(widget) is False


def test_widget_panel_enabled_show_panel_overrides_transparent_panel() -> None:
    """Explicit show_panel: True must win over the legacy transparent_panel: True flag."""
    widget = HudWidgetConfig(
        id="pace-chip",
        type="metric_card",
        bindings={"value": "pace_seconds_per_km"},
        anchor="top-left",
        x=24,
        y=24,
        width=160,
        height=96,
        style={"label": "Pace", "transparent_panel": True, "show_panel": True},
    )
    assert _widget_panel_enabled(widget) is True


def test_scaled_font_caches_object_for_same_effective_size() -> None:
    """_scaled_font must return the identical font object for repeated calls with the
    same effective scaled size, avoiding redundant ImageFont.load_default() work."""
    scale = RenderScale(x=1.0, y=1.0, draw=1.0)
    font_a = _scaled_font(scale, 18)
    font_b = _scaled_font(scale, 18)
    assert font_a is font_b, (
        "_scaled_font should return a cached font object for the same effective size, "
        "but got two distinct objects"
    )
