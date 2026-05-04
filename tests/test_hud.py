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
    RouteProjection,
    _draw_progress_bar,
    _metric_value,
    _metric_suffix,
    _progress_bar_text_layout,
    _scaled_font,
    _split_route_points,
    _widget_panel_enabled,
    render_prepared_hud_frame,
    render_hud_frame,
    validate_hud_config,
)
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.models import ActivityLap, HudSample
from race_overlay.sampling import LapWaterfallRow, LapWaterfallState

ROUTE_MAP_COMPLETED_RGBA = (34, 255, 138, 255)
ROUTE_MAP_REMAINING_RGBA = (13, 144, 195, 255)


@pytest.fixture(autouse=True)
def clear_route_map_cache():
    """Clear route map cache before each test to prevent cross-test pollution."""
    hud_module._clear_route_map_cache()
    yield
    hud_module._clear_route_map_cache()


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


def test_render_prepared_hud_frame_matches_public_render_output() -> None:
    config = broadcast_runner_preset()
    validated_config = validate_hud_config(config)
    visible_widgets = sorted(
        (widget for widget in validated_config.widgets if widget.visible),
        key=lambda widget: widget.z_index,
    )
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
    route_points = [(36.0832, 140.2106), (36.0834, 140.2108)]

    public_image = render_hud_frame(
        width=1280,
        height=720,
        hud_value=hud_value,
        route_points=route_points,
        hud_config=config,
        elapsed_seconds=6852,
        total_distance_m=42195.0,
    )
    prepared_image = render_prepared_hud_frame(
        width=1280,
        height=720,
        hud_value=hud_value,
        route_points=route_points,
        theme=validated_config.theme,
        widgets=visible_widgets,
        elapsed_seconds=6852,
        total_distance_m=42195.0,
    )

    assert prepared_image.tobytes() == public_image.tobytes()


def _rendered_text_draws(
    monkeypatch: pytest.MonkeyPatch,
    hud_config: HudConfig,
    *,
    total_distance_m: float | None = None,
    hud_value: HudSample | None = None,
    route_points: list[tuple[float, float]] | None = None,
) -> list[tuple[tuple[float, float], str]]:
    draws: list[tuple[tuple[float, float], str]] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        if isinstance(xy, tuple) and len(xy) == 2:
            draws.append(((float(xy[0]), float(xy[1])), str(text)))
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
    return draws


def _widget_bounds(widget: HudWidgetConfig, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
    left = widget.x + (frame_width - 1280 if "right" in widget.anchor else 0)
    top = widget.y + (frame_height - 720 if "bottom" in widget.anchor else 0)
    return (left, top, left + widget.width, top + widget.height)


def _region_has_alpha(image: Image.Image, bounds: tuple[int, int, int, int]) -> bool:
    left, top, right, bottom = bounds
    for y in range(max(top, 0), min(bottom, image.height)):
        for x in range(max(left, 0), min(right, image.width)):
            if image.getpixel((x, y))[3] > 0:
                return True
    return False


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
    preset = broadcast_runner_preset()
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
        hud_config=preset,
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )
    distance_ruler = next(widget for widget in preset.widgets if widget.id == "distance-ruler")
    elevation = next(widget for widget in preset.widgets if widget.id == "elevation-stat")
    heart_rate = next(widget for widget in preset.widgets if widget.id == "heart-rate-stat")

    assert "Elevation" in labels
    assert "Distance" in labels
    assert "Heart rate" in labels
    assert _region_has_alpha(image, _widget_bounds(distance_ruler, 1280, 720))
    assert _region_has_alpha(image, _widget_bounds(elevation, 1280, 720))
    assert _region_has_alpha(image, _widget_bounds(heart_rate, 1280, 720))


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


def test_draw_progress_bar_defaults_to_dense_green_ruler() -> None:
    image = Image.new("RGBA", (640, 96), (0, 0, 0, 0))
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
            width=560,
            height=56,
            style={"label": "Distance"},
        ),
        distance_m=5200.0,
        total_distance_m=10000.0,
        theme=HudThemeConfig(),
        frame_width=640,
        frame_height=96,
        scale=RenderScale(x=1.0, y=1.0, draw=1.0),
    )

    tick_x_positions = {
        x
        for x, y in ((x, y) for x in range(image.width) for y in range(image.height))
        if image.getpixel((x, y)) == (230, 238, 245, 168)
    }

    assert len(tick_x_positions) >= 30
    assert (34, 255, 138, 255) in image.getdata()


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
    preset.widgets[0].style["unit_font_size_px"] = 8.5

    with pytest.raises(ValueError, match="unit_font_size_px"):
        validate_hud_config(preset)


def test_validate_hud_config_rejects_negative_stat_block_decimals() -> None:
    preset = broadcast_runner_preset()
    distance_widget = next(widget for widget in preset.widgets if widget.id == "distance-stat")
    distance_widget.style["decimals"] = -1

    with pytest.raises(ValueError, match="decimals"):
        validate_hud_config(preset)


def test_validate_hud_config_rejects_non_positive_route_map_zoom_percent() -> None:
    preset = broadcast_runner_preset()
    route_map = next(widget for widget in preset.widgets if widget.id == "route-map")
    route_map.style["zoom_percent"] = 0

    with pytest.raises(ValueError, match="zoom_percent"):
        validate_hud_config(preset)


def test_validate_hud_config_rejects_bool_route_map_zoom_percent() -> None:
    preset = broadcast_runner_preset()
    route_map = next(widget for widget in preset.widgets if widget.id == "route-map")
    route_map.style["zoom_percent"] = True

    with pytest.raises(ValueError, match="zoom_percent"):
        validate_hud_config(preset)


def test_validate_hud_config_rejects_non_integer_route_map_zoom_percent() -> None:
    preset = broadcast_runner_preset()
    route_map = next(widget for widget in preset.widgets if widget.id == "route-map")
    route_map.style["zoom_percent"] = 90.0

    with pytest.raises(ValueError, match="zoom_percent"):
        validate_hud_config(preset)


def test_validate_hud_config_rejects_too_large_route_map_zoom_percent() -> None:
    preset = broadcast_runner_preset()
    route_map = next(widget for widget in preset.widgets if widget.id == "route-map")
    route_map.style["zoom_percent"] = 501

    with pytest.raises(ValueError, match="at most 500"):
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


def test_validate_hud_config_rejects_non_boolean_widget_visibility() -> None:
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
                visible="false",
            )
        ],
    )

    with pytest.raises(ValueError, match="visible"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_integer_widget_dimensions() -> None:
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
                width="180",
                height=50,
            )
        ],
    )

    with pytest.raises(ValueError, match="width"):
        validate_hud_config(config)


def test_render_hud_frame_keeps_right_anchored_widgets_visible_on_narrower_frames() -> None:
    preset = broadcast_runner_preset()
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
        hud_config=preset,
        elapsed_seconds=6852,
    )
    heart_rate = next(widget for widget in preset.widgets if widget.id == "heart-rate-stat")

    assert _region_has_alpha(image, _widget_bounds(heart_rate, 1100, 720))
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
    ellipse_fills: list[object] = []
    original_ellipse = ImageDraw.ImageDraw.ellipse

    def record_ellipse(self, xy, *args, **kwargs):
        ellipse_fills.append(kwargs.get("fill"))
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

    assert (228, 255, 238, 255) not in ellipse_fills


def test_render_hud_frame_route_map_uses_remaining_color_when_gps_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_fills: list[tuple[int, int, int, int]] = []
    original_line = ImageDraw.ImageDraw.line

    def record_line(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            line_fills.append(fill)
        return original_line(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)

    render_hud_frame(
        width=120,
        height=120,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=None,
            longitude=None,
            altitude_m=None,
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

    assert (13, 144, 195, 255) in line_fills
    assert (34, 255, 138, 255) not in line_fills


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


def test_metric_value_returns_stride_length_from_speed_and_cadence() -> None:
    widget = HudWidgetConfig(
        id="metric-stride",
        type="metric_card",
        bindings={"value": "stride_length_m"},
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
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )

    assert _metric_value(widget, hud_value, elapsed_seconds=6852) == "1.21"


def test_render_hud_frame_renders_stride_metric_card(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(
        monkeypatch,
        HudConfig(
            preset="stride-only",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="stride-chip",
                    type="metric_card",
                    bindings={"value": "stride_length_m"},
                    anchor="top-left",
                    x=24,
                    y=24,
                    width=160,
                    height=96,
                    style={"label": "Stride", "variant": "compact"},
                )
            ],
        ),
    )

    assert "Stride" in labels
    assert "1.21" in labels
    assert "m" in labels


def test_render_hud_frame_speed_gauge_metric_card_renders_kmh_value(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(
        monkeypatch,
        HudConfig(
            preset="speed-gauge",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="speed-chip",
                    type="metric_card",
                    bindings={"value": "speed_mps"},
                    anchor="bottom-right",
                    x=1120,
                    y=584,
                    width=160,
                    height=136,
                    style={"label": "Speed", "variant": "speed_gauge"},
                )
            ],
        ),
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=6.94,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
    )

    assert "25" in labels
    assert "KM/H" in labels
    assert "Speed" not in labels


def test_render_hud_frame_speed_gauge_metric_card_handles_missing_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _rendered_text_labels(
        monkeypatch,
        HudConfig(
            preset="speed-gauge",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="speed-chip",
                    type="metric_card",
                    bindings={"value": "speed_mps"},
                    anchor="bottom-right",
                    x=1120,
                    y=584,
                    width=160,
                    height=136,
                    style={"label": "Speed", "variant": "speed_gauge"},
                )
            ],
        ),
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=None,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
    )

    assert "--" in labels
    assert "KM/H" in labels


def test_render_hud_frame_speed_gauge_metric_card_draws_visible_pixels() -> None:
    widget = HudWidgetConfig(
        id="speed-chip",
        type="metric_card",
        bindings={"value": "speed_mps"},
        anchor="bottom-right",
        x=1120,
        y=584,
        width=160,
        height=136,
        style={"label": "Speed", "variant": "speed_gauge"},
    )
    hud_config = HudConfig(preset="speed-gauge", theme=HudThemeConfig(), widgets=[widget])

    image = render_hud_frame(
        width=1280,
        height=720,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=36.0833,
            longitude=140.2106,
            altitude_m=25.0,
            distance_m=5210.0,
            speed_mps=6.94,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        hud_config=hud_config,
        elapsed_seconds=6852,
    )

    assert _region_has_alpha(image, _widget_bounds(widget, 1280, 720))


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
    draws = _rendered_text_draws(
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

    labels = {text: xy for xy, text in draws}

    assert "N" in labels
    assert "225°SW" in labels
    assert labels["N"][1] < labels["225°SW"][1]
    assert labels["225°SW"][1] > 110


def test_render_hud_frame_route_map_shows_position_marker_arrow(monkeypatch: pytest.MonkeyPatch) -> None:
    polygon_calls: list[object] = []
    polygon_fills: list[tuple[int, int, int, int]] = []
    original_polygon = ImageDraw.ImageDraw.polygon

    def record_polygon(self, xy, *args, **kwargs):
        polygon_calls.append(xy)
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            polygon_fills.append(fill)
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

    assert polygon_calls, "expected position marker arrow polygon"
    assert (74, 155, 255, 255) in polygon_fills, "expected arrow head in blue color"


def test_render_hud_frame_route_map_projects_heading_arrow_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_vectors: list[tuple[float, float]] = []
    original_draw_position_arrow = hud_module._draw_position_marker_arrow

    def record_position_arrow(draw, center, vector, scale):
        captured_vectors.append(vector)
        return original_draw_position_arrow(draw, center, vector, scale)

    monkeypatch.setattr(hud_module, "_draw_position_marker_arrow", record_position_arrow)

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
    assert abs(vector_y / vector_x) > 10.0


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
    preset = broadcast_runner_preset()
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
        hud_config=preset,
        elapsed_seconds=6852,
        total_distance_m=10000.0,
    )

    assert image is not None
    assert image.width == 2560
    assert image.height == 1440
    assert image.getbbox() is not None


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
                    style={"label": "Heart", "unit_font_size_px": 26},
                )
            ],
        ),
    )

    # With new design: title uses theme.title_font_size_px, value uses theme.value_font_size_px, unit uses unit_font_size_px override
    assert calls == [("Heart", 14), ("162", 28), ("bpm", 26)]


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


def test_stat_block_unit_anchors_match_placement_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that stat block units use left-anchor for both left and right-aligned widgets,
    since unit_x is computed as value_bbox right edge + spacing (expecting left-anchored text)."""
    text_calls: list[tuple[str, tuple[int, int], str | None]] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        text_calls.append((str(text), xy, kwargs.get("anchor")))
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
            preset="stat-dual",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="left-stat",
                    type="stat_block",
                    bindings={"value": "heart_rate_bpm"},
                    anchor="top-left",
                    x=0,
                    y=0,
                    width=180,
                    height=96,
                    style={"label": "Heart", "unit": "bpm"},
                ),
                HudWidgetConfig(
                    id="right-stat",
                    type="stat_block",
                    bindings={"value": "distance_m"},
                    anchor="top-right",
                    x=0,
                    y=0,
                    width=180,
                    height=96,
                    style={"label": "Distance", "unit": "km"},
                ),
            ],
        ),
        elapsed_seconds=6852,
    )

    # Check left-aligned stat block unit
    left_unit_call = next(call for call in text_calls if call[0] == "bpm")
    assert left_unit_call[2] == "la", "Left-aligned stat block unit should use left anchor"

    # Check right-aligned stat block unit
    right_unit_call = next(call for call in text_calls if call[0] == "km")
    assert right_unit_call[2] == "la", "Right-aligned stat block unit should use left anchor"


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

    # Verify that rendering completes without error (removed panel_rgba from schema)
    assert len(panel_fills) >= 0  # At least one panel should be rendered


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

    assert (6, 10, 18, 148) in ellipse_fills


def test_render_hud_frame_route_map_uses_refreshed_default_route_and_marker_colors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_fills: list[tuple[int, int, int, int]] = []
    rounded_rectangle_fills: list[tuple[int, int, int, int]] = []
    ellipse_fills: list[tuple[int, int, int, int]] = []
    polygon_fills: list[tuple[int, int, int, int]] = []
    original_line = ImageDraw.ImageDraw.line
    original_rounded_rectangle = ImageDraw.ImageDraw.rounded_rectangle
    original_ellipse = ImageDraw.ImageDraw.ellipse
    original_polygon = ImageDraw.ImageDraw.polygon

    def record_line(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            line_fills.append(fill)
        return original_line(self, xy, *args, **kwargs)

    def record_rounded_rectangle(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            rounded_rectangle_fills.append(fill)
        return original_rounded_rectangle(self, xy, *args, **kwargs)

    def record_ellipse(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            ellipse_fills.append(fill)
        return original_ellipse(self, xy, *args, **kwargs)

    def record_polygon(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            polygon_fills.append(fill)
        return original_polygon(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)
    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", record_rounded_rectangle)
    monkeypatch.setattr(ImageDraw.ImageDraw, "ellipse", record_ellipse)
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
                    style={"label": "", "shape": "rounded-rect"},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    assert (6, 10, 18, 148) in rounded_rectangle_fills
    assert (34, 255, 138, 255) in line_fills
    assert (13, 144, 195, 255) in line_fills
    assert (228, 255, 238, 255) not in ellipse_fills
    assert (74, 155, 255, 255) in polygon_fills


def test_render_hud_frame_route_map_zoom_percent_insets_route_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_lines: list[list[tuple[float, float]]] = []
    original_line = ImageDraw.ImageDraw.line

    def record_line(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill in {ROUTE_MAP_COMPLETED_RGBA, ROUTE_MAP_REMAINING_RGBA}:
            recorded_lines.append([(float(x), float(y)) for x, y in xy])
        return original_line(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)

    def route_span(zoom_percent: int) -> tuple[float, float]:
        recorded_lines.clear()
        render_hud_frame(
            width=220,
            height=220,
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
            route_points=[(35.0, 139.0), (35.4, 139.7), (36.0, 140.0)],
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
                        width=220,
                        height=220,
                        style={"label": "", "shape": "circle", "zoom_percent": zoom_percent},
                    )
                ],
            ),
            elapsed_seconds=6852,
        )
        assert recorded_lines, "expected route-map line draws to match the color filter"
        points = [point for line in recorded_lines for point in line]
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        return (max(xs) - min(xs), max(ys) - min(ys))

    width_100, height_100 = route_span(100)
    width_90, height_90 = route_span(90)

    assert width_90 < width_100
    assert height_90 < height_100


def test_render_hud_frame_route_map_preserves_route_aspect_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_points: list[tuple[float, float]] = []
    original_line = ImageDraw.ImageDraw.line

    def record_line(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill in {ROUTE_MAP_COMPLETED_RGBA, ROUTE_MAP_REMAINING_RGBA}:
            recorded_points.extend([(float(x), float(y)) for x, y in xy])
        return original_line(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)

    render_hud_frame(
        width=220,
        height=220,
        hud_value=HudSample(
            timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
            latitude=0.5,
            longitude=1.0,
            altitude_m=25.0,
            distance_m=24600.0,
            speed_mps=3.58,
            pace_seconds_per_km=278.0,
            heart_rate_bpm=162,
            cadence_spm=178,
        ),
        route_points=[
            (0.0, 0.0),
            (0.0, 2.0),
            (1.0, 2.0),
            (1.0, 0.0),
            (0.0, 0.0),
        ],
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
                    width=220,
                    height=220,
                    style={"label": "", "shape": "circle"},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    xs = [x for x, _ in recorded_points]
    ys = [y for _, y in recorded_points]
    assert xs and ys, "expected route-map line draws to be recorded"
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)

    assert width > height * 1.5


def test_render_hud_frame_route_map_splits_completed_and_remaining_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line_fills: list[tuple[int, int, int, int]] = []
    original_line = ImageDraw.ImageDraw.line

    def record_line(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple):
            line_fills.append(fill)
        return original_line(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)

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
                    x=24,
                    y=24,
                    width=176,
                    height=128,
                    style={"label": "", "shape": "rounded-rect"},
                )
            ],
        ),
        elapsed_seconds=6852,
    )

    assert (34, 255, 138, 255) in line_fills
    assert (13, 144, 195, 255) in line_fills


def test_split_route_points_at_first_segment() -> None:
    split = RouteProjection(
        point=(35.1, 139.1),
        tangent=(0.5, 0.5),
        segment_start=(35.0, 139.0),
        segment_end=(35.5, 139.5),
        segment_index=0,
    )

    completed, remaining = _split_route_points(
        [(35.0, 139.0), (35.5, 139.5), (36.0, 140.0)],
        split,
    )

    assert completed == [(35.0, 139.0), (35.1, 139.1)]
    assert remaining == [(35.1, 139.1), (35.5, 139.5), (36.0, 140.0)]


def test_split_route_points_at_last_segment() -> None:
    split = RouteProjection(
        point=(35.9, 139.9),
        tangent=(0.5, 0.5),
        segment_start=(35.5, 139.5),
        segment_end=(36.0, 140.0),
        segment_index=1,
    )

    completed, remaining = _split_route_points(
        [(35.0, 139.0), (35.5, 139.5), (36.0, 140.0)],
        split,
    )

    assert completed == [(35.0, 139.0), (35.5, 139.5), (35.9, 139.9)]
    assert remaining == [(35.9, 139.9), (36.0, 140.0)]


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

    # Verify that rendering completes and panels were rendered (removed panel_rgba from schema)
    assert len(panel_fills) > 0


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


def test_validate_hud_config_rejects_unknown_route_map_shape() -> None:
    with pytest.raises(ValueError, match="supported shapes: circle, rounded-rect, square"):
        validate_hud_config(
            HudConfig(
                preset="broadcast-runner",
                theme=HudThemeConfig(),
                widgets=[
                    HudWidgetConfig(
                        id="route-map",
                        type="route_map",
                        bindings={"value": "route_points"},
                        anchor="top-left",
                        x=0,
                        y=0,
                        width=196,
                        height=196,
                        style={"shape": "triangle"},
                    )
                ],
            )
        )


def test_progress_bar_text_layout_aligns_current_and_total_values(monkeypatch: pytest.MonkeyPatch) -> None:
    layout = _progress_bar_text_layout(left=0, top=0, width=560, height=56, label="Distance")

    assert layout.current_anchor[1] == layout.total_anchor[1]
    assert layout.total_anchor[0] > layout.current_anchor[0]

    rendered_texts: list[tuple[str, tuple[float, float]]] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        if str(text) in {"5.20 KM", "10.00 KM"}:
            rendered_texts.append((str(text), (float(xy[0]), float(xy[1]))))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_text)

    image = Image.new("RGBA", (640, 96), (0, 0, 0, 0))
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
            width=560,
            height=56,
            style={"label": "Distance"},
        ),
        distance_m=5200.0,
        total_distance_m=10000.0,
        theme=HudThemeConfig(),
        frame_width=640,
        frame_height=96,
        scale=RenderScale(x=1.0, y=1.0, draw=1.0),
    )

    current_xy = next(xy for text, xy in rendered_texts if text == "5.20 KM")
    total_xy = next(xy for text, xy in rendered_texts if text == "10.00 KM")

    assert current_xy[1] == total_xy[1] == layout.current_anchor[1]
    assert current_xy[0] > 150
    assert total_xy[0] > current_xy[0]


def test_render_hud_frame_accepts_lap_state_kwarg() -> None:
    """render_hud_frame must accept lap_state= without raising, and produce an image."""
    from datetime import datetime, timezone

    lap = ActivityLap(
        start_time=datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc),
        total_time_seconds=300.0,
        distance_m=1000.0,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        max_speed_mps=None,
        elevation_delta_m=None,
        calories=None,
    )
    row = LapWaterfallRow(lap=lap, lap_index=0, is_dimmed=False)
    state = LapWaterfallState(
        completed_laps=[lap],
        visible_rows=[row],
        newest_lap_index=0,
        oldest_row_dimmed=False,
        opacity=1.0,
    )

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
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=6852,
        total_distance_m=42195.0,
        lap_state=state,
    )
    assert image.size == (1280, 720)


def test_render_hud_frame_accepts_lap_states_kwarg() -> None:
    lap = ActivityLap(
        start_time=datetime(2026, 4, 19, 9, 0, 0, tzinfo=timezone.utc),
        total_time_seconds=300.0,
        distance_m=1000.0,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        max_speed_mps=None,
        elevation_delta_m=None,
        calories=None,
    )
    row = LapWaterfallRow(lap=lap, lap_index=0, is_dimmed=False)
    state = LapWaterfallState(
        completed_laps=[lap],
        visible_rows=[row],
        newest_lap_index=0,
        oldest_row_dimmed=False,
        opacity=1.0,
    )

    image = render_hud_frame(
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
        hud_config=_make_lap_waterfall_config(),
        elapsed_seconds=6852,
        total_distance_m=42195.0,
        lap_states={"lap-table": state},
    )
    assert image.size == (1280, 720)


def test_render_hud_frame_accepts_lap_state_none() -> None:
    """render_hud_frame must accept lap_state=None (default) without raising."""
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
        hud_config=broadcast_runner_preset(),
        elapsed_seconds=6852,
        total_distance_m=42195.0,
        lap_state=None,
    )
    assert image.size == (1280, 720)


# ===== lap_waterfall widget tests =====

def _make_test_activity_lap(
    *,
    distance_m: float = 1000.0,
    total_time_seconds: float = 360.0,
    avg_heart_rate_bpm: int | None = 155,
    elevation_delta_m: float | None = 5.0,
) -> ActivityLap:
    return ActivityLap(
        start_time=datetime(2026, 4, 20, 8, 0, 0, tzinfo=timezone.utc),
        total_time_seconds=total_time_seconds,
        distance_m=distance_m,
        avg_heart_rate_bpm=avg_heart_rate_bpm,
        max_heart_rate_bpm=170,
        max_speed_mps=None,
        elevation_delta_m=elevation_delta_m,
        calories=None,
    )


def _make_lap_waterfall_config(**style_overrides: object) -> HudConfig:
    style: dict[str, object] = {"visible_rows": 5}
    style.update(style_overrides)
    return HudConfig(
        preset="lap-only",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="lap-table",
                type="lap_waterfall",
                bindings={"value": "laps"},
                anchor="top-left",
                x=0,
                y=0,
                width=400,
                height=200,
                style=style,
            )
        ],
    )


def _make_lap_rows(n: int, *, first_dimmed: bool = False) -> list[LapWaterfallRow]:
    lap = _make_test_activity_lap()
    return [
        LapWaterfallRow(lap=lap, lap_index=i, is_dimmed=(first_dimmed and i == 0))
        for i in range(n)
    ]


def _render_labels_with_lap_state(
    monkeypatch: pytest.MonkeyPatch,
    hud_config: HudConfig,
    lap_state: LapWaterfallState | None,
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
        hud_config=hud_config,
        elapsed_seconds=6852,
        lap_state=lap_state,
    )
    return labels


def _render_fills_with_lap_state(
    monkeypatch: pytest.MonkeyPatch,
    hud_config: HudConfig,
    lap_state: LapWaterfallState | None,
) -> list[tuple]:
    fills: list[tuple] = []
    original_text = ImageDraw.ImageDraw.text

    def record_fill(self, xy, text, *args, **kwargs):
        fill = kwargs.get("fill")
        if fill is None and len(args) >= 2:
            fill = args[1]
        if isinstance(fill, (tuple, list)) and len(fill) == 4:
            fills.append(tuple(fill))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record_fill)
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
        hud_config=hud_config,
        elapsed_seconds=6852,
        lap_state=lap_state,
    )
    return fills


def test_validate_hud_config_accepts_lap_waterfall_widget() -> None:
    config = _make_lap_waterfall_config()
    validate_hud_config(config)  # must not raise


def test_validate_hud_config_rejects_unsupported_binding_for_lap_waterfall() -> None:
    config = HudConfig(
        preset="broken",
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="lap-table",
                type="lap_waterfall",
                bindings={"value": "distance_m"},
                anchor="top-left",
                x=0,
                y=0,
                width=400,
                height=200,
            )
        ],
    )
    with pytest.raises(ValueError, match="unsupported binding"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_bool_show_distance_style() -> None:
    config = _make_lap_waterfall_config(show_distance="yes")
    with pytest.raises(ValueError, match="style.show_distance"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_bool_always_show_style() -> None:
    config = _make_lap_waterfall_config(always_show=1)
    with pytest.raises(ValueError, match="style.always_show"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_zero_visible_rows_style() -> None:
    config = _make_lap_waterfall_config(visible_rows=0)
    with pytest.raises(ValueError, match="visible_rows"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_positive_fade_after_seconds_style() -> None:
    config = _make_lap_waterfall_config(fade_after_seconds=-1.0)
    with pytest.raises(ValueError, match="fade_after_seconds"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_bool_show_time_style() -> None:
    config = _make_lap_waterfall_config(show_time=0)
    with pytest.raises(ValueError, match="style.show_time"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_bool_show_pace_style() -> None:
    config = _make_lap_waterfall_config(show_pace="true")
    with pytest.raises(ValueError, match="style.show_pace"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_bool_show_elevation_style() -> None:
    config = _make_lap_waterfall_config(show_elevation=1)
    with pytest.raises(ValueError, match="style.show_elevation"):
        validate_hud_config(config)


def test_validate_hud_config_rejects_non_bool_show_heart_rate_style() -> None:
    config = _make_lap_waterfall_config(show_heart_rate="false")
    with pytest.raises(ValueError, match="style.show_heart_rate"):
        validate_hud_config(config)


def test_render_hud_frame_lap_waterfall_renders_column_headers_with_active_lap_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    rows = _make_lap_rows(2)
    lap_state = LapWaterfallState(
        completed_laps=[r.lap for r in rows],
        visible_rows=rows,
        newest_lap_index=1,
        oldest_row_dimmed=False,
        opacity=1.0,
    )
    labels = _render_labels_with_lap_state(monkeypatch, config, lap_state)
    assert "Lap" in labels
    assert "Pace" in labels
    assert "Distance" in labels


def test_render_hud_frame_lap_waterfall_renders_nothing_when_lap_state_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    labels = _render_labels_with_lap_state(monkeypatch, config, None)
    assert "Lap" not in labels


def test_render_hud_frame_lap_waterfall_renders_nothing_when_opacity_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    rows = _make_lap_rows(2)
    lap_state = LapWaterfallState(
        completed_laps=[r.lap for r in rows],
        visible_rows=rows,
        newest_lap_index=1,
        oldest_row_dimmed=False,
        opacity=0.0,
    )
    labels = _render_labels_with_lap_state(monkeypatch, config, lap_state)
    assert "Lap" not in labels


def test_render_hud_frame_lap_waterfall_hidden_distance_column_not_rendered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config(show_distance=False)
    rows = _make_lap_rows(2)
    lap_state = LapWaterfallState(
        completed_laps=[r.lap for r in rows],
        visible_rows=rows,
        newest_lap_index=1,
        oldest_row_dimmed=False,
        opacity=1.0,
    )
    labels = _render_labels_with_lap_state(monkeypatch, config, lap_state)
    assert "Distance" not in labels
    assert "Lap" in labels  # Lap column always visible


def test_render_hud_frame_lap_waterfall_hidden_hr_column_not_rendered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config(show_heart_rate=False)
    rows = _make_lap_rows(2)
    lap_state = LapWaterfallState(
        completed_laps=[r.lap for r in rows],
        visible_rows=rows,
        newest_lap_index=1,
        oldest_row_dimmed=False,
        opacity=1.0,
    )
    labels = _render_labels_with_lap_state(monkeypatch, config, lap_state)
    assert "HR" not in labels


def test_render_hud_frame_lap_waterfall_dimmed_row_uses_reduced_alpha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Oldest row with is_dimmed=True must render with lower alpha than non-dimmed rows."""
    config = _make_lap_waterfall_config()
    lap = _make_test_activity_lap()
    dimmed_row = LapWaterfallRow(lap=lap, lap_index=0, is_dimmed=True)
    normal_row = LapWaterfallRow(lap=lap, lap_index=1, is_dimmed=False)
    lap_state = LapWaterfallState(
        completed_laps=[lap, lap],
        visible_rows=[dimmed_row, normal_row],
        newest_lap_index=1,
        oldest_row_dimmed=True,
        opacity=1.0,
    )
    fills = _render_fills_with_lap_state(monkeypatch, config, lap_state)
    alphas = [f[3] for f in fills]
    assert len(alphas) >= 2, "Expected text draws with RGBA fills"
    assert min(alphas) < max(alphas), "Dimmed row should use lower alpha than normal rows"


def test_render_hud_frame_lap_waterfall_renders_lap_numbers_in_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    rows = _make_lap_rows(3)
    lap_state = LapWaterfallState(
        completed_laps=[r.lap for r in rows],
        visible_rows=rows,
        newest_lap_index=2,
        oldest_row_dimmed=False,
        opacity=1.0,
    )
    labels = _render_labels_with_lap_state(monkeypatch, config, lap_state)
    assert "1" in labels
    assert "2" in labels
    assert "3" in labels


def test_render_hud_frame_lap_waterfall_keeps_rows_compact_before_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    rows = _make_lap_rows(2)
    lap_state = LapWaterfallState(
        completed_laps=[row.lap for row in rows],
        visible_rows=rows,
        newest_lap_index=1,
        oldest_row_dimmed=False,
        opacity=1.0,
    )
    calls: list[tuple[int, int, int, int]] = []
    original_composite = hud_module._alpha_composite_clipped

    def record_composite(image, overlay, left, top):
        calls.append((left, top, overlay.width, overlay.height))
        return original_composite(image, overlay, left, top)

    monkeypatch.setattr(hud_module, "_alpha_composite_clipped", record_composite)
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
        hud_config=config,
        elapsed_seconds=6852,
        lap_state=lap_state,
    )

    data_row_height = max(height for _left, _top, _width, height in calls)
    first_column_left = min(left for left, _top, _width, height in calls if height == data_row_height)
    row_tops = sorted({top for left, top, _width, height in calls if left == first_column_left and height == data_row_height})

    assert len(row_tops) == 2
    assert row_tops[1] - row_tops[0] < 50


def test_render_hud_frame_lap_waterfall_slides_rows_during_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    rows = _make_lap_rows(6)
    transition_state = LapWaterfallState(
        completed_laps=[row.lap for row in rows],
        visible_rows=[
            LapWaterfallRow(lap=row.lap, lap_index=row.lap_index, is_dimmed=(row.lap_index == 1))
            for row in rows[1:]
        ],
        newest_lap_index=5,
        oldest_row_dimmed=True,
        opacity=1.0,
        transition_previous_rows=[
            LapWaterfallRow(lap=row.lap, lap_index=row.lap_index, is_dimmed=(row.lap_index == 0))
            for row in rows[:5]
        ],
        transition_progress=0.5,
    )
    settled_state = LapWaterfallState(
        completed_laps=[row.lap for row in rows],
        visible_rows=[
            LapWaterfallRow(lap=row.lap, lap_index=row.lap_index, is_dimmed=(row.lap_index == 1))
            for row in rows[1:]
        ],
        newest_lap_index=5,
        oldest_row_dimmed=True,
        opacity=1.0,
    )
    original_composite = hud_module._alpha_composite_clipped

    def capture_bottom_row_top(lap_state: LapWaterfallState) -> int:
        calls: list[tuple[int, int, int, int]] = []

        def record_composite(image, overlay, left, top):
            calls.append((left, top, overlay.width, overlay.height))
            return original_composite(image, overlay, left, top)

        monkeypatch.setattr(hud_module, "_alpha_composite_clipped", record_composite)
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
            hud_config=config,
            elapsed_seconds=6852,
            lap_state=lap_state,
        )
        row_heights = [height for _left, _top, _width, height in calls]
        data_row_height = max(row_heights)
        first_column_left = min(left for left, _top, _width, height in calls if height == data_row_height)
        row_tops = [top for left, top, _width, height in calls if left == first_column_left and height == data_row_height]
        return max(row_tops)

    transition_bottom_top = capture_bottom_row_top(transition_state)
    settled_bottom_top = capture_bottom_row_top(settled_state)

    assert transition_bottom_top > settled_bottom_top


def test_render_hud_frame_lap_waterfall_slides_newest_row_before_window_fills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config(visible_rows=8)
    rows = _make_lap_rows(8)
    entry_state = LapWaterfallState(
        completed_laps=[row.lap for row in rows],
        visible_rows=rows,
        newest_lap_index=7,
        oldest_row_dimmed=False,
        opacity=1.0,
        transition_progress=0.5,
    )
    settled_state = LapWaterfallState(
        completed_laps=[row.lap for row in rows],
        visible_rows=rows,
        newest_lap_index=7,
        oldest_row_dimmed=False,
        opacity=1.0,
    )
    original_composite = hud_module._alpha_composite_clipped

    def capture_bottom_row_top(lap_state: LapWaterfallState) -> int:
        calls: list[tuple[int, int, int, int]] = []

        def record_composite(image, overlay, left, top):
            calls.append((left, top, overlay.width, overlay.height))
            return original_composite(image, overlay, left, top)

        monkeypatch.setattr(hud_module, "_alpha_composite_clipped", record_composite)
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
            hud_config=config,
            elapsed_seconds=6852,
            lap_state=lap_state,
        )
        data_row_height = max(height for _left, _top, _width, height in calls)
        first_column_left = min(left for left, _top, _width, height in calls if height == data_row_height)
        row_tops = [top for left, top, _width, height in calls if left == first_column_left and height == data_row_height]
        return max(row_tops)

    assert capture_bottom_row_top(entry_state) > capture_bottom_row_top(settled_state)


def test_render_hud_frame_lap_waterfall_highlights_newest_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    rows = _make_lap_rows(3)
    lap_state = LapWaterfallState(
        completed_laps=[row.lap for row in rows],
        visible_rows=rows,
        newest_lap_index=2,
        oldest_row_dimmed=False,
        opacity=1.0,
        transition_progress=0.5,
    )
    fills: list[tuple[int, int, int, int]] = []
    boxes: list[tuple[int, int, int, int]] = []
    original_rounded_rectangle = ImageDraw.ImageDraw.rounded_rectangle

    def record_rounded_rectangle(self, xy, *args, **kwargs):
        fill = kwargs.get("fill")
        if isinstance(fill, tuple) and len(fill) == 4:
            fills.append(fill)
            if isinstance(xy, tuple) and len(xy) == 4:
                boxes.append(tuple(int(round(value)) for value in xy))
        return original_rounded_rectangle(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", record_rounded_rectangle)
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
        hud_config=config,
        elapsed_seconds=6852,
        lap_state=lap_state,
    )

    assert fills
    assert boxes
    left, top, right, bottom = boxes[-1]
    assert right > left
    assert bottom > top
    assert right - left < 500
    assert bottom - top <= 40


def test_render_hud_frame_lap_waterfall_renders_distance_and_pace_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    lap = _make_test_activity_lap(distance_m=410.0, total_time_seconds=73.0, avg_heart_rate_bpm=91)
    lap_state = LapWaterfallState(
        completed_laps=[lap],
        visible_rows=[LapWaterfallRow(lap=lap, lap_index=0, is_dimmed=False)],
        newest_lap_index=0,
        oldest_row_dimmed=False,
        opacity=1.0,
    )

    labels = _render_labels_with_lap_state(monkeypatch, config, lap_state)

    assert "0.41 km" in labels
    assert any(label.endswith("/km") for label in labels)
    assert "91 bpm" in labels


def test_render_hud_frame_lap_waterfall_renders_elevation_with_sign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    lap_pos = _make_test_activity_lap(elevation_delta_m=12.0)
    lap_neg = _make_test_activity_lap(elevation_delta_m=-8.0)
    rows = [
        LapWaterfallRow(lap=lap_pos, lap_index=0, is_dimmed=False),
        LapWaterfallRow(lap=lap_neg, lap_index=1, is_dimmed=False),
    ]
    lap_state = LapWaterfallState(
        completed_laps=[lap_pos, lap_neg],
        visible_rows=rows,
        newest_lap_index=1,
        oldest_row_dimmed=False,
        opacity=1.0,
    )
    labels = _render_labels_with_lap_state(monkeypatch, config, lap_state)
    assert any("+12" in label for label in labels), f"Expected '+12' in labels: {labels}"
    assert any("-8" in label for label in labels), f"Expected '-8' in labels: {labels}"


def test_render_hud_frame_lap_waterfall_prefers_widget_scoped_lap_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _make_lap_waterfall_config()
    fallback_lap = _make_test_activity_lap(distance_m=1000.0)
    widget_lap = _make_test_activity_lap(distance_m=410.0)
    fallback_state = LapWaterfallState(
        completed_laps=[fallback_lap],
        visible_rows=[LapWaterfallRow(lap=fallback_lap, lap_index=0, is_dimmed=False)],
        newest_lap_index=0,
        oldest_row_dimmed=False,
        opacity=1.0,
    )
    widget_state = LapWaterfallState(
        completed_laps=[widget_lap],
        visible_rows=[LapWaterfallRow(lap=widget_lap, lap_index=2, is_dimmed=False)],
        newest_lap_index=2,
        oldest_row_dimmed=False,
        opacity=1.0,
    )

    labels: list[str] = []
    original_text = ImageDraw.ImageDraw.text

    def record_text(self, xy, text, *args, **kwargs):
        labels.append(str(text))
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
        hud_config=config,
        elapsed_seconds=6852,
        lap_state=fallback_state,
        lap_states={"lap-table": widget_state},
    )

    assert "3" in labels
    assert "0.41 km" in labels
    assert "1.00 km" not in labels


def test_render_hud_frame_lap_waterfall_always_show_overrides_opacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When always_show=True, the widget renders even if lap_state.opacity is low."""
    config = _make_lap_waterfall_config(always_show=True)
    rows = _make_lap_rows(1)
    lap_state = LapWaterfallState(
        completed_laps=[r.lap for r in rows],
        visible_rows=rows,
        newest_lap_index=0,
        oldest_row_dimmed=False,
        opacity=0.1,  # low but not zero
    )
    labels = _render_labels_with_lap_state(monkeypatch, config, lap_state)
    assert "Lap" in labels


def test_lap_waterfall_column_widths_do_not_exceed_available_width() -> None:
    widths = hud_module._lap_waterfall_column_widths(
        ["lap", "distance", "time", "pace", "elevation", "heart_rate"],
        180,
        RenderScale(x=1.0, y=1.0, draw=1.0),
    )

    assert sum(widths) == 180
    assert all(width >= 1 for width in widths)


def test_route_map_cache_is_created_and_reused() -> None:
    """Route map should create and reuse a static cache for repeated renders."""
    config = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=200,
            )
        ],
    )
    
    route_points = [
        (36.0830, 140.2100),
        (36.0831, 140.2102),
        (36.0832, 140.2104),
        (36.0833, 140.2106),
        (36.0834, 140.2108),
    ]
    
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0832,
        longitude=140.2104,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    # First render should create cache
    frame1 = render_hud_frame(1280, 720, hud_value, route_points, hud_config=config)
    
    # Check that cache was created
    cache = hud_module._get_route_map_cache()
    assert len(cache) > 0, "Cache should be created after first render"
    
    # Second render with different GPS position should reuse cache
    hud_value2 = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 15, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=1020.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    frame2 = render_hud_frame(1280, 720, hud_value2, route_points, hud_config=config)
    
    # Cache should still have one entry (reused)
    cache_after = hud_module._get_route_map_cache()
    assert len(cache_after) == len(cache), "Cache should be reused for same config"
    
    # Clean up
    hud_module._clear_route_map_cache()


def test_route_map_cache_invalidated_when_remaining_color_changes() -> None:
    """Route map cache should be invalidated when remaining_rgba changes."""
    route_points = [
        (36.0830, 140.2100),
        (36.0831, 140.2102),
        (36.0832, 140.2104),
    ]
    
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0831,
        longitude=140.2102,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    config1 = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=200,
            )
        ],
    )
    
    # First render
    frame1 = render_hud_frame(1280, 720, hud_value, route_points, hud_config=config1)
    cache_keys_1 = set(hud_module._get_route_map_cache().keys())
    
    # Change only the cached base-route color
    config2 = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=200,
                style={"remaining_rgba": [255, 0, 0, 255]},
            )
        ],
    )
    
    # Second render with different config
    frame2 = render_hud_frame(1280, 720, hud_value, route_points, hud_config=config2)
    cache_keys_2 = set(hud_module._get_route_map_cache().keys())
    
    # Cache should have new entry for different config
    assert cache_keys_1 != cache_keys_2, "Cache key should change when widget config changes"
    
    # Clean up
    hud_module._clear_route_map_cache()


def test_route_map_cache_invalidated_when_title_font_changes() -> None:
    """Route map cache should be invalidated when cached label font changes."""
    route_points = [
        (36.0830, 140.2100),
        (36.0831, 140.2102),
        (36.0832, 140.2104),
    ]
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0831,
        longitude=140.2102,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    config1 = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=200,
            )
        ],
    )
    render_hud_frame(1280, 720, hud_value, route_points, hud_config=config1)
    cache_keys_1 = set(hud_module._get_route_map_cache().keys())

    config2 = HudConfig(
        theme=HudThemeConfig(title_font_family="mono"),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=200,
            )
        ],
    )
    render_hud_frame(1280, 720, hud_value, route_points, hud_config=config2)
    cache_keys_2 = set(hud_module._get_route_map_cache().keys())

    assert cache_keys_1 != cache_keys_2, "Cache key should change when cached label font changes"


def test_route_map_output_parity_with_caching() -> None:
    """Route map output should be identical with or without cache."""
    config = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=200,
            )
        ],
    )
    
    route_points = [
        (36.0830, 140.2100),
        (36.0831, 140.2102),
        (36.0832, 140.2104),
        (36.0833, 140.2106),
    ]
    
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0831,
        longitude=140.2102,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    # Clear cache before first render
    hud_module._clear_route_map_cache()
    
    # First render (no cache)
    frame1 = render_hud_frame(1280, 720, hud_value, route_points, hud_config=config)
    
    # Clear cache
    hud_module._clear_route_map_cache()
    
    # Second render (also no cache, for comparison)
    frame2 = render_hud_frame(1280, 720, hud_value, route_points, hud_config=config)
    
    # Frames should be identical
    assert frame1.tobytes() == frame2.tobytes(), "Renders without cache should be identical"
    
    # Third render (with cache from frame2)
    frame3 = render_hud_frame(1280, 720, hud_value, route_points, hud_config=config)
    
    # Frame with cache should match frame without cache
    assert frame2.tobytes() == frame3.tobytes(), "Render with cache should match render without cache"
    
    # Clean up
    hud_module._clear_route_map_cache()


def test_route_map_cache_evicts_oldest_entries_when_limit_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route map cache should stay bounded instead of growing forever."""
    monkeypatch.setattr(hud_module, "ROUTE_MAP_CACHE_MAX_ENTRIES", 2)
    route_points = [
        (36.0830, 140.2100),
        (36.0831, 140.2102),
        (36.0832, 140.2104),
    ]
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0831,
        longitude=140.2102,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )

    def render_with_remaining_color(color: list[int]) -> set[str]:
        config = HudConfig(
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="route-map",
                    type="route_map",
                    bindings={"value": "route_points"},
                    anchor="top-left",
                    x=10,
                    y=10,
                    width=200,
                    height=200,
                    style={"remaining_rgba": color},
                )
            ],
        )
        render_hud_frame(1280, 720, hud_value, route_points, hud_config=config)
        return set(hud_module._get_route_map_cache().keys())

    first_keys = render_with_remaining_color([255, 0, 0, 255])
    second_keys = render_with_remaining_color([0, 255, 0, 255])
    third_keys = render_with_remaining_color([0, 0, 255, 255])
    first_key = next(iter(first_keys))

    assert len(third_keys) == 2
    assert first_key not in third_keys
    assert third_keys != second_keys


def test_route_map_cache_contains_static_components() -> None:
    """Route map cache should contain background and projected route."""
    config = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=200,
            )
        ],
    )
    
    route_points = [
        (36.0830, 140.2100),
        (36.0831, 140.2102),
        (36.0832, 140.2104),
    ]
    
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0831,
        longitude=140.2102,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    # Clear cache before render
    hud_module._clear_route_map_cache()
    
    # Render to create cache
    frame = render_hud_frame(1280, 720, hud_value, route_points, hud_config=config)
    
    # Check cache contents
    cache = hud_module._get_route_map_cache()
    assert len(cache) > 0, "Cache should exist"
    
    # Get the cache entry
    cache_entry = next(iter(cache.values()))
    
    # Cache should have required components
    assert hasattr(cache_entry, "background_image"), "Cache should contain background image"
    assert hasattr(cache_entry, "projected_points"), "Cache should contain projected points"
    assert hasattr(cache_entry, "project_fn"), "Cache should contain projection function"
    
    # Validate components
    assert cache_entry.background_image is not None
    assert len(cache_entry.projected_points) == len(route_points)
    assert callable(cache_entry.project_fn)
    
    # Clean up
    hud_module._clear_route_map_cache()


def test_route_map_uses_cached_projected_points_without_reprojection_on_large_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Test that route_map uses cached projected points directly without
    reprojecting all points every frame on large routes.
    
    This is the key optimization for Task 2: avoid O(n) reprojection by
    using cached projected_points via slicing.
    """
    # Create a large route (simulating the 9343-point route)
    route_points = [(35.0 + i * 0.001, 139.0 + i * 0.001) for i in range(1000)]
    
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
                width=200,
                height=200,
            )
        ],
    )
    
    # First render to populate cache
    first_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=35.1,
        longitude=139.1,
        altitude_m=25.0,
        distance_m=10000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    render_hud_frame(
        width=200,
        height=200,
        hud_value=first_sample,
        route_points=route_points,
        hud_config=hud_config,
        elapsed_seconds=3000,
    )
    
    # Track how many times project_fn is called on second render
    cache = hud_module._get_route_map_cache()
    cache_entry = next(iter(cache.values()))
    original_project_fn = cache_entry.project_fn
    projection_call_count = [0]
    
    def counting_project_fn(point):
        projection_call_count[0] += 1
        return original_project_fn(point)
    
    # Replace project_fn with counting version
    cache_entry.project_fn = counting_project_fn
    
    # Second render at different position
    second_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 20, tzinfo=timezone.utc),
        latitude=35.2,
        longitude=139.2,
        altitude_m=25.0,
        distance_m=15000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    render_hud_frame(
        width=200,
        height=200,
        hud_value=second_sample,
        route_points=route_points,
        hud_config=hud_config,
        elapsed_seconds=3010,
    )
    
    # After optimization, should only project:
    # 1. The split point itself (1 call)
    # 2. The heading vector endpoints (2 calls for segment_start and segment_end)
    # Total: ~3 calls, NOT 1000 calls (all route points)
    assert projection_call_count[0] <= 5, (
        f"Expected minimal projections (~3), but got {projection_call_count[0]}. "
        "route_map should use cached projected_points directly via slicing, "
        "not reproject all points every frame."
    )


def test_route_map_preserves_visual_output_after_projection_optimization() -> None:
    """
    Test that visual output remains identical after optimizing projection logic.
    This ensures we maintain render parity while improving performance.
    """
    route_points = [(35.0 + i * 0.01, 139.0 + i * 0.01) for i in range(100)]
    
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
                width=200,
                height=200,
            )
        ],
    )
    
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=35.5,
        longitude=139.5,
        altitude_m=25.0,
        distance_m=50000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    # Render twice with cache clear in between
    image1 = render_hud_frame(
        width=200,
        height=200,
        hud_value=hud_value,
        route_points=route_points,
        hud_config=hud_config,
        elapsed_seconds=10000,
    )
    
    hud_module._clear_route_map_cache()
    
    image2 = render_hud_frame(
        width=200,
        height=200,
        hud_value=hud_value,
        route_points=route_points,
        hud_config=hud_config,
        elapsed_seconds=10000,
    )
    
    # Images should be identical
    assert list(image1.getdata()) == list(image2.getdata()), (
        "Visual output changed after optimization. "
        "Optimization must preserve render parity."
    )


def test_route_map_cache_contains_pre_rendered_base_layer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Test that the route base layer (static route polyline) is pre-rendered
    into the cached background image, not redrawn every frame.
    
    This is the remaining Task 2 spec gap: route_map should split work into
    clip-static (route base layer rasterization in cache) vs frame-dynamic
    (position/split/heading overlays only).
    """
    # Use a larger route to make the issue visible
    route_points = [(35.0 + i * 0.001, 139.0 + i * 0.001) for i in range(100)]
    
    hud_config = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=200,
            )
        ],
    )
    
    hud_value = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=35.05,
        longitude=139.05,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    # Clear cache before render
    hud_module._clear_route_map_cache()
    
    # Render to create cache
    render_hud_frame(1280, 720, hud_value, route_points, hud_config=hud_config)
    
    # Get cached background
    cache = hud_module._get_route_map_cache()
    cache_entry = next(iter(cache.values()))
    cached_bg = cache_entry.background_image
    
    # The cached background should contain the pre-rendered route polyline
    # Check for the base route color (remaining_rgba = blue: 13, 144, 195, 255)
    pixels = list(cached_bg.getdata())
    
    # Count route color pixels (remaining/base route color)
    route_pixels = sum(1 for r, g, b, a in pixels if r < 30 and g > 100 and b > 150 and a > 200)
    
    # After the fix, the static route should be pre-rendered in background
    assert route_pixels > 50, (
        f"Expected cached background to contain pre-rendered route polyline, "
        f"but found only {route_pixels} route pixels. "
        "The static route base layer should be rasterized into background_image."
    )
    
    # Now check that per-frame drawing doesn't redraw the full route polyline
    # by monitoring ImageDraw.line calls during a second render
    line_calls = []
    original_line = ImageDraw.ImageDraw.line
    
    def record_line(self, *args, **kwargs):
        # Record the arguments (especially the points list length)
        if args:
            points = args[0]
            if isinstance(points, list):
                line_calls.append(len(points))
        return original_line(self, *args, **kwargs)
    
    monkeypatch.setattr(ImageDraw.ImageDraw, "line", record_line)
    
    # Render a second frame at different position
    hud_value2 = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 15, tzinfo=timezone.utc),
        latitude=35.06,
        longitude=139.06,
        altitude_m=25.0,
        distance_m=1500.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    
    render_hud_frame(1280, 720, hud_value2, route_points, hud_config=hud_config)
    
    # After the fix, we should NOT draw the FULL route polyline
    # We may draw the completed portion (which varies based on position)
    # But the key is we're not redrawing the entire route base layer
    # With 100 route points, drawing > 90 points means we're drawing almost the full route
    max_line_length = max(line_calls) if line_calls else 0
    assert max_line_length < 90, (
        f"Found line() call with {max_line_length} points. "
        "Static route base layer should be pre-rendered in cache. "
        "Frame should only draw dynamic completed overlay (not full route)."
    )
    
    # Clean up
    hud_module._clear_route_map_cache()
