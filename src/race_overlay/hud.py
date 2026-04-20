from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig, _require_unique_widget_ids
from race_overlay.models import HudSample

HUD_REFERENCE_WIDTH = 1280
HUD_REFERENCE_HEIGHT = 720
PROGRESS_BAR_MIN_WIDTH = 232
SUPPORTED_WIDGET_ANCHORS = {"top-left", "top-right", "bottom-left", "bottom-right"}


@dataclass(slots=True, frozen=True)
class RenderScale:
    x: float
    y: float
    draw: float


def _render_scale(frame_width: int, frame_height: int) -> RenderScale:
    x_scale = max(frame_width / HUD_REFERENCE_WIDTH, 1.0)
    y_scale = max(frame_height / HUD_REFERENCE_HEIGHT, 1.0)
    return RenderScale(x=x_scale, y=y_scale, draw=min(x_scale, y_scale))


def _scale_x(scale: RenderScale, value: int) -> int:
    return int(round(value * scale.x))


def _scale_y(scale: RenderScale, value: int) -> int:
    return int(round(value * scale.y))


def _scale_draw(scale: RenderScale, value: int) -> int:
    return max(int(round(value * scale.draw)), 1)


@lru_cache(maxsize=32)
def _load_default_font(pixel_size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=pixel_size)


def _scaled_font(scale: RenderScale, size: int) -> ImageFont.FreeTypeFont:
    return _load_default_font(max(_scale_draw(scale, size), 8))


@dataclass(slots=True, frozen=True)
class HudLayout:
    """Legacy layout compatibility shim. Prefer passing ``hud_config``."""

    pace_anchor: tuple[int, int]
    stats_anchor: tuple[int, int]
    map_box: tuple[int, int, int, int]

    @classmethod
    def default(cls) -> "HudLayout":
        return cls(pace_anchor=(64, 48), stats_anchor=(64, 180), map_box=(980, 40, 1220, 280))


def render_hud_frame(
    width: int,
    height: int,
    hud_value: HudSample,
    route_points: list[tuple[float, float]],
    hud_config: HudConfig | HudLayout | None = None,
    elapsed_seconds: int = 0,
    *,
    total_distance_m: float | None = None,
    layout: HudLayout | None = None,
) -> Image.Image:
    """Render a HUD frame.

    ``total_distance_m`` sets the progress-bar goal for configurable HUD widgets.
    It is ignored when rendering through the legacy ``HudLayout``/``layout`` path.
    """
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    legacy_layout = _resolve_legacy_layout(hud_config, layout)
    if legacy_layout is not None:
        _render_legacy_layout(draw, legacy_layout, hud_value, route_points, elapsed_seconds)
        return image

    resolved_hud_config = validate_hud_config(_resolve_hud_config(hud_config))
    widgets = sorted((widget for widget in resolved_hud_config.widgets if widget.visible), key=lambda item: item.z_index)
    scale = _render_scale(width, height)
    for widget in widgets:
        _render_widget(
            image,
            draw,
            widget,
            hud_value,
            route_points,
            elapsed_seconds,
            resolved_hud_config.theme,
            width,
            height,
            total_distance_m,
            scale,
        )
    return image


def _resolve_legacy_layout(hud_config: HudConfig | HudLayout | None, layout: HudLayout | None) -> HudLayout | None:
    if hud_config is not None and layout is not None:
        raise TypeError("hud_config and layout cannot be passed together")
    if isinstance(hud_config, HudLayout):
        return hud_config
    return layout


def _resolve_hud_config(hud_config: HudConfig | HudLayout | None) -> HudConfig:
    if hud_config is None or isinstance(hud_config, HudLayout):
        raise TypeError("hud_config must be a HudConfig when rendering configurable widgets")
    return hud_config


def validate_hud_config(hud_config: HudConfig) -> HudConfig:
    _require_unique_widget_ids(hud_config.widgets)
    for widget in hud_config.widgets:
        _validate_widget(widget)
    return hud_config


def _render_legacy_layout(
    draw: ImageDraw.ImageDraw,
    layout: HudLayout,
    hud_value: HudSample,
    route_points: list[tuple[float, float]],
    elapsed_seconds: int,
) -> None:
    draw.rounded_rectangle((40, 30, 430, 320), radius=20, fill=(0, 0, 0, 150))
    draw.text(layout.pace_anchor, f"Pace {hud_value.pace_seconds_per_km:.0f}s/km", fill=(255, 255, 255, 255))
    draw.text(layout.stats_anchor, f"Dist {hud_value.distance_m / 1000:.2f} km", fill=(255, 255, 255, 255))
    draw.text((layout.stats_anchor[0], layout.stats_anchor[1] + 36), f"HR {hud_value.heart_rate_bpm}", fill=(255, 255, 255, 255))
    draw.text((layout.stats_anchor[0], layout.stats_anchor[1] + 72), f"Cad {hud_value.cadence_spm}", fill=(255, 255, 255, 255))
    draw.text((layout.stats_anchor[0], layout.stats_anchor[1] + 108), f"Time {elapsed_seconds}s", fill=(255, 255, 255, 255))
    _draw_legacy_route_map(draw, route_points, layout.map_box)


def _render_widget(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    route_points: list[tuple[float, float]],
    elapsed_seconds: int,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    total_distance_m: float | None,
    scale: RenderScale,
) -> None:
    if widget.type == "progress_bar":
        _draw_progress_bar(draw, widget, hud_value.distance_m, total_distance_m, theme, frame_width, frame_height, scale)
    elif widget.type == "stat_block":
        _draw_stat_block(draw, widget, hud_value, theme, frame_width, frame_height, scale)
    elif widget.type == "route_map":
        _draw_route_map(image, draw, widget, route_points, hud_value, theme, frame_width, frame_height, scale)
    elif widget.type == "hero_metric":
        _draw_hero_metric(draw, widget, hud_value.pace_seconds_per_km, theme, frame_width, frame_height, scale)
    elif widget.type == "metric_card":
        _draw_metric_card(draw, widget, hud_value, elapsed_seconds, theme, frame_width, frame_height, scale)
    elif widget.type == "context_card":
        _draw_context_card(draw, widget, hud_value.timestamp, theme, frame_width, frame_height, scale)
    else:
        raise ValueError(f"unknown widget type '{widget.type}' for widget '{widget.id}'")


def _validate_widget(widget: HudWidgetConfig) -> None:
    if widget.anchor not in SUPPORTED_WIDGET_ANCHORS:
        supported = ", ".join(sorted(SUPPORTED_WIDGET_ANCHORS))
        raise ValueError(
            f"unsupported anchor '{widget.anchor}' for widget '{widget.id}' of type '{widget.type}'; "
            f"supported anchors: {supported}"
        )
    if widget.type == "progress_bar":
        _require_supported_binding(widget, {"distance_m"})
        _validate_progress_bar_widget(widget)
    elif widget.type == "stat_block":
        _require_supported_binding(widget, {"altitude_m", "distance_m", "heart_rate_bpm"})
    elif widget.type == "route_map":
        _require_supported_binding(widget, {"route_points"})
    elif widget.type == "hero_metric":
        _require_supported_binding(widget, {"pace_seconds_per_km"})
    elif widget.type == "metric_card":
        _require_supported_binding(widget, {"pace_seconds_per_km", "heart_rate_bpm", "cadence_spm", "elapsed_seconds", "speed_mps"})
    elif widget.type == "context_card":
        _require_supported_binding(widget, {"timestamp"})
    else:
        raise ValueError(f"unknown widget type '{widget.type}' for widget '{widget.id}'")


def _validate_progress_bar_widget(widget: HudWidgetConfig) -> None:
    if widget.width < PROGRESS_BAR_MIN_WIDTH:
        raise ValueError(
            f"progress_bar widget '{widget.id}' requires a minimum width of {PROGRESS_BAR_MIN_WIDTH}px "
            f"(got {widget.width}px)"
        )


def _require_supported_binding(widget: HudWidgetConfig, supported_bindings: set[str]) -> str:
    binding = widget.bindings.get("value")
    if binding not in supported_bindings:
        supported = ", ".join(sorted(supported_bindings))
        raise ValueError(
            f"unsupported binding '{binding}' for widget '{widget.id}' of type '{widget.type}'; "
            f"supported bindings: {supported}"
        )
    return binding


def _resolve_widget_origin(widget: HudWidgetConfig, frame_width: int, frame_height: int, scale: RenderScale) -> tuple[int, int]:
    left = _scale_x(scale, widget.x)
    top = _scale_y(scale, widget.y)
    if "right" in widget.anchor:
        left += frame_width - _scale_x(scale, HUD_REFERENCE_WIDTH)
    if "bottom" in widget.anchor:
        top += frame_height - _scale_y(scale, HUD_REFERENCE_HEIGHT)
    return (max(left, 0), max(top, 0))


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    distance_m: float | None,
    total_distance_m: float | None,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    goal_source_m = total_distance_m if total_distance_m is not None else distance_m
    goal_m = max(goal_source_m if goal_source_m is not None else 1.0, 1.0)
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    if not bool(widget.style.get("transparent_panel", False)):
        draw.rounded_rectangle((left, top, left + w, top + h), radius=_scale_draw(scale, 18), fill=tuple(theme.panel_rgba))
    track_left = left + _scale_x(scale, 16)
    track_right = left + w - _scale_x(scale, 16)
    track_y = top + _scale_y(scale, 42)
    draw.line((track_left, track_y, track_right, track_y), fill=tuple(theme.text_rgba), width=_scale_draw(scale, 2))
    for kilometer in range(int(goal_m // 1000) + 1):
        ratio = kilometer / max(goal_m / 1000.0, 1.0)
        x = track_left + int((track_right - track_left) * ratio)
        tick_height = _scale_draw(scale, 20) if kilometer % 2 == 0 else _scale_draw(scale, 14)
        draw.line((x, track_y - tick_height // 2, x, track_y + tick_height // 2), fill=tuple(theme.text_rgba), width=_scale_draw(scale, 2))
    progress_value_m = distance_m if distance_m is not None else 0.0
    progress_ratio = min(max(progress_value_m / goal_m, 0.0), 1.0)
    marker_x = track_left + int((track_right - track_left) * progress_ratio)
    r = _scale_draw(scale, 9)
    draw.ellipse((marker_x - r, track_y - r, marker_x + r, track_y + r), fill=tuple(theme.accent_rgba), outline=tuple(theme.text_rgba))


def _draw_stat_block(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    binding = _require_supported_binding(widget, {"altitude_m", "distance_m", "heart_rate_bpm"})
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    draw.rounded_rectangle(
        (left, top, left + w, top + h),
        radius=_scale_draw(scale, 20),
        fill=tuple(theme.panel_rgba),
    )
    label = str(widget.style.get("label", "Metric"))
    unit = str(widget.style.get("unit", ""))
    align = str(widget.style.get("align", "left"))
    value_text = _stat_block_value(binding, hud_value, decimals=int(widget.style.get("decimals", 0)))
    if align == "right":
        value_right = left + w - _scale_x(scale, 12)
        draw.text((value_right, top + _scale_y(scale, 12)), label, fill=tuple(theme.text_rgba), anchor="ra", font=_scaled_font(scale, 18))
        draw.text((value_right, top + _scale_y(scale, 38)), value_text, fill=tuple(theme.text_rgba), anchor="ra", font=_scaled_font(scale, 18))
        draw.text((value_right, top + _scale_y(scale, 58)), unit, fill=tuple(theme.text_rgba), anchor="ra", font=_scaled_font(scale, 18))
        return

    draw.text((left + _scale_x(scale, 12), top + _scale_y(scale, 12)), label, fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    draw.text((left + _scale_x(scale, 12), top + _scale_y(scale, 38)), value_text, fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    draw.text((left + w - _scale_x(scale, 12), top + _scale_y(scale, 58)), unit, fill=tuple(theme.text_rgba), anchor="ra", font=_scaled_font(scale, 18))


def _stat_block_value(binding: str, hud_value: HudSample, decimals: int) -> str:
    if binding == "altitude_m":
        return "--" if hud_value.altitude_m is None else f"{hud_value.altitude_m:.0f}"
    if binding == "distance_m":
        if hud_value.distance_m is None:
            return "--"
        return f"{hud_value.distance_m / 1000:.{decimals}f}"
    if binding == "heart_rate_bpm":
        return "--" if hud_value.heart_rate_bpm is None else str(hud_value.heart_rate_bpm)
    raise AssertionError(f"unsupported stat_block binding '{binding}'")


def _draw_route_map(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    route_points: list[tuple[float, float]],
    hud_value: HudSample,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    shape = str(widget.style.get("shape", "rect"))
    widget_image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    widget_draw = ImageDraw.Draw(widget_image)
    if shape == "circle":
        widget_draw.ellipse((0, 0, w, h), fill=tuple(theme.panel_rgba), outline=(255, 255, 255, 120))
    else:
        widget_draw.rounded_rectangle(
            (0, 0, w, h),
            radius=_scale_draw(scale, 16),
            fill=tuple(theme.panel_rgba),
            outline=(255, 255, 255, 120),
        )
    label = str(widget.style.get("label", "Route map"))
    if label:
        widget_draw.text((_scale_x(scale, 12), _scale_y(scale, 10)), label, fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    if len(route_points) < 2:
        image.alpha_composite(widget_image, (left, top))
        return

    map_left = _scale_x(scale, 12)
    map_top = _scale_y(scale, 36) if label else _scale_y(scale, 12)
    map_bottom = h - _scale_y(scale, 12)
    inner_width = max(w - _scale_x(scale, 24), 1)
    inner_height = max(h - (_scale_y(scale, 48) if label else _scale_y(scale, 24)), 1)
    latitudes = [point[0] for point in route_points]
    longitudes = [point[1] for point in route_points]
    lat_min, lat_max = min(latitudes), max(latitudes)
    lon_min, lon_max = min(longitudes), max(longitudes)

    def project(point: tuple[float, float]) -> tuple[float, float]:
        lat, lon = point
        x = map_left + ((lon - lon_min) / max(lon_max - lon_min, 1e-9)) * inner_width
        y = map_bottom - ((lat - lat_min) / max(lat_max - lat_min, 1e-9)) * inner_height
        return (x, y)

    projected = [project(point) for point in route_points]
    widget_draw.line(projected, fill=tuple(theme.accent_rgba), width=_scale_draw(scale, 4))
    current_point = _resolve_current_route_point(route_points, hud_value)
    if current_point is not None:
        x, y = project(current_point)
        r = _scale_draw(scale, 6)
        widget_draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 90, 90, 255))

    if shape == "circle":
        mask = Image.new("L", (w, h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, w, h), fill=255)
        image.paste(widget_image, (left, top), mask)
        return

    image.alpha_composite(widget_image, (left, top))


def _draw_hero_metric(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    pace_seconds_per_km: float | None,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(scale, 22), fill=tuple(theme.panel_rgba))
    draw.text((left + _scale_x(scale, 20), top + _scale_y(scale, 18)), str(widget.style.get("label", "Pace")), fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    draw.text((left + _scale_x(scale, 20), top + _scale_y(scale, 54)), _format_pace(pace_seconds_per_km), fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    draw.text((right - _scale_x(scale, 12), bottom - _scale_y(scale, 12)), "/km", fill=(255, 255, 255, 160), anchor="rs", font=_scaled_font(scale, 18))


def _draw_metric_card(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    elapsed_seconds: int,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    if widget.style.get("variant") == "compact":
        draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(scale, 20), fill=tuple(theme.panel_rgba))
        label = str(widget.style.get("label", "Metric"))
        draw.text((left + _scale_x(scale, 12), top + _scale_y(scale, 12)), label, fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
        draw.text((left + _scale_x(scale, 12), top + _scale_y(scale, 34)), _metric_value(widget, hud_value, elapsed_seconds), fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
        draw.text((right - _scale_x(scale, 12), bottom - _scale_y(scale, 12)), _metric_suffix(widget), fill=(255, 255, 255, 160), anchor="rs", font=_scaled_font(scale, 18))
        return

    draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(scale, 18), fill=tuple(theme.panel_rgba))
    label = str(widget.style.get("label", "Metric"))
    draw.text((left + _scale_x(scale, 16), top + _scale_y(scale, 16)), label, fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    draw.text((left + _scale_x(scale, 16), top + _scale_y(scale, 52)), _metric_value(widget, hud_value, elapsed_seconds), fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    draw.text((left + _scale_x(scale, 16), bottom - _scale_y(scale, 24)), _metric_suffix(widget), fill=(255, 255, 255, 160), font=_scaled_font(scale, 18))


def _draw_context_card(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    timestamp: datetime,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(scale, 22), fill=tuple(theme.panel_rgba))
    draw.text((left + _scale_x(scale, 20), top + _scale_y(scale, 20)), str(widget.style.get("label", "Context")), fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    context_timestamp = timestamp if timestamp.tzinfo is None else timestamp.astimezone(timestamp.tzinfo)
    draw.text((left + _scale_x(scale, 20), top + _scale_y(scale, 70)), context_timestamp.strftime("%H:%M"), fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    draw.text((left + _scale_x(scale, 20), top + _scale_y(scale, 122)), context_timestamp.strftime("%Y.%m.%d"), fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))
    draw.text((left + _scale_x(scale, 140), top + _scale_y(scale, 70)), theme.note_text, fill=tuple(theme.text_rgba), font=_scaled_font(scale, 18))


def _draw_legacy_route_map(draw: ImageDraw.ImageDraw, route_points: list[tuple[float, float]], map_box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = map_box
    draw.rounded_rectangle(map_box, radius=16, fill=(0, 0, 0, 120), outline=(255, 255, 255, 180))
    if len(route_points) < 2:
        return

    latitudes = [point[0] for point in route_points]
    longitudes = [point[1] for point in route_points]
    lat_min, lat_max = min(latitudes), max(latitudes)
    lon_min, lon_max = min(longitudes), max(longitudes)

    def project(point: tuple[float, float]) -> tuple[float, float]:
        lat, lon = point
        x = left + 12 + ((lon - lon_min) / max(lon_max - lon_min, 1e-9)) * ((right - left) - 24)
        y = bottom - 12 - ((lat - lat_min) / max(lat_max - lat_min, 1e-9)) * ((bottom - top) - 24)
        return (x, y)

    projected = [project(point) for point in route_points]
    draw.line(projected, fill=(0, 200, 255, 255), width=4)
    x, y = projected[-1]
    draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 90, 90, 255))


def _metric_value(widget: HudWidgetConfig, hud_value: HudSample, elapsed_seconds: int) -> str:
    binding = _require_supported_binding(widget, {"pace_seconds_per_km", "heart_rate_bpm", "cadence_spm", "elapsed_seconds", "speed_mps"})
    if binding == "pace_seconds_per_km":
        return _format_pace(hud_value.pace_seconds_per_km)
    if binding == "heart_rate_bpm":
        return "--" if hud_value.heart_rate_bpm is None else str(hud_value.heart_rate_bpm)
    if binding == "cadence_spm":
        return "--" if hud_value.cadence_spm is None else str(hud_value.cadence_spm)
    if binding == "elapsed_seconds":
        hours, remainder = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if binding == "speed_mps":
        return "--" if hud_value.speed_mps is None else f"{hud_value.speed_mps * 3.6:.1f}"
    raise AssertionError(f"unreachable metric binding '{binding}'")


def _metric_suffix(widget: HudWidgetConfig) -> str:
    binding = _require_supported_binding(widget, {"pace_seconds_per_km", "heart_rate_bpm", "cadence_spm", "elapsed_seconds", "speed_mps"})
    if binding == "pace_seconds_per_km":
        return "/km"
    if binding == "heart_rate_bpm":
        return "bpm"
    if binding == "cadence_spm":
        return "spm"
    if binding == "elapsed_seconds":
        return "hh:mm:ss"
    if binding == "speed_mps":
        return "km/h"
    raise AssertionError(f"unreachable metric binding '{binding}'")


def _format_pace(pace_seconds_per_km: float | None) -> str:
    if pace_seconds_per_km is None:
        return "--:--"
    total_seconds = max(int(round(pace_seconds_per_km)), 0)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _resolve_current_route_point(
    route_points: list[tuple[float, float]], hud_value: HudSample
) -> tuple[float, float] | None:
    if hud_value.latitude is None or hud_value.longitude is None:
        return None

    current = (hud_value.latitude, hud_value.longitude)
    closest_point = route_points[-1]
    closest_distance_sq = float("inf")

    for segment_start, segment_end in zip(route_points, route_points[1:]):
        candidate = _project_point_onto_segment(current, segment_start, segment_end)
        distance_sq = _distance_squared(current, candidate)
        if distance_sq < closest_distance_sq:
            closest_point = candidate
            closest_distance_sq = distance_sq

    return closest_point


def _project_point_onto_segment(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> tuple[float, float]:
    start_lat, start_lon = segment_start
    end_lat, end_lon = segment_end
    delta_lat = end_lat - start_lat
    delta_lon = end_lon - start_lon
    segment_length_sq = (delta_lat * delta_lat) + (delta_lon * delta_lon)
    if segment_length_sq <= 0.0:
        return segment_start

    point_lat, point_lon = point
    projection = (
        ((point_lat - start_lat) * delta_lat) + ((point_lon - start_lon) * delta_lon)
    ) / segment_length_sq
    clamped_projection = min(max(projection, 0.0), 1.0)
    return (
        start_lat + (delta_lat * clamped_projection),
        start_lon + (delta_lon * clamped_projection),
    )


def _distance_squared(left: tuple[float, float], right: tuple[float, float]) -> float:
    return ((left[0] - right[0]) ** 2) + ((left[1] - right[1]) ** 2)
