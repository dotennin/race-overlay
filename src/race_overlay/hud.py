import math
import time
import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from importlib.resources import files

from PIL import Image, ImageDraw, ImageFont

from race_overlay.hud_schema import (
    HUD_FONT_FAMILY_OPTIONS,
    HUD_FONT_WEIGHT_OPTIONS,
    HudConfig,
    HudThemeConfig,
    HudWidgetConfig,
    _require_rgba_list,
    _require_unique_widget_ids,
    validate_hud_theme_config,
)
from race_overlay.models import HudSample
from race_overlay.sampling import LAP_WATERFALL_DEFAULT_VISIBLE_ROWS, LapWaterfallRow, LapWaterfallState

HUD_REFERENCE_WIDTH = 1280
HUD_REFERENCE_HEIGHT = 720
PROGRESS_BAR_MIN_WIDTH = 232
SUPPORTED_WIDGET_ANCHORS = {"top-left",
                            "top-right", "bottom-left", "bottom-right"}
LEGACY_DEFAULT_FONT_SIZE_PX = 18
ROUTE_MAP_DEFAULT_SHAPE = "circle"
ROUTE_MAP_ZOOM_PERCENT_MAX = 500
WIDGET_PANEL_RGBA = (12, 18, 28, 168)
ROUTE_MAP_PANEL_RGBA = (6, 10, 18, 148)
ROUTE_MAP_PANEL_OUTLINE_RGBA = (6, 10, 18, 148)
ROUTE_MAP_ROUTE_RGBA = (34, 255, 138, 255)
ROUTE_MAP_REMAINING_RGBA = (13, 144, 195, 255)
ROUTE_MAP_MARKER_RGBA = (228, 255, 238, 255)
ROUTE_MAP_HEADING_ARROW_RGBA = (74, 155, 255, 255)
ROUTE_MAP_HEADING_ARROW_TEAL_RGBA = (0, 215, 180, 255)
ROUTE_MAP_HEADING_ARROW_HEAD_RGBA = (255, 255, 255, 255)
PROGRESS_BAR_FILL_RGBA = (34, 255, 138, 255)
PROGRESS_BAR_RAIL_RGBA = (8, 12, 20, 220)
PROGRESS_BAR_TICK_RGBA = (230, 238, 245, 168)
LAP_WATERFALL_LATEST_FILL_RGBA = (24, 98, 166, 92)
LAP_WATERFALL_LATEST_OUTLINE_RGBA = (34, 255, 138, 220)
LAP_WATERFALL_LATEST_GLOW_RGBA = (74, 155, 255, 92)
ROUTE_MAP_CACHE_MAX_ENTRIES = 32
_FONT_FILES = {
    "sans": {"regular": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf"},
    "serif": {"regular": "DejaVuSerif.ttf", "bold": "DejaVuSerif-Bold.ttf"},
    "mono": {"regular": "DejaVuSansMono.ttf", "bold": "DejaVuSansMono-Bold.ttf"},
    "broadcast_ui": {"regular": "BarlowSemiCondensed-Regular.ttf", "bold": "BarlowSemiCondensed-Medium.ttf"},
    "broadcast_value": {"regular": "BarlowSemiCondensed-BoldItalic.ttf", "bold": "BarlowSemiCondensed-BoldItalic.ttf"},
}


@dataclass(slots=True, frozen=True)
class RenderScale:
    x: float
    y: float
    draw: float


@dataclass(slots=True, frozen=True)
class RouteProjection:
    point: tuple[float, float]
    tangent: tuple[float, float]
    segment_start: tuple[float, float]
    segment_end: tuple[float, float]
    segment_index: int


@dataclass(slots=True, frozen=False)
class RouteMapCache:
    """Cache for static route map rendering data."""
    background_image: Image.Image
    projected_points: list[tuple[float, float]]
    project_fn: object  # Callable, but we avoid typing.Callable for simplicity



# Module-level cache for route map static data
_route_map_cache: dict[str, RouteMapCache] = {}


def _get_route_map_cache() -> dict[str, RouteMapCache]:
    """Get the route map cache dictionary."""
    return _route_map_cache


def _clear_route_map_cache() -> None:
    """Clear all route map cache entries."""
    _route_map_cache.clear()


def _store_route_map_cache_entry(cache_key: str, cache_entry: RouteMapCache) -> None:
    if cache_key not in _route_map_cache and len(_route_map_cache) >= ROUTE_MAP_CACHE_MAX_ENTRIES:
        oldest_key = next(iter(_route_map_cache))
        _route_map_cache.pop(oldest_key, None)
    _route_map_cache[cache_key] = cache_entry


def _route_map_cache_key(
    widget: HudWidgetConfig,
    route_points: list[tuple[float, float]],
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> str:
    """Generate a cache key for route map static data."""
    # Include all parameters that affect static rendering
    route_hash = hash(tuple(route_points))
    title_font_hash = hash((
        widget.style.get("title_font_family", _theme_role_value(theme, "title_font_family", "font_family")),
        widget.style.get("title_font_weight", _theme_role_value(theme, "title_font_weight", "font_weight")),
        widget.style.get("title_font_size_px", _theme_role_value(theme, "title_font_size_px", "font_size_px")),
    ))
    widget_hash = hash((
        widget.id,
        widget.width,
        widget.height,
        widget.anchor,
        widget.x,
        widget.y,
        str(widget.style.get("shape", ROUTE_MAP_DEFAULT_SHAPE)),
        tuple(widget.style.get("background_rgba", ROUTE_MAP_PANEL_RGBA)),
        tuple(widget.style.get("remaining_rgba", ROUTE_MAP_REMAINING_RGBA)),
        widget.style.get("zoom_percent", 100),
        str(widget.style.get("label", "Route map")),
        widget.style.get("show_panel", None),
        widget.style.get("transparent_panel", None),
        title_font_hash,
    ))
    theme_hash = hash((
        tuple(theme.text_rgba),
        _theme_role_value(theme, "title_font_family", "font_family"),
        _theme_role_value(theme, "title_font_weight", "font_weight"),
        _theme_role_value(theme, "title_font_size_px", "font_size_px"),
    ))
    scale_hash = hash((scale.x, scale.y, scale.draw))
    return f"route_map_{frame_width}x{frame_height}_{widget_hash}_{route_hash}_{theme_hash}_{scale_hash}"


ROUTE_MAP_SHAPES = ("circle", "rounded-rect", "square")


@dataclass(slots=True, frozen=True)
class ProgressBarTextLayout:
    current_anchor: tuple[int, int]
    total_anchor: tuple[int, int]


def _route_map_shape(widget: HudWidgetConfig) -> str:
    shape = str(widget.style.get("shape", "circle"))
    if shape not in ROUTE_MAP_SHAPES:
        supported = ", ".join(ROUTE_MAP_SHAPES)
        raise ValueError(f"supported shapes: {supported}")
    return shape


def _route_map_zoom_percent(widget: HudWidgetConfig) -> int:
    value = widget.style.get("zoom_percent", 90)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"widget '{widget.id}' style.zoom_percent must be an integer")
    if value < 1:
        raise ValueError(f"widget '{widget.id}' style.zoom_percent must be at least 1")
    if value > ROUTE_MAP_ZOOM_PERCENT_MAX:
        raise ValueError(f"widget '{widget.id}' style.zoom_percent must be at most {ROUTE_MAP_ZOOM_PERCENT_MAX}")
    return value


def _route_map_projection_bounds(
    route_points: list[tuple[float, float]],
    left: int,
    top: int,
    right: int,
    bottom: int,
    zoom_percent: int,
) -> tuple[float, float, float, float, float, float, float]:
    latitudes = [point[0] for point in route_points]
    longitudes = [point[1] for point in route_points]
    lat_min, lat_max = min(latitudes), max(latitudes)
    lon_min, lon_max = min(longitudes), max(longitudes)

    lat_range = max(lat_max - lat_min, 1e-9)
    lon_range = max(lon_max - lon_min, 1e-9)
    zoom_scale = zoom_percent / 100.0

    inner_width = max(right - left, 1)
    inner_height = max(bottom - top, 1)
    projection_scale = min(inner_width / lon_range, inner_height / lat_range) * zoom_scale
    content_width = lon_range * projection_scale
    content_height = lat_range * projection_scale
    offset_x = left + (inner_width - content_width) / 2
    offset_y = top + (inner_height - content_height) / 2
    return lat_min, lat_max, lon_min, lon_max, projection_scale, offset_x, offset_y


def _progress_bar_text_layout(left: int, top: int, width: int, height: int, label: str) -> ProgressBarTextLayout:
    value_baseline_y = top + 14
    current_x = left + 16 + (80 if label else 0)
    total_x = left + width - 16
    return ProgressBarTextLayout(current_anchor=(current_x, value_baseline_y), total_anchor=(total_x, value_baseline_y))


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
def _load_default_font(pixel_size: int, family: str = "sans", weight: str = "regular") -> ImageFont.FreeTypeFont:
    font_filename = _FONT_FILES[family][weight]

    if family in ("broadcast_ui", "broadcast_value"):
        try:
            font_path = files(
                "race_overlay.assets.fonts").joinpath(font_filename)
            return ImageFont.truetype(str(font_path), pixel_size)
        except (OSError, AttributeError):
            pass

    try:
        return ImageFont.truetype(font_filename, pixel_size)
    except OSError:
        return ImageFont.load_default(size=pixel_size)


def _scaled_font(
    scale: RenderScale, size: int, font_family: str = "sans", font_weight: str = "regular"
) -> ImageFont.FreeTypeFont:
    return _load_default_font(max(_scale_draw(scale, size), 8), font_family, font_weight)


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
    lap_state: LapWaterfallState | None = None,
    lap_states: dict[str, LapWaterfallState] | None = None,
) -> Image.Image:
    """Render a HUD frame.

    ``total_distance_m`` sets the progress-bar goal for configurable HUD widgets.
    It is ignored when rendering through the legacy ``HudLayout``/``layout`` path.
    """
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    legacy_layout = _resolve_legacy_layout(hud_config, layout)
    if legacy_layout is not None:
        _render_legacy_layout(draw, legacy_layout, hud_value,
                              route_points, elapsed_seconds)
        return image

    resolved_hud_config = validate_hud_config(_resolve_hud_config(hud_config))
    widgets = sorted(
        (widget for widget in resolved_hud_config.widgets if widget.visible), key=lambda item: item.z_index)
    return render_prepared_hud_frame(
        width=width,
        height=height,
        hud_value=hud_value,
        route_points=route_points,
        theme=resolved_hud_config.theme,
        widgets=widgets,
        elapsed_seconds=elapsed_seconds,
        total_distance_m=total_distance_m,
        lap_state=lap_state,
        lap_states=lap_states,
    )


def render_prepared_hud_frame(
    width: int,
    height: int,
    hud_value: HudSample,
    route_points: list[tuple[float, float]],
    theme: HudThemeConfig,
    widgets: list[HudWidgetConfig],
    elapsed_seconds: int = 0,
    *,
    total_distance_m: float | None = None,
    lap_state: LapWaterfallState | None = None,
    lap_states: dict[str, LapWaterfallState] | None = None,
    route_map_cache_keys: dict[str, str] | None = None,
) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = _render_scale(width, height)
    for widget in widgets:
        _render_widget(
            image,
            draw,
            widget,
            hud_value,
            route_points,
            elapsed_seconds,
            theme,
            width,
            height,
            total_distance_m,
            scale,
            lap_state=lap_state,
            lap_states=lap_states,
            route_map_cache_key=route_map_cache_keys.get(widget.id) if route_map_cache_keys is not None else None,
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
        raise TypeError(
            "hud_config must be a HudConfig when rendering configurable widgets")
    return hud_config


def validate_hud_config(hud_config: HudConfig) -> HudConfig:
    validate_hud_theme_config(hud_config.theme)
    _require_unique_widget_ids(hud_config.widgets)
    for widget in hud_config.widgets:
        _validate_widget(widget)
    return hud_config


def prime_route_map_caches(
    *,
    widgets: list[HudWidgetConfig],
    route_points: list[tuple[float, float]],
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
) -> dict[str, str]:
    if len(route_points) < 2:
        return {}

    scale = _render_scale(frame_width, frame_height)
    cache_keys: dict[str, str] = {}
    for widget in widgets:
        if widget.type != "route_map":
            continue
        w = _scale_x(scale, widget.width)
        h = _scale_y(scale, widget.height)
        shape = str(widget.style.get("shape", ROUTE_MAP_DEFAULT_SHAPE))
        cache_key = _route_map_cache_key(widget, route_points, theme, frame_width, frame_height, scale)
        if cache_key not in _route_map_cache:
            _store_route_map_cache_entry(
                cache_key,
                _create_route_map_cache(widget, route_points, w, h, shape, scale, theme),
            )
        cache_keys[widget.id] = cache_key
    return cache_keys


def _render_legacy_layout(
    draw: ImageDraw.ImageDraw,
    layout: HudLayout,
    hud_value: HudSample,
    route_points: list[tuple[float, float]],
    elapsed_seconds: int,
) -> None:
    draw.rounded_rectangle((40, 30, 430, 320), radius=20, fill=(0, 0, 0, 150))
    draw.text(layout.pace_anchor, f"Pace {
              hud_value.pace_seconds_per_km:.0f}s/km", fill=(255, 255, 255, 255))
    draw.text(layout.stats_anchor, f"Dist {
              hud_value.distance_m / 1000:.2f} km", fill=(255, 255, 255, 255))
    draw.text((layout.stats_anchor[0], layout.stats_anchor[1] + 36),
              f"HR {hud_value.heart_rate_bpm}", fill=(255, 255, 255, 255))
    draw.text((layout.stats_anchor[0], layout.stats_anchor[1] + 72),
              f"Cad {hud_value.cadence_spm}", fill=(255, 255, 255, 255))
    draw.text((layout.stats_anchor[0], layout.stats_anchor[1] + 108),
              f"Time {elapsed_seconds}s", fill=(255, 255, 255, 255))
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
    *,
    lap_state: LapWaterfallState | None = None,
    lap_states: dict[str, LapWaterfallState] | None = None,
    route_map_cache_key: str | None = None,
) -> None:
    if widget.type == "progress_bar":
        _draw_progress_bar(draw, widget, hud_value.distance_m,
                           total_distance_m, theme, frame_width, frame_height, scale)
    elif widget.type == "stat_block":
        _draw_stat_block(draw, widget, hud_value, theme,
                         frame_width, frame_height, scale)
    elif widget.type == "route_map":
        _draw_route_map(image, draw, widget, route_points,
                        hud_value, theme, frame_width, frame_height, scale, route_map_cache_key=route_map_cache_key)
    elif widget.type == "hero_metric":
        _draw_hero_metric(draw, widget, hud_value.pace_seconds_per_km,
                          theme, frame_width, frame_height, scale)
    elif widget.type == "metric_card":
        _draw_metric_card(draw, widget, hud_value, elapsed_seconds,
                          theme, frame_width, frame_height, scale)
    elif widget.type == "context_card":
        _draw_context_card(draw, widget, hud_value.timestamp,
                           theme, frame_width, frame_height, scale)
    elif widget.type == "lap_waterfall":
        widget_lap_state = lap_state
        if lap_states is not None:
            widget_lap_state = lap_states.get(widget.id, widget_lap_state)
        _draw_lap_waterfall(image, widget, widget_lap_state, theme, frame_width, frame_height, scale)
    else:
        raise ValueError(f"unknown widget type '{
                         widget.type}' for widget '{widget.id}'")


def _validate_widget(widget: HudWidgetConfig) -> None:
    _validate_widget_core_fields(widget)
    if widget.anchor not in SUPPORTED_WIDGET_ANCHORS:
        supported = ", ".join(sorted(SUPPORTED_WIDGET_ANCHORS))
        raise ValueError(
            f"unsupported anchor '{widget.anchor}' for widget '{
                widget.id}' of type '{widget.type}'; "
            f"supported anchors: {supported}"
        )
    if widget.width <= 0:
        raise ValueError(f"widget '{widget.id}' width must be greater than 0")
    if widget.height <= 0:
        raise ValueError(f"widget '{widget.id}' height must be greater than 0")
    if widget.type == "progress_bar":
        _require_supported_binding(widget, {"distance_m"})
        _validate_progress_bar_widget(widget)
    elif widget.type == "stat_block":
        _require_supported_binding(
            widget, {"altitude_m", "distance_m", "heart_rate_bpm"})
    elif widget.type == "route_map":
        _validate_route_map_widget(widget)
    elif widget.type == "hero_metric":
        _require_supported_binding(widget, {"pace_seconds_per_km"})
    elif widget.type == "metric_card":
        _require_supported_binding(widget, {
                                   "pace_seconds_per_km", "heart_rate_bpm", "cadence_spm", "elapsed_seconds", "speed_mps", "stride_length_m"})
    elif widget.type == "context_card":
        _require_supported_binding(widget, {"timestamp"})
    elif widget.type == "lap_waterfall":
        _require_supported_binding(widget, {"laps"})
        _validate_lap_waterfall_widget_style(widget)
    else:
        raise ValueError(f"unknown widget type '{
                         widget.type}' for widget '{widget.id}'")
    _validate_widget_style(widget)


def _validate_widget_core_fields(widget: HudWidgetConfig) -> None:
    if not isinstance(widget.visible, bool):
        raise ValueError(f"widget '{widget.id}' visible must be a boolean")
    _require_widget_int(widget, "x")
    _require_widget_int(widget, "y")
    _require_widget_int(widget, "z_index")
    _require_widget_int(widget, "width", minimum=1)
    _require_widget_int(widget, "height", minimum=1)


def _require_widget_int(widget: HudWidgetConfig, field_name: str, *, minimum: int | None = None) -> int:
    value = getattr(widget, field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"widget '{widget.id}' {
                         field_name} must be a finite integer")
    if minimum is not None and value < minimum:
        qualifier = f"at least {minimum}" if minimum != 1 else "greater than 0"
        raise ValueError(f"widget '{widget.id}' {
                         field_name} must be {qualifier}")
    return value


def _validate_widget_style(widget: HudWidgetConfig) -> None:
    _validate_optional_enum_style(
        widget, "unit_font_family", HUD_FONT_FAMILY_OPTIONS)
    _validate_optional_enum_style(
        widget, "unit_font_weight", HUD_FONT_WEIGHT_OPTIONS)
    _validate_optional_font_size_style(widget, "unit_font_size_px")
    _validate_optional_enum_style(
        widget, "value_font_family", HUD_FONT_FAMILY_OPTIONS)
    _validate_optional_enum_style(
        widget, "value_font_weight", HUD_FONT_WEIGHT_OPTIONS)
    _validate_optional_font_size_style(widget, "value_font_size_px")
    _validate_optional_bool_style(widget, "show_panel")
    _validate_optional_bool_style(widget, "transparent_panel")
    _validate_optional_bool_style(widget, "show_unit")
    _validate_optional_bool_style(widget, "show_current_value")
    _validate_optional_bool_style(widget, "show_total_value")
    _validate_optional_bool_style(widget, "show_north_marker")
    _validate_optional_bool_style(widget, "show_bearing_label")
    _validate_optional_rgba_style(widget, "fill_rgba")
    _validate_optional_rgba_style(widget, "rail_rgba")
    _validate_optional_rgba_style(widget, "tick_rgba")
    _validate_optional_non_negative_int_style(widget, "decimals")
    _validate_optional_text_style(widget, "format")


def _validate_progress_bar_widget(widget: HudWidgetConfig) -> None:
    if widget.width < PROGRESS_BAR_MIN_WIDTH:
        raise ValueError(
            f"progress_bar widget '{widget.id}' requires a minimum width of {
                PROGRESS_BAR_MIN_WIDTH}px "
            f"(got {widget.width}px)"
        )
    _validate_optional_font_size_style(widget, "current_font_size_px")


def _validate_route_map_widget(widget: HudWidgetConfig) -> None:
    _require_supported_binding(widget, {"route_points"})
    _route_map_shape(widget)
    _route_map_zoom_percent(widget)


def _validate_lap_waterfall_widget_style(widget: HudWidgetConfig) -> None:
    visible_rows = widget.style.get("visible_rows")
    if visible_rows is not None:
        if isinstance(visible_rows, bool) or not isinstance(visible_rows, int) or visible_rows < 1:
            raise ValueError(
                f"widget '{widget.id}' style.visible_rows must be a positive integer")
    fade_after_seconds = widget.style.get("fade_after_seconds")
    if fade_after_seconds is not None:
        if isinstance(fade_after_seconds, bool) or not isinstance(fade_after_seconds, (int, float)) or fade_after_seconds <= 0:
            raise ValueError(
                f"widget '{widget.id}' style.fade_after_seconds must be a positive number")
    for key in ("always_show", "show_distance", "show_time", "show_pace", "show_elevation", "show_heart_rate"):
        val = widget.style.get(key)
        if val is not None and not isinstance(val, bool):
            raise ValueError(
                f"widget '{widget.id}' style.{key} must be a boolean")


def _require_supported_binding(widget: HudWidgetConfig, supported_bindings: set[str]) -> str:
    binding = widget.bindings.get("value")
    if binding not in supported_bindings:
        supported = ", ".join(sorted(supported_bindings))
        raise ValueError(
            f"unsupported binding '{binding}' for widget '{
                widget.id}' of type '{widget.type}'; "
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


def _widget_panel_enabled(widget: HudWidgetConfig) -> bool:
    show_panel = widget.style.get("show_panel")
    if isinstance(show_panel, bool):
        return show_panel
    transparent_panel = widget.style.get("transparent_panel")
    if isinstance(transparent_panel, bool):
        return not transparent_panel
    if transparent_panel is not None:
        raise ValueError(
            f"widget '{widget.id}' style.transparent_panel must be a boolean")
    if show_panel is not None:
        raise ValueError(
            f"widget '{widget.id}' style.show_panel must be a boolean")
    return widget.type == "route_map"


def _validate_optional_enum_style(widget: HudWidgetConfig, key: str, allowed: tuple[str, ...]) -> None:
    if key not in widget.style:
        return
    value = widget.style[key]
    if not isinstance(value, str) or value not in allowed:
        allowed_values = ", ".join(allowed)
        raise ValueError(f"widget '{widget.id}' style.{
                         key} must be one of: {allowed_values}")


def _validate_optional_font_size_style(widget: HudWidgetConfig, key: str) -> None:
    if key not in widget.style:
        return
    _require_font_size_style(widget, widget.style[key], key)


def _validate_optional_bool_style(widget: HudWidgetConfig, key: str) -> None:
    if key in widget.style and not isinstance(widget.style[key], bool):
        raise ValueError(f"widget '{widget.id}' style.{key} must be a boolean")


def _validate_optional_non_negative_int_style(widget: HudWidgetConfig, key: str) -> None:
    if key not in widget.style:
        return
    value = widget.style[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"widget '{widget.id}' style.{
                         key} must be an integer")
    if value < 0:
        raise ValueError(f"widget '{widget.id}' style.{
                         key} must be at least 0")


def _validate_optional_rgba_style(widget: HudWidgetConfig, key: str) -> None:
    if key in widget.style:
        _require_rgba_style(widget, widget.style[key], key)


def _validate_optional_text_style(widget: HudWidgetConfig, key: str) -> None:
    if key in widget.style and not isinstance(widget.style[key], str):
        raise ValueError(f"widget '{widget.id}' style.{key} must be a string")


def _style_bool(widget: HudWidgetConfig, key: str, default: bool) -> bool:
    value = widget.style.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"widget '{widget.id}' style.{key} must be a boolean")
    return value


def _style_font_size(widget: HudWidgetConfig, theme: HudThemeConfig, fallback: int) -> int:
    value = widget.style.get(
        "unit_font_size_px", theme.unit_font_size_px or fallback)
    return _require_font_size_style(widget, value, "unit_font_size_px")


def _style_font_family(widget: HudWidgetConfig, theme: HudThemeConfig) -> str:
    value = widget.style.get("unit_font_family", theme.unit_font_family)
    if not isinstance(value, str) or value not in HUD_FONT_FAMILY_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_FAMILY_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.unit_font_family must be one of: {
                         allowed_values}")
    return value


def _require_font_size_style(widget: HudWidgetConfig, value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"widget '{widget.id}' style.{key} must be a number")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"widget '{widget.id}' style.{
                             key} must be a finite integer")
        value = int(value)
    if value < 8:
        raise ValueError(f"widget '{widget.id}' style.{
                         key} must be at least 8")
    return int(value)


def _style_font_weight(widget: HudWidgetConfig, theme: HudThemeConfig) -> str:
    value = widget.style.get("unit_font_weight", theme.unit_font_weight)
    if not isinstance(value, str) or value not in HUD_FONT_WEIGHT_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_WEIGHT_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.unit_font_weight must be one of: {
                         allowed_values}")
    return value


def _style_font(widget: HudWidgetConfig, theme: HudThemeConfig, scale: RenderScale, fallback: int = 18) -> ImageFont.FreeTypeFont:
    return _scaled_font(
        scale,
        _style_font_size(widget, theme, fallback),
        _style_font_family(widget, theme),
        _style_font_weight(widget, theme),
    )


def _require_rgba_style(widget: HudWidgetConfig, value: object, key: str) -> tuple[int, int, int, int]:
    rgba = _require_rgba_list(value, f"widget '{widget.id}' style.{key}")
    return (rgba[0], rgba[1], rgba[2], rgba[3])


def _style_rgba(widget: HudWidgetConfig, key: str, default: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if key not in widget.style:
        return default
    return _require_rgba_style(widget, widget.style[key], key)


def _theme_role_value(theme: HudThemeConfig, role_key: str, legacy_key: str) -> str | int:
    role_value = getattr(theme, role_key)
    if role_value is not None:
        return role_value
    legacy_value = getattr(theme, legacy_key)
    if "font_size" in role_key and legacy_value == LEGACY_DEFAULT_FONT_SIZE_PX:
        if "title" in role_key:
            return 14
        elif "value" in role_key:
            return 32
        elif "unit" in role_key:
            return 12
    return legacy_value


def _style_role_font(widget: HudWidgetConfig, theme: HudThemeConfig, scale: RenderScale, *, role: str) -> ImageFont.FreeTypeFont:
    # Widget-level overrides for all roles (unit, value, title, etc.); fallback to theme defaults
    family_key = f"{role}_font_family"
    weight_key = f"{role}_font_weight"
    size_key = f"{role}_font_size_px"

    family_value = widget.style.get(
        family_key, _theme_role_value(theme, family_key, "font_family"))
    if not isinstance(family_value, str) or family_value not in HUD_FONT_FAMILY_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_FAMILY_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.{
                         family_key} must be one of: {allowed_values}")

    weight_value = widget.style.get(
        weight_key, _theme_role_value(theme, weight_key, "font_weight"))
    if not isinstance(weight_value, str) or weight_value not in HUD_FONT_WEIGHT_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_WEIGHT_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.{
                         weight_key} must be one of: {allowed_values}")

    size_value = widget.style.get(
        size_key, _theme_role_value(theme, size_key, "font_size_px"))
    size = _require_font_size_style(widget, size_value, size_key)

    return _scaled_font(scale, size, family_value, weight_value)


def _progress_bar_value_font(
    widget: HudWidgetConfig,
    theme: HudThemeConfig,
    scale: RenderScale,
    *,
    current: bool = False,
) -> ImageFont.FreeTypeFont:
    family_value = widget.style.get("unit_font_family", _theme_role_value(
        theme, "value_font_family", "font_family"))
    if not isinstance(family_value, str) or family_value not in HUD_FONT_FAMILY_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_FAMILY_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.unit_font_family must be one of: {
                         allowed_values}")

    weight_value = widget.style.get("unit_font_weight", _theme_role_value(
        theme, "value_font_weight", "font_weight"))
    if not isinstance(weight_value, str) or weight_value not in HUD_FONT_WEIGHT_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_WEIGHT_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.unit_font_weight must be one of: {
                         allowed_values}")

    if current:
        size_value = widget.style.get("current_font_size_px")
        if size_value is None:
            size_value = widget.style.get("unit_font_size_px", _theme_role_value(
                theme, "value_font_size_px", "font_size_px"))
            size = max(_require_font_size_style(
                widget, size_value, "unit_font_size_px") - 2, 8)
        else:
            size = _require_font_size_style(
                widget, size_value, "current_font_size_px")
    else:
        size_value = widget.style.get("unit_font_size_px", _theme_role_value(
            theme, "value_font_size_px", "font_size_px"))
        size = _require_font_size_style(
            widget, size_value, "unit_font_size_px")
    return _scaled_font(scale, size, family_value, weight_value)


def _title_font(widget: HudWidgetConfig, theme: HudThemeConfig, scale: RenderScale) -> ImageFont.FreeTypeFont:
    return _style_role_font(widget, theme, scale, role="title")


def _value_font(widget: HudWidgetConfig, theme: HudThemeConfig, scale: RenderScale) -> ImageFont.FreeTypeFont:
    return _style_role_font(widget, theme, scale, role="value")


def _unit_font(widget: HudWidgetConfig, theme: HudThemeConfig, scale: RenderScale) -> ImageFont.FreeTypeFont:
    return _style_role_font(widget, theme, scale, role="unit")


def _distance_label(distance_m: float, show_units: bool) -> str:
    suffix = " KM" if show_units else ""
    return f"{distance_m / 1000:.2f}{suffix}"


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
    left, top = _resolve_widget_origin(
        widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    title_font = _title_font(widget, theme, scale)
    current_font = _progress_bar_value_font(widget, theme, scale, current=True)
    total_font = _progress_bar_value_font(widget, theme, scale, current=False)
    if _widget_panel_enabled(widget):
        draw.rounded_rectangle((left, top, left + w, top + h),
                               radius=_scale_draw(scale, 18), fill=(6, 10, 18, 120))
    text_layout = _progress_bar_text_layout(
        left, top, w, h, str(widget.style.get("label", "")))
    track_left = left + _scale_x(scale, 16)
    track_right = left + w - _scale_x(scale, 16)
    track_top = top + _scale_y(scale, 34)
    track_bottom = top + h - _scale_y(scale, 10)
    track_y = track_top + (track_bottom - track_top) // 2
    label = str(widget.style.get("label", ""))
    show_units = _style_bool(widget, "show_unit", theme.show_units)
    show_current_value = _style_bool(widget, "show_current_value", True)
    show_total_value = _style_bool(widget, "show_total_value", True)
    fill_rgba = _style_rgba(widget, "fill_rgba", PROGRESS_BAR_FILL_RGBA)
    rail_rgba = _style_rgba(widget, "rail_rgba", PROGRESS_BAR_RAIL_RGBA)
    tick_rgba = _style_rgba(widget, "tick_rgba", PROGRESS_BAR_TICK_RGBA)
    rail_radius = max((track_bottom - track_top) // 2, _scale_draw(scale, 6))
    draw.rounded_rectangle((track_left, track_top, track_right,
                           track_bottom), radius=rail_radius, fill=rail_rgba)
    draw.line((track_left, track_y, track_right, track_y),
              fill=rail_rgba, width=_scale_draw(scale, 1))
    progress_value_m = distance_m if distance_m is not None else 0.0
    progress_ratio = min(max(progress_value_m / goal_m, 0.0), 1.0)
    progress_right = track_left + \
        int((track_right - track_left) * progress_ratio)
    fill_top = track_top + _scale_y(scale, 3)
    fill_bottom = track_bottom - _scale_y(scale, 3)
    fill_radius = max((fill_bottom - fill_top) // 2, _scale_draw(scale, 4))
    if progress_right > track_left:
        draw.rounded_rectangle(
            (track_left, fill_top, max(progress_right,
             track_left + fill_radius * 2), fill_bottom),
            radius=fill_radius,
            fill=fill_rgba,
        )

    tick_distances_m = [0.0]
    minor_tick_step_m = 250.0
    while minor_tick_step_m < goal_m:
        tick_distances_m.append(minor_tick_step_m)
        minor_tick_step_m += 250.0
    if goal_m > 250.0:
        tick_distances_m.append(goal_m)

    for tick_distance_m in tick_distances_m:
        ratio = min(max(tick_distance_m / goal_m, 0.0), 1.0)
        x = track_left + int((track_right - track_left) * ratio)
        if math.isclose(tick_distance_m % 1000.0, 0.0, abs_tol=1e-6):
            tick_height = track_bottom - track_top + _scale_y(scale, 8)
        elif math.isclose(tick_distance_m % 500.0, 0.0, abs_tol=1e-6):
            tick_height = track_bottom - track_top + _scale_y(scale, 2)
        else:
            tick_height = max(track_bottom - track_top -
                              _scale_y(scale, 4), _scale_draw(scale, 6))
        draw.line((x, track_y - tick_height // 2, x, track_y +
                  tick_height // 2), fill=tick_rgba, width=_scale_draw(scale, 1))

    text_y = top + _scale_y(scale, 10)
    text_x = track_left
    if label:
        draw.text((text_x, text_y), label, fill=tuple(
            theme.text_rgba), font=title_font)
        label_box = draw.textbbox((text_x, text_y), label, font=title_font)
        text_x = label_box[2] + _scale_x(scale, 10)
    if show_current_value:
        current_text = _distance_label(progress_value_m, show_units)
        current_box = draw.textbbox((0, 0), current_text, font=current_font)
        current_text_width = current_box[2] - current_box[0]
        current_text_x = max(track_left, progress_right -
                             current_text_width - _scale_x(scale, 8))
        draw.text(
            (current_text_x, text_layout.current_anchor[1]),
            current_text,
            fill=tuple(theme.text_rgba),
            font=current_font,
        )
    if show_total_value:
        draw.text(
            text_layout.total_anchor,
            _distance_label(goal_m, show_units),
            fill=tuple(theme.text_rgba),
            anchor="ra",
            font=total_font,
        )


def _draw_stat_block(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    binding = _require_supported_binding(
        widget, {"altitude_m", "distance_m", "heart_rate_bpm"})
    left, top = _resolve_widget_origin(
        widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    variant = str(widget.style.get("variant", "standard"))

    if _widget_panel_enabled(widget):
        draw.rounded_rectangle(
            (left, top, right, bottom),
            radius=_scale_draw(scale, 20),
            fill=(6, 10, 18, 120),
        )

    title_font = _title_font(widget, theme, scale)
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    label = str(widget.style.get("label", "Metric"))
    unit = str(widget.style.get("unit", "")) if _style_bool(
        widget, "show_unit", theme.show_units) else ""
    align = str(widget.style.get("align", "left"))
    value_text = _stat_block_value(binding, hud_value)

    # Compact variant: reduced spacing
    if variant == "compact":
        if align == "right":
            value_right = right - _scale_x(scale, 12)
            value_y = top + _scale_y(scale, 28)
            draw.text(
                (value_right, top + _scale_y(scale, 8)),
                label,
                fill=tuple(theme.text_rgba),
                anchor="ra",
                font=title_font,
            )
            draw.text(
                (value_right, value_y),
                value_text,
                fill=tuple(theme.text_rgba),
                anchor="ra",
                font=value_font,
            )
            if unit:
                value_bbox = draw.textbbox(
                    (value_right, value_y), value_text, font=value_font, anchor="ra")
                unit_x = value_bbox[2] + _scale_x(scale, 6)
                unit_bbox_origin = draw.textbbox(
                    (0, 0), unit, font=unit_font, anchor="la")
                value_bbox_origin = draw.textbbox(
                    (0, 0), value_text, font=value_font, anchor="ra")
                unit_y = value_y + (value_bbox_origin[3] - unit_bbox_origin[3])
                draw.text(
                    (unit_x, unit_y),
                    unit,
                    fill=tuple(theme.text_rgba),
                    anchor="la",
                    font=unit_font,
                )
        else:
            value_x = left + _scale_x(scale, 12)
            value_y = top + _scale_y(scale, 28)
            draw.text((value_x, top + _scale_y(scale, 8)), label,
                      fill=tuple(theme.text_rgba), font=title_font)
            draw.text((value_x, value_y), value_text,
                      fill=tuple(theme.text_rgba), font=value_font)
            if unit:
                value_bbox = draw.textbbox(
                    (value_x, value_y), value_text, font=value_font, anchor="la")
                unit_x = value_bbox[2] + _scale_x(scale, 6)
                unit_bbox_origin = draw.textbbox(
                    (0, 0), unit, font=unit_font, anchor="la")
                value_bbox_origin = draw.textbbox(
                    (0, 0), value_text, font=value_font, anchor="la")
                unit_y = value_y + (value_bbox_origin[3] - unit_bbox_origin[3])
                draw.text((unit_x, unit_y), unit, fill=tuple(
                    theme.text_rgba), anchor="la", font=unit_font)
        return

    # Standard variant: original spacing
    if align == "right":
        value_right = right - _scale_x(scale, 12)
        value_y = top + _scale_y(scale, 34)
        draw.text(
            (value_right, top + _scale_y(scale, 12)),
            label,
            fill=tuple(theme.text_rgba),
            anchor="ra",
            font=title_font,
        )
        draw.text(
            (value_right, value_y),
            value_text,
            fill=tuple(theme.text_rgba),
            anchor="ra",
            font=value_font,
        )
        if unit:
            value_bbox = draw.textbbox(
                (value_right, value_y), value_text, font=value_font, anchor="ra")
            unit_x = value_bbox[2] + _scale_x(scale, 6)
            unit_bbox_origin = draw.textbbox(
                (0, 0), unit, font=unit_font, anchor="la")
            value_bbox_origin = draw.textbbox(
                (0, 0), value_text, font=value_font, anchor="ra")
            unit_y = value_y + (value_bbox_origin[3] - unit_bbox_origin[3])
            draw.text(
                (unit_x, unit_y),
                unit,
                fill=tuple(theme.text_rgba),
                anchor="la",
                font=unit_font,
            )
        return

    value_x = left + _scale_x(scale, 12)
    value_y = top + _scale_y(scale, 34)
    draw.text((value_x, top + _scale_y(scale, 12)), label,
              fill=tuple(theme.text_rgba), font=title_font)
    draw.text((value_x, value_y), value_text,
              fill=tuple(theme.text_rgba), font=value_font)
    if unit:
        value_bbox = draw.textbbox(
            (value_x, value_y), value_text, font=value_font, anchor="la")
        unit_x = value_bbox[2] + _scale_x(scale, 6)
        unit_bbox_origin = draw.textbbox(
            (0, 0), unit, font=unit_font, anchor="la")
        value_bbox_origin = draw.textbbox(
            (0, 0), value_text, font=value_font, anchor="la")
        unit_y = value_y + (value_bbox_origin[3] - unit_bbox_origin[3])
        draw.text((unit_x, unit_y), unit, fill=tuple(
            theme.text_rgba), anchor="la", font=unit_font)


def _stat_block_value(binding: str, hud_value: HudSample) -> str:
    if binding == "altitude_m":
        return "--" if hud_value.altitude_m is None else f"{hud_value.altitude_m:.0f}"
    if binding == "distance_m":
        if hud_value.distance_m is None:
            return "--"
        return f"{hud_value.distance_m / 1000:.1f}"
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
    *,
    route_map_cache_key: str | None = None,
) -> None:
    left, top = _resolve_widget_origin(
        widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    shape = str(widget.style.get("shape", ROUTE_MAP_DEFAULT_SHAPE))
    
    # Early return if not enough points
    if len(route_points) < 2:
        # Still need to draw background and label
        widget_image = _create_route_map_background(widget, w, h, shape, scale, theme)
        image.alpha_composite(widget_image, (left, top))
        return
    
    # Check cache
    cache_key = route_map_cache_key or _route_map_cache_key(widget, route_points, theme, frame_width, frame_height, scale)
    cache = _route_map_cache.get(cache_key)
    
    if cache is None:
        # Create static components and cache them
        cache = _create_route_map_cache(widget, route_points, w, h, shape, scale, theme)
        _store_route_map_cache_entry(cache_key, cache)
    
    # Start with cached background (which already has the full route polyline)
    widget_image = cache.background_image.copy()
    widget_draw = ImageDraw.Draw(widget_image)
    
    # Compute dynamic components
    show_north_marker = _style_bool(widget, "show_north_marker", True)
    show_bearing_label = _style_bool(widget, "show_bearing_label", True)
    route_projection = _resolve_route_projection(route_points, hud_value)
    bearing_label = ""
    if route_projection is not None and show_bearing_label:
        bearing_label = _format_bearing_label(route_projection.tangent)
    
    unit_font = _unit_font(widget, theme, scale)
    
    # Draw dynamic route overlays (frame-dynamic work only)
    completed_rgba = _style_rgba(widget, "completed_rgba", ROUTE_MAP_ROUTE_RGBA)
    
    if route_projection is not None:
        # Have GPS position: overlay the completed portion in a different color
        # The base route is already rendered in the cached background
        split_index = route_projection.segment_index
        split_point_projected = cache.project_fn(route_projection.point)
        
        # Build completed path using cached projections
        completed_projected = [*cache.projected_points[:split_index + 1], split_point_projected]
        
        # Draw only the completed portion as a dynamic overlay
        if len(completed_projected) >= 2:
            widget_draw.line(completed_projected, fill=completed_rgba,
                             width=_scale_draw(scale, 4))
        
        # Draw position marker
        heading_vector = _projected_route_vector(route_projection, cache.project_fn)
        _draw_position_marker_arrow(
            widget_draw,
            split_point_projected,
            heading_vector,
            scale,
        )
    
    # Composite widget to frame
    if shape == "circle":
        mask = Image.new("L", (w, h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, w, h), fill=255)
        image.paste(widget_image, (left, top), mask)
    else:
        image.alpha_composite(widget_image, (left, top))
    
    # Draw north marker above the widget (outside background)
    if show_north_marker:
        north_y = top - _scale_y(scale, 10)
        draw.text((left + w / 2, north_y), "N",
                  fill=tuple(theme.text_rgba), anchor="ms", font=unit_font)
    
    # Draw bearing label below the widget (outside background)
    if bearing_label:
        bearing_y = top + h + _scale_y(scale, 10)
        draw.text((left + w / 2, bearing_y), bearing_label,
                  fill=tuple(theme.text_rgba), anchor="mt", font=unit_font)


def _create_route_map_background(
    widget: HudWidgetConfig,
    w: int,
    h: int,
    shape: str,
    scale: RenderScale,
    theme: HudThemeConfig,
) -> Image.Image:
    """Create the static background panel for a route map widget."""
    background_rgba = _style_rgba(widget, "background_rgba", ROUTE_MAP_PANEL_RGBA)
    widget_image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    widget_draw = ImageDraw.Draw(widget_image)
    
    if shape == "circle":
        if _widget_panel_enabled(widget):
            widget_draw.ellipse((0, 0, w, h), fill=background_rgba,
                                outline=ROUTE_MAP_PANEL_OUTLINE_RGBA)
    else:
        if _widget_panel_enabled(widget):
            widget_draw.rounded_rectangle(
                (0, 0, w, h),
                radius=_scale_draw(scale, 16),
                fill=background_rgba,
                outline=ROUTE_MAP_PANEL_OUTLINE_RGBA,
            )
    
    label = str(widget.style.get("label", "Route map"))
    title_font = _title_font(widget, theme, scale)
    if label:
        widget_draw.text((_scale_x(scale, 12), _scale_y(scale, 10)),
                         label, fill=tuple(theme.text_rgba), font=title_font)
    
    return widget_image


def _create_route_map_cache(
    widget: HudWidgetConfig,
    route_points: list[tuple[float, float]],
    w: int,
    h: int,
    shape: str,
    scale: RenderScale,
    theme: HudThemeConfig,
) -> RouteMapCache:
    """Create a cache entry with static route map components."""
    # Create background with label
    background_image = _create_route_map_background(widget, w, h, shape, scale, theme)
    
    # Compute projection parameters
    label = str(widget.style.get("label", "Route map"))
    show_top_overlays = bool(label)
    map_left = _scale_x(scale, 12)
    map_top = _scale_y(scale, 36) if show_top_overlays else _scale_y(scale, 12)
    map_bottom = h - _scale_y(scale, 12)
    inner_width = max(w - _scale_x(scale, 24), 1)
    inner_height = max(map_bottom - map_top, 1)
    lat_min, lat_max, lon_min, lon_max, projection_scale, offset_x, offset_y = _route_map_projection_bounds(
        route_points,
        map_left,
        map_top,
        map_left + inner_width,
        map_top + inner_height,
        _route_map_zoom_percent(widget),
    )

    # Create projection function
    def project(point: tuple[float, float]) -> tuple[float, float]:
        lat, lon = point
        return (
            offset_x + ((lon - lon_min) * projection_scale),
            offset_y + ((lat_max - lat) * projection_scale),
        )
    
    # Pre-project all route points
    projected_points = [project(point) for point in route_points]
    
    # Pre-render the full route polyline onto the background (clip-static work)
    # This is the key Task 2 fix: rasterize the route base layer into the cache
    background_with_route = background_image.copy()
    background_draw = ImageDraw.Draw(background_with_route)
    
    # Get route color from widget style (use remaining color as the base/neutral color)
    base_route_rgba = _style_rgba(widget, "remaining_rgba", ROUTE_MAP_REMAINING_RGBA)
    
    # Draw the full route polyline once during cache creation
    if len(projected_points) >= 2:
        background_draw.line(projected_points, fill=base_route_rgba, width=_scale_draw(scale, 4))
    
    return RouteMapCache(
        background_image=background_with_route,
        projected_points=projected_points,
        project_fn=project,
    )


def _draw_hero_metric(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    pace_seconds_per_km: float | None,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    left, top = _resolve_widget_origin(
        widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    title_font = _title_font(widget, theme, scale)
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    if _widget_panel_enabled(widget):
        draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(
            scale, 22), fill=(6, 10, 18, 120))
    draw.text(
        (left + _scale_x(scale, 20), top + _scale_y(scale, 18)),
        str(widget.style.get("label", "Pace")),
        fill=tuple(theme.text_rgba),
        font=title_font,
    )
    draw.text(
        (left + _scale_x(scale, 20), top + _scale_y(scale, 50)),
        _format_pace(pace_seconds_per_km),
        fill=tuple(theme.text_rgba),
        font=value_font,
    )
    if _style_bool(widget, "show_unit", theme.show_units):
        draw.text(
            (right - _scale_x(scale, 12), bottom - _scale_y(scale, 12)),
            "/km",
            fill=tuple(theme.text_rgba),
            anchor="rs",
            font=unit_font,
        )


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
    left, top = _resolve_widget_origin(
        widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    title_font = _title_font(widget, theme, scale)
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    label = str(widget.style.get("label", "Metric"))
    align = str(widget.style.get("align", "left"))
    variant = str(widget.style.get("variant", "standard"))

    if variant == "speed_gauge":
        _draw_speed_gauge_metric_card(
            draw,
            widget,
            hud_value,
            theme,
            frame_width,
            frame_height,
            scale,
        )
        return

    if variant == "compact":
        if _widget_panel_enabled(widget):
            draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(
                scale, 20), fill=(6, 10, 18, 120))
        value_text = _metric_value(widget, hud_value, elapsed_seconds)

        if align == "right":
            # Right-aligned: label and value on right side
            value_right = right - _scale_x(scale, 12)
            value_y = top + _scale_y(scale, 30)
            draw.text((value_right, top + _scale_y(scale, 12)), label,
                      fill=tuple(theme.text_rgba), anchor="ra", font=title_font)
            draw.text((value_right, value_y), value_text, fill=tuple(
                theme.text_rgba), anchor="ra", font=value_font)
            suffix = _metric_suffix(widget, theme)
            if suffix:
                value_bbox = draw.textbbox(
                    (value_right, value_y), value_text, font=value_font, anchor="ra")
                suffix_x = value_bbox[2] + _scale_x(scale, 6)
                suffix_bbox_origin = draw.textbbox(
                    (0, 0), suffix, font=unit_font, anchor="la")
                value_bbox_origin = draw.textbbox(
                    (0, 0), value_text, font=value_font, anchor="ra")
                suffix_y = value_y + \
                    (value_bbox_origin[3] - suffix_bbox_origin[3])
                draw.text((suffix_x, suffix_y), suffix, fill=tuple(
                    theme.text_rgba), anchor="la", font=unit_font)
        else:
            # Left-aligned: label and value on left side (default)
            value_x = left + _scale_x(scale, 12)
            value_y = top + _scale_y(scale, 30)
            draw.text((value_x, top + _scale_y(scale, 12)), label,
                      fill=tuple(theme.text_rgba), font=title_font)
            draw.text((value_x, value_y), value_text,
                      fill=tuple(theme.text_rgba), font=value_font)
            suffix = _metric_suffix(widget, theme)
            if suffix:
                value_bbox = draw.textbbox(
                    (value_x, value_y), value_text, font=value_font, anchor="la")
                suffix_x = value_bbox[2] + _scale_x(scale, 6)
                suffix_bbox_origin = draw.textbbox(
                    (0, 0), suffix, font=unit_font, anchor="la")
                value_bbox_origin = draw.textbbox(
                    (0, 0), value_text, font=value_font, anchor="la")
                suffix_y = value_y + \
                    (value_bbox_origin[3] - suffix_bbox_origin[3])
                draw.text((suffix_x, suffix_y), suffix, fill=tuple(
                    theme.text_rgba), anchor="la", font=unit_font)
        return

    # Non-compact variant
    if _widget_panel_enabled(widget):
        draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(
            scale, 18), fill=(6, 10, 18, 120))
    value_text = _metric_value(widget, hud_value, elapsed_seconds)

    if align == "right":
        # Right-aligned: label and value on right side
        value_right = right - _scale_x(scale, 16)
        value_y = top + _scale_y(scale, 48)
        draw.text((value_right, top + _scale_y(scale, 16)), label,
                  fill=tuple(theme.text_rgba), anchor="ra", font=title_font)
        draw.text((value_right, value_y), value_text, fill=tuple(
            theme.text_rgba), anchor="ra", font=value_font)
        suffix = _metric_suffix(widget, theme)
        if suffix:
            value_bbox = draw.textbbox(
                (value_right, value_y), value_text, font=value_font, anchor="ra")
            suffix_x = value_bbox[2] + _scale_x(scale, 6)
            suffix_bbox_origin = draw.textbbox(
                (0, 0), suffix, font=unit_font, anchor="la")
            value_bbox_origin = draw.textbbox(
                (0, 0), value_text, font=value_font, anchor="ra")
            suffix_y = value_y + (value_bbox_origin[3] - suffix_bbox_origin[3])
            draw.text((suffix_x, suffix_y), suffix, fill=tuple(
                theme.text_rgba), anchor="la", font=unit_font)
    else:
        # Left-aligned: label and value on left side (default)
        value_x = left + _scale_x(scale, 16)
        value_y = top + _scale_y(scale, 48)
        draw.text((value_x, top + _scale_y(scale, 16)), label,
                  fill=tuple(theme.text_rgba), font=title_font)
        draw.text((value_x, value_y), value_text,
                  fill=tuple(theme.text_rgba), font=value_font)
        suffix = _metric_suffix(widget, theme)
        if suffix:
            value_bbox = draw.textbbox(
                (value_x, value_y), value_text, font=value_font, anchor="la")
            suffix_x = value_bbox[2] + _scale_x(scale, 6)
            suffix_bbox_origin = draw.textbbox(
                (0, 0), suffix, font=unit_font, anchor="la")
            value_bbox_origin = draw.textbbox(
                (0, 0), value_text, font=value_font, anchor="la")
            suffix_y = value_y + (value_bbox_origin[3] - suffix_bbox_origin[3])
            draw.text((suffix_x, suffix_y), suffix, fill=tuple(
                theme.text_rgba), anchor="la", font=unit_font)


def _draw_speed_gauge_metric_card(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)

    if _widget_panel_enabled(widget):
        draw.rounded_rectangle(
            (left, top, right, bottom),
            radius=_scale_draw(scale, 24),
            fill=(6, 10, 18, 156),
        )

    padding_x = _scale_x(scale, 10)
    padding_y = _scale_y(scale, 8)
    gauge_left = left + padding_x
    gauge_top = top + padding_y
    gauge_right = right - padding_x
    gauge_bottom = bottom - padding_y

    draw.ellipse(
        (gauge_left, gauge_top, gauge_right, gauge_bottom),
        fill=(10, 14, 22, 148),
        outline=(168, 174, 182, 255),
        width=_scale_draw(scale, 3),
    )

    arc_inset = _scale_draw(scale, 12)
    arc_bounds = (
        gauge_left + arc_inset,
        gauge_top + arc_inset,
        gauge_right - arc_inset,
        gauge_bottom - arc_inset,
    )
    arc_width = _scale_draw(scale, 7)
    arc_start = 130.0
    arc_sweep = 270.0
    arc_end = arc_start + arc_sweep

    draw.arc(
        arc_bounds,
        start=arc_start,
        end=arc_end,
        fill=(88, 95, 108, 255),
        width=arc_width,
    )

    progress = _speed_gauge_progress(hud_value)
    segments = (
        (0.00, 0.42, (77, 221, 92, 255)),
        (0.42, 0.66, (193, 181, 39, 255)),
        (0.66, 0.84, (194, 121, 28, 255)),
        (0.84, 1.00, (174, 35, 31, 255)),
    )
    for start_ratio, end_ratio, color in segments:
        if progress <= start_ratio:
            continue
        segment_end_ratio = min(progress, end_ratio)
        draw.arc(
            arc_bounds,
            start=arc_start + arc_sweep * start_ratio,
            end=arc_start + arc_sweep * segment_end_ratio,
            fill=color,
            width=arc_width,
        )

    marker_angle = arc_start + arc_sweep * progress
    marker_radius = max((arc_bounds[2] - arc_bounds[0]) / 2 + _scale_draw(scale, 3), 1)
    center_x = (arc_bounds[0] + arc_bounds[2]) / 2
    center_y = (arc_bounds[1] + arc_bounds[3]) / 2
    marker_theta = math.radians(marker_angle)
    marker_outer = (
        center_x + math.cos(marker_theta) * marker_radius,
        center_y + math.sin(marker_theta) * marker_radius,
    )
    marker_inner = (
        center_x + math.cos(marker_theta) * (marker_radius - _scale_draw(scale, 24)),
        center_y + math.sin(marker_theta) * (marker_radius - _scale_draw(scale, 24)),
    )
    marker_perp = (-math.sin(marker_theta), math.cos(marker_theta))
    marker_half_width = _scale_draw(scale, 7)
    draw.polygon(
        (
            marker_outer,
            (
                marker_inner[0] + marker_perp[0] * marker_half_width,
                marker_inner[1] + marker_perp[1] * marker_half_width,
            ),
            (
                marker_inner[0] - marker_perp[0] * marker_half_width,
                marker_inner[1] - marker_perp[1] * marker_half_width,
            ),
        ),
        fill=(230, 230, 230, 255),
    )

    value_text = _speed_gauge_value_text(hud_value)
    draw.text(
        (left + w * 0.46, top + h * 0.50),
        value_text,
        fill=tuple(theme.text_rgba),
        anchor="mm",
        font=value_font,
    )

    if _style_bool(widget, "show_unit", theme.show_units):
        draw.text(
            (left + w * 0.63, top + h * 0.72),
            "KM/H",
            fill=tuple(theme.text_rgba),
            anchor="mm",
            font=unit_font,
        )


def _draw_context_card(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    timestamp: datetime,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    left, top = _resolve_widget_origin(
        widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    title_font = _title_font(widget, theme, scale)
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    if _widget_panel_enabled(widget):
        draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(
            scale, 22), fill=(6, 10, 18, 120))
    context_timestamp = timestamp if timestamp.tzinfo is None else timestamp.astimezone(
        timestamp.tzinfo)
    if _is_compact_context_variant(widget):
        draw.text(
            (left + _scale_x(scale, 20), top + _scale_y(scale, 20)),
            _format_context_timestamp(widget, context_timestamp),
            fill=tuple(theme.text_rgba),
            font=value_font,
        )
        return
    draw.text(
        (left + _scale_x(scale, 20), top + _scale_y(scale, 20)),
        str(widget.style.get("label", "Context")),
        fill=tuple(theme.text_rgba),
        font=title_font,
    )
    draw.text(
        (left + _scale_x(scale, 20), top + _scale_y(scale, 70)),
        context_timestamp.strftime("%H:%M"),
        fill=tuple(theme.text_rgba),
        font=value_font,
    )
    draw.text(
        (left + _scale_x(scale, 20), top + _scale_y(scale, 122)),
        context_timestamp.strftime("%Y.%m.%d"),
        fill=tuple(theme.text_rgba),
        font=unit_font,
    )
    draw.text(
        (left + _scale_x(scale, 140), top + _scale_y(scale, 70)),
        theme.note_text,
        fill=tuple(theme.text_rgba),
        font=unit_font,
    )


def _draw_lap_waterfall(
    image: Image.Image,
    widget: HudWidgetConfig,
    lap_state: LapWaterfallState | None,
    theme: HudThemeConfig,
    frame_width: int,
    frame_height: int,
    scale: RenderScale,
) -> None:
    if lap_state is None:
        return
    always_show = widget.style.get("always_show", False)
    opacity = 1.0 if always_show else lap_state.opacity
    if opacity <= 0:
        return

    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    widget_image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    widget_draw = ImageDraw.Draw(widget_image)

    title_font = _title_font(widget, theme, scale)
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    header_color = tuple(theme.text_rgba)
    row_color = tuple(theme.text_rgba)
    transition_rows = None
    transition_progress = 1.0
    if (
        lap_state.transition_previous_rows is not None
        and len(lap_state.transition_previous_rows) == len(lap_state.visible_rows)
        and 0.0 <= lap_state.transition_progress < 1.0
    ):
        transition_rows = lap_state.transition_previous_rows
        transition_progress = max(0.0, min(lap_state.transition_progress, 1.0))

    columns = _lap_waterfall_columns(widget)
    pad_x = _scale_x(scale, 10)
    pad_y = _scale_y(scale, 8)
    content_width = max(w - (pad_x * 2), _scale_x(scale, 24))
    col_widths = _lap_waterfall_column_widths(columns, content_width, scale)

    header_text_h = max(
        _lap_waterfall_text_height(widget_draw, _LAP_WATERFALL_COLUMN_LABELS.get(col, col), title_font)
        for col in columns
    )
    row_text_h = max(
        _lap_waterfall_text_height(widget_draw, _LAP_WATERFALL_COLUMN_MEASURE_SAMPLES.get(col, "00"), value_font)
        for col in columns
    )
    configured_visible_rows = widget.style.get("visible_rows", LAP_WATERFALL_DEFAULT_VISIBLE_ROWS)
    if isinstance(configured_visible_rows, bool) or not isinstance(configured_visible_rows, int) or configured_visible_rows < 1:
        configured_visible_rows = LAP_WATERFALL_DEFAULT_VISIBLE_ROWS
    visible_row_slots = max(configured_visible_rows, 1)
    available_rows_height = max(h - (pad_y * 2) - header_text_h - _scale_y(scale, 6), row_text_h)
    row_h = max(available_rows_height // visible_row_slots, row_text_h)
    header_y = pad_y
    first_row_y = header_y + header_text_h + _scale_y(scale, 6)

    # Header row
    x = pad_x
    for col, cw in zip(columns, col_widths):
        label = _LAP_WATERFALL_COLUMN_LABELS.get(col, col)
        _draw_lap_waterfall_cell(
            widget_image,
            left=x,
            top=header_y,
            width=cw,
            height=header_text_h,
            text=label,
            fill=header_color,
            font=title_font,
        )
        x += cw

    # Data rows
    dimmed_alpha = round(255 * 0.65)

    def draw_row(row: LapWaterfallRow, y: int, *, alpha: int, highlight_strength: float = 0.0) -> None:
        if highlight_strength > 0.0 and lap_state.newest_lap_index == row.lap_index:
            row_bounds = _lap_waterfall_row_text_bounds(
                row,
                columns,
                col_widths,
                left=pad_x,
                top=y,
                value_font=value_font,
                unit_font=unit_font,
                scale=scale,
                gap=_scale_x(scale, 6),
            )
            _draw_lap_waterfall_row_highlight(
                widget_draw,
                left=row_bounds[0],
                top=row_bounds[1],
                right=row_bounds[2],
                bottom=row_bounds[3],
                scale=scale,
                intensity=highlight_strength,
            )
        color = (row_color[0], row_color[1], row_color[2], alpha)
        values = _lap_waterfall_row_values(row, columns)
        x = pad_x
        for val, cw in zip(values, col_widths):
            _draw_lap_waterfall_cell(
                widget_image,
                left=x,
                top=y,
                width=cw,
                height=row_h,
                text=val,
                fill=color,
                font=value_font,
                unit_font=unit_font,
                gap=_scale_x(scale, 6),
            )
            x += cw

    if transition_rows is not None:
        for i, row in enumerate(transition_rows):
            y = first_row_y + int(round((i - transition_progress) * row_h))
            alpha = dimmed_alpha if row.is_dimmed or i <= 1 else 255
            draw_row(row, y, alpha=alpha)

        new_row = lap_state.visible_rows[-1]
        y = first_row_y + int(round((len(transition_rows) - transition_progress) * row_h))
        alpha = dimmed_alpha if new_row.is_dimmed else 255
        draw_row(new_row, y, alpha=alpha, highlight_strength=1.0)
    else:
        for i, row in enumerate(lap_state.visible_rows):
            y = first_row_y + i * row_h
            if lap_state.transition_progress < 1.0 and lap_state.newest_lap_index == row.lap_index:
                y += int(round((1.0 - lap_state.transition_progress) * row_h))
            alpha = dimmed_alpha if row.is_dimmed else 255
            highlight_strength = 0.0
            if lap_state.newest_lap_index == row.lap_index:
                highlight_strength = max(0.35, 1.0 - lap_state.transition_progress)
            draw_row(row, y, alpha=alpha, highlight_strength=highlight_strength)

    # Apply overall widget opacity
    if opacity < 1.0:
        r, g, b, a = widget_image.split()
        a = a.point(lambda v: round(v * opacity))
        widget_image = Image.merge("RGBA", (r, g, b, a))

    image.alpha_composite(widget_image, (left, top))


_LAP_WATERFALL_COLUMN_LABELS: dict[str, str] = {
    "lap": "Lap",
    "distance": "Distance",
    "time": "Time",
    "pace": "Pace",
    "elevation": "Elev",
    "heart_rate": "HR",
}

_LAP_WATERFALL_COLUMN_WEIGHTS: dict[str, float] = {
    "lap": 0.8,
    "distance": 1.6,
    "time": 1.0,
    "pace": 1.5,
    "elevation": 1.0,
    "heart_rate": 1.1,
}

_LAP_WATERFALL_COLUMN_MEASURE_SAMPLES: dict[str, str] = {
    "lap": "99",
    "distance": "00.00 km",
    "time": "00:00",
    "pace": "00:00 /km",
    "elevation": "+999m",
    "heart_rate": "999 bpm",
}

_LAP_WATERFALL_COLUMN_STYLE_KEYS: dict[str, str] = {
    "distance": "show_distance",
    "time": "show_time",
    "pace": "show_pace",
    "elevation": "show_elevation",
    "heart_rate": "show_heart_rate",
}


def _lap_waterfall_columns(widget: HudWidgetConfig) -> list[str]:
    cols = ["lap"]
    for col in ("distance", "time", "pace", "elevation", "heart_rate"):
        style_key = _LAP_WATERFALL_COLUMN_STYLE_KEYS[col]
        if widget.style.get(style_key, True):
            cols.append(col)
    return cols


def _lap_waterfall_column_widths(columns: list[str], total_width: int, scale: RenderScale) -> list[int]:
    if not columns:
        return []
    total_weight = sum(_LAP_WATERFALL_COLUMN_WEIGHTS.get(col, 1.0) for col in columns)
    widths: list[int] = []
    remaining_width = max(total_width, len(columns))
    remaining_weight = total_weight
    for index, col in enumerate(columns):
        if index == len(columns) - 1:
            widths.append(remaining_width)
            continue
        weight = _LAP_WATERFALL_COLUMN_WEIGHTS.get(col, 1.0)
        width = int(round(remaining_width * (weight / remaining_weight)))
        remaining_columns = len(columns) - index - 1
        width = max(width, 1)
        width = min(width, remaining_width - remaining_columns)
        widths.append(width)
        remaining_width -= width
        remaining_weight -= weight
    return widths


def _lap_waterfall_row_values(row: LapWaterfallRow, columns: list[str]) -> list[str]:
    lap = row.lap
    values: list[str] = []
    for col in columns:
        if col == "lap":
            values.append(str(row.lap_index + 1))
        elif col == "distance":
            values.append(f"{lap.distance_m / 1000:.2f} km")
        elif col == "time":
            t = max(int(round(lap.total_time_seconds)), 0)
            values.append(f"{t // 60}:{t % 60:02d}")
        elif col == "pace":
            if lap.distance_m > 0:
                pace = (lap.total_time_seconds / lap.distance_m) * 1000
                values.append(f"{_format_pace(pace)} /km")
            else:
                values.append("--")
        elif col == "elevation":
            elev = lap.elevation_delta_m
            if elev is None:
                values.append("--")
            else:
                sign = "+" if elev >= 0 else ""
                values.append(f"{sign}{round(elev)}m")
        elif col == "heart_rate":
            hr = lap.avg_heart_rate_bpm
            values.append(f"{round(hr)} bpm" if hr is not None else "--")
        else:
            values.append("--")
    return values


def _draw_lap_waterfall_cell(
    image: Image.Image,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    text: str,
    fill: tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont,
    unit_font: ImageFont.FreeTypeFont | None = None,
    gap: int = 0,
) -> None:
    if width <= 0 or height <= 0 or not text:
        return
    cell_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cell_draw = ImageDraw.Draw(cell_image)

    if unit_font is None:
        bbox = cell_draw.textbbox((0, 0), text, font=font)
        cell_draw.text((-bbox[0], -bbox[1]), text, fill=fill, font=font)
        _alpha_composite_clipped(image, cell_image, left, top)
        return

    try:
        transparent_fill = (fill[0], fill[1], fill[2], 0)
    except Exception:
        transparent_fill = (0, 0, 0, 0)
    bbox = cell_draw.textbbox((0, 0), text, font=font)
    cell_draw.text((-bbox[0], -bbox[1]), text, fill=transparent_fill, font=font)

    if " " in text:
        value_text, unit_text = text.rsplit(" ", 1)
    else:
        i = len(text) - 1
        while i >= 0 and (text[i].isalpha() or text[i] in ("/", "%")):
            i -= 1
        if i == len(text) - 1:
            cell_draw.text((-bbox[0], -bbox[1]), text, fill=fill, font=font)
            _alpha_composite_clipped(image, cell_image, left, top)
            return
        value_text = text[: i + 1]
        unit_text = text[i + 1 :]

    value_bbox = cell_draw.textbbox((0, 0), value_text, font=font)
    unit_bbox = cell_draw.textbbox((0, 0), unit_text, font=unit_font)

    value_x = -value_bbox[0]
    value_y = -value_bbox[1]
    cell_draw.text((value_x, value_y), value_text, fill=fill, font=font)

    value_width = value_bbox[2] - value_bbox[0]
    unit_x = value_x + value_width + gap
    unit_y = value_y + (value_bbox[3] - unit_bbox[3])
    cell_draw.text((unit_x, unit_y), unit_text, fill=fill, font=unit_font)
    _alpha_composite_clipped(image, cell_image, left, top)


def _lap_waterfall_row_text_bounds(
    row: LapWaterfallRow,
    columns: list[str],
    col_widths: list[int],
    *,
    left: int,
    top: int,
    value_font: ImageFont.FreeTypeFont,
    unit_font: ImageFont.FreeTypeFont,
    scale: RenderScale,
    gap: int,
) -> tuple[int, int, int, int]:
    scratch = ImageDraw.Draw(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
    values = _lap_waterfall_row_values(row, columns)
    x = left
    left_bound: int | None = None
    top_bound: int | None = None
    right_bound: int | None = None
    bottom_bound: int | None = None
    for val, cw in zip(values, col_widths):
        cell_bounds = _lap_waterfall_cell_text_bounds(scratch, val, value_font, unit_font, gap)
        cell_left = x + cell_bounds[0]
        cell_top = top + cell_bounds[1]
        cell_right = x + cell_bounds[2]
        cell_bottom = top + cell_bounds[3]
        left_bound = cell_left if left_bound is None else min(left_bound, cell_left)
        top_bound = cell_top if top_bound is None else min(top_bound, cell_top)
        right_bound = cell_right if right_bound is None else max(right_bound, cell_right)
        bottom_bound = cell_bottom if bottom_bound is None else max(bottom_bound, cell_bottom)
        x += cw
    if left_bound is None or top_bound is None or right_bound is None or bottom_bound is None:
        return (left, top, left, top)
    pad = _scale_draw(scale, 2)
    return (left_bound - pad, top_bound - pad, right_bound + pad, bottom_bound + pad)


def _lap_waterfall_cell_text_bounds(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    unit_font: ImageFont.FreeTypeFont,
    gap: int,
) -> tuple[int, int, int, int]:
    if " " in text:
        value_text, unit_text = text.rsplit(" ", 1)
    else:
        i = len(text) - 1
        while i >= 0 and (text[i].isalpha() or text[i] in ("/", "%")):
            i -= 1
        if i == len(text) - 1:
            return draw.textbbox((0, 0), text, font=font)
        value_text = text[: i + 1]
        unit_text = text[i + 1 :]

    value_bbox = draw.textbbox((0, 0), value_text, font=font)
    unit_bbox = draw.textbbox((0, 0), unit_text, font=unit_font)
    value_x = -value_bbox[0]
    value_y = -value_bbox[1]
    unit_x = value_x + (value_bbox[2] - value_bbox[0]) + gap
    unit_y = value_y + (value_bbox[3] - unit_bbox[3])
    left = min(value_x + value_bbox[0], unit_x + unit_bbox[0])
    top = min(value_y + value_bbox[1], unit_y + unit_bbox[1])
    right = max(value_x + value_bbox[2], unit_x + unit_bbox[2])
    bottom = max(value_y + value_bbox[3], unit_y + unit_bbox[3])
    return (left, top, right, bottom)


def _draw_lap_waterfall_row_highlight(
    draw: ImageDraw.ImageDraw,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    scale: RenderScale,
    intensity: float,
) -> None:
    intensity = max(0.0, min(intensity, 1.0))
    if right <= left or bottom <= top or intensity <= 0.0:
        return
    glow = (
        LAP_WATERFALL_LATEST_GLOW_RGBA[0],
        LAP_WATERFALL_LATEST_GLOW_RGBA[1],
        LAP_WATERFALL_LATEST_GLOW_RGBA[2],
        int(round(LAP_WATERFALL_LATEST_GLOW_RGBA[3] * (0.5 + 0.5 * intensity))),
    )
    fill = (
        LAP_WATERFALL_LATEST_FILL_RGBA[0],
        LAP_WATERFALL_LATEST_FILL_RGBA[1],
        LAP_WATERFALL_LATEST_FILL_RGBA[2],
        int(round(LAP_WATERFALL_LATEST_FILL_RGBA[3] * (0.45 + 0.55 * intensity))),
    )
    outline = (
        LAP_WATERFALL_LATEST_OUTLINE_RGBA[0],
        LAP_WATERFALL_LATEST_OUTLINE_RGBA[1],
        LAP_WATERFALL_LATEST_OUTLINE_RGBA[2],
        int(round(LAP_WATERFALL_LATEST_OUTLINE_RGBA[3] * (0.35 + 0.65 * intensity))),
    )
    glow_inset = _scale_x(scale, 1)
    inset_x = _scale_x(scale, 2)
    inset_y = _scale_y(scale, 2)
    radius = _scale_draw(scale, 9)
    draw.rounded_rectangle(
        (left - glow_inset, top - glow_inset, right + glow_inset, bottom + glow_inset),
        radius=radius,
        fill=glow,
    )
    draw.rounded_rectangle(
        (left - inset_x, top - inset_y, right + inset_x, bottom + inset_y),
        radius=radius,
        fill=fill,
        outline=outline,
        width=_scale_draw(scale, 1),
    )


def _alpha_composite_clipped(image: Image.Image, overlay: Image.Image, left: int, top: int) -> None:
    if overlay.width <= 0 or overlay.height <= 0:
        return
    target_left = max(left, 0)
    target_top = max(top, 0)
    target_right = min(left + overlay.width, image.width)
    target_bottom = min(top + overlay.height, image.height)
    if target_right <= target_left or target_bottom <= target_top:
        return
    crop = overlay.crop(
        (
            target_left - left,
            target_top - top,
            target_right - left,
            target_bottom - top,
        )
    )
    image.alpha_composite(crop, (target_left, target_top))


def _lap_waterfall_text_height(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return max(bbox[3] - bbox[1], 1)


def _draw_legacy_route_map(draw: ImageDraw.ImageDraw, route_points: list[tuple[float, float]], map_box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = map_box
    draw.rounded_rectangle(map_box, radius=16, fill=(
        0, 0, 0, 120), outline=(255, 255, 255, 180))
    if len(route_points) < 2:
        return

    lat_min, lat_max, lon_min, lon_max, projection_scale, offset_x, offset_y = _route_map_projection_bounds(
        route_points,
        left + 12,
        top + 12,
        right - 12,
        bottom - 12,
        100,
    )

    def project(point: tuple[float, float]) -> tuple[float, float]:
        lat, lon = point
        return (
            offset_x + ((lon - lon_min) * projection_scale),
            offset_y + ((lat_max - lat) * projection_scale),
        )

    projected = [project(point) for point in route_points]
    draw.line(projected, fill=(0, 200, 255, 255), width=4)
    x, y = projected[-1]
    draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 90, 90, 255))


def _stride_length_m(hud_value: HudSample) -> float | None:
    if hud_value.speed_mps is None or hud_value.cadence_spm is None or hud_value.cadence_spm <= 0:
        return None
    return (hud_value.speed_mps * 60.0) / hud_value.cadence_spm


def _metric_value(widget: HudWidgetConfig, hud_value: HudSample, elapsed_seconds: int) -> str:
    binding = _require_supported_binding(widget, {
                                         "pace_seconds_per_km", "heart_rate_bpm", "cadence_spm", "elapsed_seconds", "speed_mps", "stride_length_m"})
    if binding == "pace_seconds_per_km":
        return _format_pace(hud_value.pace_seconds_per_km)
    if binding == "heart_rate_bpm":
        return "--" if hud_value.heart_rate_bpm is None else str(hud_value.heart_rate_bpm)
    if binding == "cadence_spm":
        return "--" if hud_value.cadence_spm is None else str(hud_value.cadence_spm)
    if binding == "stride_length_m":
        stride_length_m = _stride_length_m(hud_value)
        return "--" if stride_length_m is None else f"{stride_length_m:.2f}"
    if binding == "elapsed_seconds":
        hours, remainder = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if binding == "speed_mps":
        return "--" if hud_value.speed_mps is None else f"{hud_value.speed_mps * 3.6:.1f}"
    raise AssertionError(f"unreachable metric binding '{binding}'")


def _metric_suffix(widget: HudWidgetConfig, theme: HudThemeConfig) -> str:
    if not _style_bool(widget, "show_unit", theme.show_units):
        return ""
    binding = _require_supported_binding(widget, {
                                         "pace_seconds_per_km", "heart_rate_bpm", "cadence_spm", "elapsed_seconds", "speed_mps", "stride_length_m"})
    if binding == "pace_seconds_per_km":
        return "/km"
    if binding == "heart_rate_bpm":
        return "bpm"
    if binding == "cadence_spm":
        return "SPM"
    if binding == "stride_length_m":
        return "m"
    if binding == "elapsed_seconds":
        return ""
    if binding == "speed_mps":
        return "km/h"
    raise AssertionError(f"unreachable metric binding '{binding}'")


def _speed_gauge_value_text(hud_value: HudSample) -> str:
    if hud_value.speed_mps is None:
        return "--"
    return f"{round(hud_value.speed_mps * 3.6):.0f}"


def _speed_gauge_progress(hud_value: HudSample) -> float:
    if hud_value.speed_mps is None:
        return 0.0
    speed_kmh = hud_value.speed_mps * 3.6
    return min(max(speed_kmh / 30.0, 0.0), 1.0)


def _is_compact_context_variant(widget: HudWidgetConfig) -> bool:
    variant = widget.style.get("variant")
    return isinstance(variant, str) and variant in {"compact", "timestamp_chip"}


def _format_context_timestamp(widget: HudWidgetConfig, timestamp: datetime) -> str:
    timestamp_format = widget.style.get("format", "%Y/%m/%d %H:%M:%S")
    if not isinstance(timestamp_format, str):
        raise ValueError(f"widget '{widget.id}' style.format must be a string")
    return timestamp.strftime(timestamp_format)


def _format_pace(pace_seconds_per_km: float | None) -> str:
    if pace_seconds_per_km is None:
        return "--:--"
    total_seconds = max(int(round(pace_seconds_per_km)), 0)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _resolve_route_projection(route_points: list[tuple[float, float]], hud_value: HudSample) -> RouteProjection | None:
    if hud_value.latitude is None or hud_value.longitude is None:
        return None

    current = (hud_value.latitude, hud_value.longitude)
    closest_point = route_points[-1]
    closest_segment_start = route_points[0]
    closest_segment_end = route_points[1]
    closest_tangent = (0.0, 0.0)
    closest_distance_sq = float("inf")
    segment_index = 0

    for index, (segment_start, segment_end) in enumerate(zip(route_points, route_points[1:])):
        candidate = _project_point_onto_segment(
            current, segment_start, segment_end)
        distance_sq = _distance_squared(current, candidate)
        candidate_tangent = (
            segment_end[0] - segment_start[0], segment_end[1] - segment_start[1])
        if distance_sq < closest_distance_sq or (
            math.isclose(distance_sq, closest_distance_sq, abs_tol=1e-12)
            and _is_zero_vector(closest_tangent)
            and not _is_zero_vector(candidate_tangent)
        ):
            closest_point = candidate
            closest_segment_start = segment_start
            closest_segment_end = segment_end
            closest_tangent = candidate_tangent
            closest_distance_sq = distance_sq
            segment_index = index

    return RouteProjection(
        point=closest_point,
        tangent=closest_tangent,
        segment_start=closest_segment_start,
        segment_end=closest_segment_end,
        segment_index=segment_index,
    )


def _projected_route_vector(
    route_projection: RouteProjection,
    project,
) -> tuple[float, float]:
    start_x, start_y = project(route_projection.segment_start)
    end_x, end_y = project(route_projection.segment_end)
    return (end_x - start_x, end_y - start_y)


def _split_route_points(
    route_points: list[tuple[float, float]],
    route_projection: RouteProjection,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    split_point = route_projection.point
    start_index = route_projection.segment_index
    completed = [*route_points[: start_index + 1], split_point]
    remaining = [split_point, *route_points[start_index + 1 :]]
    return completed, remaining


def _is_zero_vector(vector: tuple[float, float]) -> bool:
    return abs(vector[0]) <= 1e-12 and abs(vector[1]) <= 1e-12


def _format_bearing_label(tangent: tuple[float, float]) -> str:
    bearing = _bearing_from_tangent(tangent)
    if bearing is None:
        return ""
    return f"{bearing:03d}°{_bearing_cardinal(bearing)}"


def _bearing_from_tangent(tangent: tuple[float, float]) -> int | None:
    delta_lat, delta_lon = tangent
    if _is_zero_vector(tangent):
        return None
    return int(round((math.degrees(math.atan2(delta_lon, delta_lat)) + 360.0) % 360.0)) % 360


def _ease_in_out(t: float) -> float:
    return 0.5 * (1 - math.cos(math.pi * t))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_color(c1, c2, t: float):
    return (
        int(_lerp(c1[0], c2[0], t)),
        int(_lerp(c1[1], c2[1], t)),
        int(_lerp(c1[2], c2[2], t)),
        int(_lerp(c1[3], c2[3], t)),
    )


def _pulse_value(
    duration: float = 2.0,
) -> tuple[float, float, float]:
    # During pytest runs, freeze pulse for deterministic renders
    if os.environ.get("PYTEST_CURRENT_TEST") is not None:
        return 1.0, 1.0, 0.0
    phase = (time.monotonic() % duration) / duration
    v = 0.5 * (1 - math.cos(math.pi * phase))

    scale = 0.95 + 0.15 * v
    alpha = 0.80 + 0.20 * v

    return scale, alpha, v


def _bearing_cardinal(bearing: int) -> str:
    cardinals = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return cardinals[int(((bearing + 22.5) % 360) // 45)]


def _draw_position_marker_arrow(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    vector: tuple[float, float],
    scale: RenderScale,
) -> None:
    dx, dy = vector
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        return

    ux = dx / length
    uy = dy / length

    # 垂直方向
    px = -uy
    py = ux

    cx, cy = center

    # 新增动画值
    pulse_scale, pulse_alpha, color_t = _pulse_value()

    def S(v: int) -> float:
        return _scale_draw(scale, v) * pulse_scale

    # ---- 尺寸 ----
    nose_len = _scale_draw(scale, 5)      # 前尖
    wing_len = _scale_draw(scale, 5)      # 左右翼长度
    wing_width = _scale_draw(scale, 5)    # 翼展
    notch_len = _scale_draw(scale, 3.5)      # 中间凹进去的长度

    # 1. 箭头尖
    tip = (
        cx + ux * nose_len,
        cy + uy * nose_len,
    )

    # 2. 左翼
    left = (
        cx - ux * wing_len + px * wing_width,
        cy - uy * wing_len + py * wing_width,
    )

    # 3. 中间内凹点
    notch = (
        cx - ux * notch_len,
        cy - uy * notch_len,
    )

    # 4. 右翼
    right = (
        cx - ux * wing_len - px * wing_width,
        cy - uy * wing_len - py * wing_width,
    )

    arrow_points = (
        tip,
        right,
        notch,
        left,
    )

    fill = _lerp_color(ROUTE_MAP_HEADING_ARROW_RGBA,
                       ROUTE_MAP_HEADING_ARROW_TEAL_RGBA, color_t)
    fill = (
        fill[0],
        fill[1],
        fill[2],
        int(fill[3] * pulse_alpha),
    )

    outline = (
        ROUTE_MAP_HEADING_ARROW_HEAD_RGBA[0],
        ROUTE_MAP_HEADING_ARROW_HEAD_RGBA[1],
        ROUTE_MAP_HEADING_ARROW_HEAD_RGBA[2],
    )

    draw.polygon(
        arrow_points,
        fill=fill,
    )

    draw.polygon(
        arrow_points,
        outline=outline,
        width=_scale_draw(scale, 1),
    )


def _heading_arrow_head_points(
    center: tuple[float, float],
    vector: tuple[float, float],
    scale: RenderScale,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None:
    dx, dy = vector
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        return None
    unit_x = dx / length
    unit_y = dy / length
    center_x, center_y = center
    arrow_length = _scale_draw(scale, 18)
    arrow_width = _scale_draw(scale, 5)
    head_length = _scale_draw(scale, 8)
    tip_x = center_x + (unit_x * arrow_length)
    tip_y = center_y + (unit_y * arrow_length)
    side_x = -unit_y
    side_y = unit_x
    return (
        (tip_x, tip_y),
        (tip_x - (unit_x * head_length) + (side_x * arrow_width),
         tip_y - (unit_y * head_length) + (side_y * arrow_width)),
        (tip_x - (unit_x * head_length) - (side_x * arrow_width),
         tip_y - (unit_y * head_length) - (side_y * arrow_width)),
    )


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
        ((point_lat - start_lat) * delta_lat) +
        ((point_lon - start_lon) * delta_lon)
    ) / segment_length_sq
    clamped_projection = min(max(projection, 0.0), 1.0)
    return (
        start_lat + (delta_lat * clamped_projection),
        start_lon + (delta_lon * clamped_projection),
    )


def _distance_squared(left: tuple[float, float], right: tuple[float, float]) -> float:
    return ((left[0] - right[0]) ** 2) + ((left[1] - right[1]) ** 2)
