import math
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

HUD_REFERENCE_WIDTH = 1280
HUD_REFERENCE_HEIGHT = 720
PROGRESS_BAR_MIN_WIDTH = 232
SUPPORTED_WIDGET_ANCHORS = {"top-left", "top-right", "bottom-left", "bottom-right"}
LEGACY_DEFAULT_FONT_SIZE_PX = 18
ROUTE_MAP_DEFAULT_SHAPE = "circle"
WIDGET_PANEL_RGBA = (12, 18, 28, 168)
ROUTE_MAP_PANEL_RGBA = (6, 10, 18, 148)
ROUTE_MAP_PANEL_OUTLINE_RGBA = (255, 255, 255, 96)
ROUTE_MAP_ROUTE_RGBA = (34, 255, 138, 255)
ROUTE_MAP_MARKER_RGBA = (228, 255, 238, 255)
ROUTE_MAP_HEADING_ARROW_RGBA = (74, 155, 255, 255)
ROUTE_MAP_HEADING_ARROW_HEAD_RGBA = (255, 255, 255, 255)
PROGRESS_BAR_FILL_RGBA = (34, 255, 138, 255)
PROGRESS_BAR_RAIL_RGBA = (8, 12, 20, 220)
PROGRESS_BAR_TICK_RGBA = (230, 238, 245, 168)
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
            font_path = files("race_overlay.assets.fonts").joinpath(font_filename)
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
    validate_hud_theme_config(hud_config.theme)
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
    _validate_widget_core_fields(widget)
    if widget.anchor not in SUPPORTED_WIDGET_ANCHORS:
        supported = ", ".join(sorted(SUPPORTED_WIDGET_ANCHORS))
        raise ValueError(
            f"unsupported anchor '{widget.anchor}' for widget '{widget.id}' of type '{widget.type}'; "
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
        _require_supported_binding(widget, {"altitude_m", "distance_m", "heart_rate_bpm"})
    elif widget.type == "route_map":
        _require_supported_binding(widget, {"route_points"})
        _route_map_shape(widget)  # Validate shape enum
    elif widget.type == "hero_metric":
        _require_supported_binding(widget, {"pace_seconds_per_km"})
    elif widget.type == "metric_card":
        _require_supported_binding(widget, {"pace_seconds_per_km", "heart_rate_bpm", "cadence_spm", "elapsed_seconds", "speed_mps"})
    elif widget.type == "context_card":
        _require_supported_binding(widget, {"timestamp"})
    else:
        raise ValueError(f"unknown widget type '{widget.type}' for widget '{widget.id}'")
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
        raise ValueError(f"widget '{widget.id}' {field_name} must be a finite integer")
    if minimum is not None and value < minimum:
        qualifier = f"at least {minimum}" if minimum != 1 else "greater than 0"
        raise ValueError(f"widget '{widget.id}' {field_name} must be {qualifier}")
    return value


def _validate_widget_style(widget: HudWidgetConfig) -> None:
    _validate_optional_enum_style(widget, "font_family", HUD_FONT_FAMILY_OPTIONS)
    _validate_optional_enum_style(widget, "font_weight", HUD_FONT_WEIGHT_OPTIONS)
    _validate_optional_font_size_style(widget, "font_size_px")
    _validate_optional_bool_style(widget, "show_panel")
    _validate_optional_bool_style(widget, "transparent_panel")
    _validate_optional_bool_style(widget, "show_unit")
    _validate_optional_bool_style(widget, "show_current_value")
    _validate_optional_bool_style(widget, "show_total_value")
    _validate_optional_bool_style(widget, "show_north_marker")
    _validate_optional_bool_style(widget, "show_bearing_label")
    _validate_optional_bool_style(widget, "show_heading_arrow")
    _validate_optional_rgba_style(widget, "fill_rgba")
    _validate_optional_rgba_style(widget, "rail_rgba")
    _validate_optional_rgba_style(widget, "tick_rgba")
    _validate_optional_non_negative_int_style(widget, "decimals")
    _validate_optional_text_style(widget, "format")


def _validate_progress_bar_widget(widget: HudWidgetConfig) -> None:
    if widget.width < PROGRESS_BAR_MIN_WIDTH:
        raise ValueError(
            f"progress_bar widget '{widget.id}' requires a minimum width of {PROGRESS_BAR_MIN_WIDTH}px "
            f"(got {widget.width}px)"
        )
    _validate_optional_font_size_style(widget, "current_font_size_px")


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


def _widget_panel_enabled(widget: HudWidgetConfig) -> bool:
    show_panel = widget.style.get("show_panel")
    if isinstance(show_panel, bool):
        return show_panel
    transparent_panel = widget.style.get("transparent_panel")
    if isinstance(transparent_panel, bool):
        return not transparent_panel
    if transparent_panel is not None:
        raise ValueError(f"widget '{widget.id}' style.transparent_panel must be a boolean")
    if show_panel is not None:
        raise ValueError(f"widget '{widget.id}' style.show_panel must be a boolean")
    return widget.type == "route_map"


def _validate_optional_enum_style(widget: HudWidgetConfig, key: str, allowed: tuple[str, ...]) -> None:
    if key not in widget.style:
        return
    value = widget.style[key]
    if not isinstance(value, str) or value not in allowed:
        allowed_values = ", ".join(allowed)
        raise ValueError(f"widget '{widget.id}' style.{key} must be one of: {allowed_values}")


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
        raise ValueError(f"widget '{widget.id}' style.{key} must be an integer")
    if value < 0:
        raise ValueError(f"widget '{widget.id}' style.{key} must be at least 0")


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
    value = widget.style.get("font_size_px", theme.font_size_px or fallback)
    return _require_font_size_style(widget, value, "font_size_px")


def _style_font_family(widget: HudWidgetConfig, theme: HudThemeConfig) -> str:
    value = widget.style.get("font_family", theme.font_family)
    if not isinstance(value, str) or value not in HUD_FONT_FAMILY_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_FAMILY_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.font_family must be one of: {allowed_values}")
    return value


def _require_font_size_style(widget: HudWidgetConfig, value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"widget '{widget.id}' style.{key} must be a number")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"widget '{widget.id}' style.{key} must be a finite integer")
        value = int(value)
    if value < 8:
        raise ValueError(f"widget '{widget.id}' style.{key} must be at least 8")
    return int(value)


def _style_font_weight(widget: HudWidgetConfig, theme: HudThemeConfig) -> str:
    value = widget.style.get("font_weight", theme.font_weight)
    if not isinstance(value, str) or value not in HUD_FONT_WEIGHT_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_WEIGHT_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.font_weight must be one of: {allowed_values}")
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
    family_value = widget.style.get("font_family", _theme_role_value(theme, f"{role}_font_family", "font_family"))
    if not isinstance(family_value, str) or family_value not in HUD_FONT_FAMILY_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_FAMILY_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.font_family must be one of: {allowed_values}")

    weight_value = widget.style.get("font_weight", _theme_role_value(theme, f"{role}_font_weight", "font_weight"))
    if not isinstance(weight_value, str) or weight_value not in HUD_FONT_WEIGHT_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_WEIGHT_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.font_weight must be one of: {allowed_values}")

    size_value = widget.style.get("font_size_px", _theme_role_value(theme, f"{role}_font_size_px", "font_size_px"))
    size = _require_font_size_style(widget, size_value, "font_size_px")
    return _scaled_font(scale, size, family_value, weight_value)


def _progress_bar_value_font(
    widget: HudWidgetConfig,
    theme: HudThemeConfig,
    scale: RenderScale,
    *,
    current: bool = False,
) -> ImageFont.FreeTypeFont:
    family_value = widget.style.get("font_family", _theme_role_value(theme, "value_font_family", "font_family"))
    if not isinstance(family_value, str) or family_value not in HUD_FONT_FAMILY_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_FAMILY_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.font_family must be one of: {allowed_values}")

    weight_value = widget.style.get("font_weight", _theme_role_value(theme, "value_font_weight", "font_weight"))
    if not isinstance(weight_value, str) or weight_value not in HUD_FONT_WEIGHT_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_WEIGHT_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.font_weight must be one of: {allowed_values}")

    if current:
        size_value = widget.style.get("current_font_size_px")
        if size_value is None:
            size_value = widget.style.get("font_size_px", _theme_role_value(theme, "value_font_size_px", "font_size_px"))
            size = max(_require_font_size_style(widget, size_value, "font_size_px") - 2, 8)
        else:
            size = _require_font_size_style(widget, size_value, "current_font_size_px")
    else:
        size_value = widget.style.get("font_size_px", _theme_role_value(theme, "value_font_size_px", "font_size_px"))
        size = _require_font_size_style(widget, size_value, "font_size_px")
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
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    title_font = _title_font(widget, theme, scale)
    current_font = _progress_bar_value_font(widget, theme, scale, current=True)
    total_font = _progress_bar_value_font(widget, theme, scale, current=False)
    if _widget_panel_enabled(widget):
        draw.rounded_rectangle((left, top, left + w, top + h), radius=_scale_draw(scale, 18), fill=(6, 10, 18, 120))
    text_layout = _progress_bar_text_layout(left, top, w, h, str(widget.style.get("label", "")))
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
    draw.rounded_rectangle((track_left, track_top, track_right, track_bottom), radius=rail_radius, fill=rail_rgba)
    draw.line((track_left, track_y, track_right, track_y), fill=rail_rgba, width=_scale_draw(scale, 1))
    progress_value_m = distance_m if distance_m is not None else 0.0
    progress_ratio = min(max(progress_value_m / goal_m, 0.0), 1.0)
    progress_right = track_left + int((track_right - track_left) * progress_ratio)
    fill_top = track_top + _scale_y(scale, 3)
    fill_bottom = track_bottom - _scale_y(scale, 3)
    fill_radius = max((fill_bottom - fill_top) // 2, _scale_draw(scale, 4))
    if progress_right > track_left:
        draw.rounded_rectangle(
            (track_left, fill_top, max(progress_right, track_left + fill_radius * 2), fill_bottom),
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
            tick_height = max(track_bottom - track_top - _scale_y(scale, 4), _scale_draw(scale, 6))
        draw.line((x, track_y - tick_height // 2, x, track_y + tick_height // 2), fill=tick_rgba, width=_scale_draw(scale, 1))

    text_y = top + _scale_y(scale, 10)
    text_x = track_left
    if label:
        draw.text((text_x, text_y), label, fill=tuple(theme.text_rgba), font=title_font)
        label_box = draw.textbbox((text_x, text_y), label, font=title_font)
        text_x = label_box[2] + _scale_x(scale, 10)
    if show_current_value:
        current_text = _distance_label(progress_value_m, show_units)
        current_box = draw.textbbox((0, 0), current_text, font=current_font)
        current_text_width = current_box[2] - current_box[0]
        current_text_x = max(track_left, progress_right - current_text_width - _scale_x(scale, 8))
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
    binding = _require_supported_binding(widget, {"altitude_m", "distance_m", "heart_rate_bpm"})
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    if _widget_panel_enabled(widget):
        draw.rounded_rectangle(
            (left, top, left + w, top + h),
            radius=_scale_draw(scale, 20),
            fill=(6, 10, 18, 120),
        )
    title_font = _title_font(widget, theme, scale)
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    label = str(widget.style.get("label", "Metric"))
    unit = str(widget.style.get("unit", "")) if _style_bool(widget, "show_unit", theme.show_units) else ""
    align = str(widget.style.get("align", "left"))
    value_text = _stat_block_value(binding, hud_value, decimals=int(widget.style.get("decimals", 0)))
    if align == "right":
        value_right = left + w - _scale_x(scale, 12)
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
            value_bbox = draw.textbbox((value_right, value_y), value_text, font=value_font, anchor="ra")
            unit_x = value_bbox[2] + _scale_x(scale, 6)
            unit_bbox_origin = draw.textbbox((0, 0), unit, font=unit_font, anchor="la")
            value_bbox_origin = draw.textbbox((0, 0), value_text, font=value_font, anchor="ra")
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
    draw.text((value_x, top + _scale_y(scale, 12)), label, fill=tuple(theme.text_rgba), font=title_font)
    draw.text((value_x, value_y), value_text, fill=tuple(theme.text_rgba), font=value_font)
    if unit:
        value_bbox = draw.textbbox((value_x, value_y), value_text, font=value_font, anchor="la")
        unit_x = value_bbox[2] + _scale_x(scale, 6)
        unit_bbox_origin = draw.textbbox((0, 0), unit, font=unit_font, anchor="la")
        value_bbox_origin = draw.textbbox((0, 0), value_text, font=value_font, anchor="la")
        unit_y = value_y + (value_bbox_origin[3] - unit_bbox_origin[3])
        draw.text((unit_x, unit_y), unit, fill=tuple(theme.text_rgba), anchor="la", font=unit_font)


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
    shape = str(widget.style.get("shape", ROUTE_MAP_DEFAULT_SHAPE))
    background_rgba = _style_rgba(widget, "background_rgba", ROUTE_MAP_PANEL_RGBA)
    widget_image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    widget_draw = ImageDraw.Draw(widget_image)
    if shape == "circle":
        if _widget_panel_enabled(widget):
            widget_draw.ellipse((0, 0, w, h), fill=background_rgba, outline=ROUTE_MAP_PANEL_OUTLINE_RGBA)
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
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    if label:
        widget_draw.text((_scale_x(scale, 12), _scale_y(scale, 10)), label, fill=tuple(theme.text_rgba), font=title_font)
    if len(route_points) < 2:
        image.alpha_composite(widget_image, (left, top))
        return

    show_north_marker = _style_bool(widget, "show_north_marker", True)
    show_bearing_label = _style_bool(widget, "show_bearing_label", True)
    show_heading_arrow = _style_bool(widget, "show_heading_arrow", True)
    route_projection = _resolve_route_projection(route_points, hud_value)
    bearing_label = ""
    if route_projection is not None and show_bearing_label:
        bearing_label = _format_bearing_label(route_projection.tangent)
    show_top_overlays = label or show_north_marker
    show_bottom_overlay = bool(bearing_label)
    map_left = _scale_x(scale, 12)
    map_top = _scale_y(scale, 36) if show_top_overlays else _scale_y(scale, 12)
    map_bottom = h - (_scale_y(scale, 18) if show_bottom_overlay else _scale_y(scale, 12))
    inner_width = max(w - _scale_x(scale, 24), 1)
    inner_height = max(map_bottom - map_top, 1)
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
    widget_draw.line(projected, fill=ROUTE_MAP_ROUTE_RGBA, width=_scale_draw(scale, 4))
    if show_north_marker:
        widget_draw.text((w / 2, _scale_y(scale, 10)), "N", fill=tuple(theme.text_rgba), anchor="ma", font=unit_font)
    if route_projection is not None:
        if bearing_label:
            widget_draw.text(
                (w / 2, h - _scale_y(scale, 10)),
                bearing_label,
                fill=tuple(theme.text_rgba),
                anchor="ms",
                font=unit_font,
            )
        x, y = project(route_projection.point)
        r = _scale_draw(scale, 7)
        widget_draw.ellipse(
            (x - r, y - r, x + r, y + r),
            fill=ROUTE_MAP_MARKER_RGBA,
            outline=ROUTE_MAP_ROUTE_RGBA,
            width=_scale_draw(scale, 2),
        )
        if show_heading_arrow:
            heading_vector = _projected_route_vector(route_projection, project)
            _draw_heading_arrow(
                widget_draw,
                (x, y),
                heading_vector,
                scale,
                arrow_rgba=ROUTE_MAP_HEADING_ARROW_RGBA,
            )
            arrow_head = _heading_arrow_head_points((x, y), heading_vector, scale)
            if arrow_head is not None:
                widget_draw.polygon(arrow_head, fill=ROUTE_MAP_HEADING_ARROW_HEAD_RGBA)

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
    title_font = _title_font(widget, theme, scale)
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    if _widget_panel_enabled(widget):
        draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(scale, 22), fill=(6, 10, 18, 120))
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
            fill=(255, 255, 255, 160),
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
    left, top = _resolve_widget_origin(widget, frame_width, frame_height, scale)
    w = _scale_x(scale, widget.width)
    h = _scale_y(scale, widget.height)
    right, bottom = left + w, top + h
    title_font = _title_font(widget, theme, scale)
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    label = str(widget.style.get("label", "Metric"))
    align = str(widget.style.get("align", "left"))
    
    if widget.style.get("variant") == "compact":
        if _widget_panel_enabled(widget):
            draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(scale, 20), fill=(6, 10, 18, 120))
        value_text = _metric_value(widget, hud_value, elapsed_seconds)
        
        if align == "right":
            # Right-aligned: label and value on right side
            value_right = right - _scale_x(scale, 12)
            value_y = top + _scale_y(scale, 30)
            draw.text((value_right, top + _scale_y(scale, 12)), label, fill=tuple(theme.text_rgba), anchor="ra", font=title_font)
            draw.text((value_right, value_y), value_text, fill=tuple(theme.text_rgba), anchor="ra", font=value_font)
            suffix = _metric_suffix(widget, theme)
            if suffix:
                value_bbox = draw.textbbox((value_right, value_y), value_text, font=value_font, anchor="ra")
                suffix_x = value_bbox[2] + _scale_x(scale, 6)
                suffix_bbox_origin = draw.textbbox((0, 0), suffix, font=unit_font, anchor="la")
                value_bbox_origin = draw.textbbox((0, 0), value_text, font=value_font, anchor="ra")
                suffix_y = value_y + (value_bbox_origin[3] - suffix_bbox_origin[3])
                draw.text((suffix_x, suffix_y), suffix, fill=(255, 255, 255, 160), anchor="la", font=unit_font)
        else:
            # Left-aligned: label and value on left side (default)
            value_x = left + _scale_x(scale, 12)
            value_y = top + _scale_y(scale, 30)
            draw.text((value_x, top + _scale_y(scale, 12)), label, fill=tuple(theme.text_rgba), font=title_font)
            draw.text((value_x, value_y), value_text, fill=tuple(theme.text_rgba), font=value_font)
            suffix = _metric_suffix(widget, theme)
            if suffix:
                value_bbox = draw.textbbox((value_x, value_y), value_text, font=value_font, anchor="la")
                suffix_x = value_bbox[2] + _scale_x(scale, 6)
                suffix_bbox_origin = draw.textbbox((0, 0), suffix, font=unit_font, anchor="la")
                value_bbox_origin = draw.textbbox((0, 0), value_text, font=value_font, anchor="la")
                suffix_y = value_y + (value_bbox_origin[3] - suffix_bbox_origin[3])
                draw.text((suffix_x, suffix_y), suffix, fill=(255, 255, 255, 160), anchor="la", font=unit_font)
        return

    # Non-compact variant
    if _widget_panel_enabled(widget):
        draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(scale, 18), fill=(6, 10, 18, 120))
    value_text = _metric_value(widget, hud_value, elapsed_seconds)
    
    if align == "right":
        # Right-aligned: label and value on right side
        value_right = right - _scale_x(scale, 16)
        value_y = top + _scale_y(scale, 48)
        draw.text((value_right, top + _scale_y(scale, 16)), label, fill=tuple(theme.text_rgba), anchor="ra", font=title_font)
        draw.text((value_right, value_y), value_text, fill=tuple(theme.text_rgba), anchor="ra", font=value_font)
        suffix = _metric_suffix(widget, theme)
        if suffix:
            value_bbox = draw.textbbox((value_right, value_y), value_text, font=value_font, anchor="ra")
            suffix_x = value_bbox[2] + _scale_x(scale, 6)
            suffix_bbox_origin = draw.textbbox((0, 0), suffix, font=unit_font, anchor="la")
            value_bbox_origin = draw.textbbox((0, 0), value_text, font=value_font, anchor="ra")
            suffix_y = value_y + (value_bbox_origin[3] - suffix_bbox_origin[3])
            draw.text((suffix_x, suffix_y), suffix, fill=(255, 255, 255, 160), anchor="la", font=unit_font)
    else:
        # Left-aligned: label and value on left side (default)
        value_x = left + _scale_x(scale, 16)
        value_y = top + _scale_y(scale, 48)
        draw.text((value_x, top + _scale_y(scale, 16)), label, fill=tuple(theme.text_rgba), font=title_font)
        draw.text((value_x, value_y), value_text, fill=tuple(theme.text_rgba), font=value_font)
        suffix = _metric_suffix(widget, theme)
        if suffix:
            value_bbox = draw.textbbox((value_x, value_y), value_text, font=value_font, anchor="la")
            suffix_x = value_bbox[2] + _scale_x(scale, 6)
            suffix_bbox_origin = draw.textbbox((0, 0), suffix, font=unit_font, anchor="la")
            value_bbox_origin = draw.textbbox((0, 0), value_text, font=value_font, anchor="la")
            suffix_y = value_y + (value_bbox_origin[3] - suffix_bbox_origin[3])
            draw.text((suffix_x, suffix_y), suffix, fill=(255, 255, 255, 160), anchor="la", font=unit_font)


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
    title_font = _title_font(widget, theme, scale)
    value_font = _value_font(widget, theme, scale)
    unit_font = _unit_font(widget, theme, scale)
    if _widget_panel_enabled(widget):
        draw.rounded_rectangle((left, top, right, bottom), radius=_scale_draw(scale, 22), fill=(6, 10, 18, 120))
    context_timestamp = timestamp if timestamp.tzinfo is None else timestamp.astimezone(timestamp.tzinfo)
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


def _metric_suffix(widget: HudWidgetConfig, theme: HudThemeConfig) -> str:
    if not _style_bool(widget, "show_unit", theme.show_units):
        return ""
    binding = _require_supported_binding(widget, {"pace_seconds_per_km", "heart_rate_bpm", "cadence_spm", "elapsed_seconds", "speed_mps"})
    if binding == "pace_seconds_per_km":
        return "/km"
    if binding == "heart_rate_bpm":
        return "bpm"
    if binding == "cadence_spm":
        return "spm"
    if binding == "elapsed_seconds":
        return ""
    if binding == "speed_mps":
        return "km/h"
    raise AssertionError(f"unreachable metric binding '{binding}'")


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
        candidate = _project_point_onto_segment(current, segment_start, segment_end)
        distance_sq = _distance_squared(current, candidate)
        candidate_tangent = (segment_end[0] - segment_start[0], segment_end[1] - segment_start[1])
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


def _bearing_cardinal(bearing: int) -> str:
    cardinals = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return cardinals[int(((bearing + 22.5) % 360) // 45)]


def _draw_heading_arrow(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    vector: tuple[float, float],
    scale: RenderScale,
    *,
    arrow_rgba: tuple[int, int, int, int] = ROUTE_MAP_HEADING_ARROW_RGBA,
) -> None:
    arrow_head = _heading_arrow_head_points(center, vector, scale)
    if arrow_head is None:
        return
    dx, dy = vector
    length = math.hypot(dx, dy)
    unit_x = dx / length
    unit_y = dy / length
    center_x, center_y = center
    arrow_length = _scale_draw(scale, 18)
    tail_length = _scale_draw(scale, 6)
    tip_x = center_x + (unit_x * arrow_length)
    tip_y = center_y + (unit_y * arrow_length)
    tail_x = center_x - (unit_x * tail_length)
    tail_y = center_y - (unit_y * tail_length)
    draw.line((tail_x, tail_y, tip_x, tip_y), fill=arrow_rgba, width=_scale_draw(scale, 2))
    draw.polygon(arrow_head, fill=arrow_rgba)


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
        (tip_x - (unit_x * head_length) + (side_x * arrow_width), tip_y - (unit_y * head_length) + (side_y * arrow_width)),
        (tip_x - (unit_x * head_length) - (side_x * arrow_width), tip_y - (unit_y * head_length) - (side_y * arrow_width)),
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
        ((point_lat - start_lat) * delta_lat) + ((point_lon - start_lon) * delta_lon)
    ) / segment_length_sq
    clamped_projection = min(max(projection, 0.0), 1.0)
    return (
        start_lat + (delta_lat * clamped_projection),
        start_lon + (delta_lon * clamped_projection),
    )


def _distance_squared(left: tuple[float, float], right: tuple[float, float]) -> float:
    return ((left[0] - right[0]) ** 2) + ((left[1] - right[1]) ** 2)
