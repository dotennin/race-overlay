from datetime import datetime, timezone
import os
from pathlib import Path
import time

from PIL import Image, ImageDraw
import pytest

import race_overlay.hud as hud_module
from race_overlay.hud import HudLayout, _draw_progress_bar, _metric_value, render_hud_frame
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig
from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.models import HudSample


def _rendered_text_labels(monkeypatch: pytest.MonkeyPatch, hud_config: HudConfig) -> list[str]:
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
    )
    return labels


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
    assert image.getpixel((80, 210))[3] > 0
    assert image.getpixel((1150, 170))[3] > 0


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

    assert image.getpixel((950, 170))[3] > 0
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
