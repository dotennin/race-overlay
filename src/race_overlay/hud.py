from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageDraw

from race_overlay.hud_presets import broadcast_runner_preset
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig
from race_overlay.models import HudSample


@dataclass(slots=True, frozen=True)
class HudLayout:
    """Legacy layout compatibility shim. Prefer passing ``hud_config``."""

    pace_anchor: tuple[int, int]
    stats_anchor: tuple[int, int]
    map_box: tuple[int, int, int, int]

    @classmethod
    def default(cls) -> "HudLayout":
        return cls(pace_anchor=(64, 48), stats_anchor=(64, 180), map_box=(980, 40, 1220, 280))

    def to_hud_config(self) -> HudConfig:
        config = broadcast_runner_preset()
        positions = {
            "route-map": (*self.map_box[:2], self.map_box[2] - self.map_box[0], self.map_box[3] - self.map_box[1]),
            "hero-pace": (max(self.pace_anchor[0] - 20, 0), max(self.pace_anchor[1] - 18, 0), 336, 116),
            "metric-heart-rate": (max(self.stats_anchor[0] - 40, 0), max(self.stats_anchor[1] - 16, 0), 160, 96),
            "metric-cadence": (max(self.stats_anchor[0] + 132, 0), max(self.stats_anchor[1] - 16, 0), 160, 96),
            "metric-elapsed": (max(self.stats_anchor[0] - 40, 0), max(self.stats_anchor[1] + 92, 0), 160, 96),
            "metric-speed": (max(self.stats_anchor[0] + 132, 0), max(self.stats_anchor[1] + 92, 0), 160, 96),
        }
        for widget in config.widgets:
            if widget.id in positions:
                widget.x, widget.y, widget.width, widget.height = positions[widget.id]
        return config


def render_hud_frame(
    width: int,
    height: int,
    hud_value: HudSample,
    route_points: list[tuple[float, float]],
    hud_config: HudConfig | HudLayout | None = None,
    elapsed_seconds: int = 0,
    *,
    layout: HudLayout | None = None,
) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    resolved_hud_config = _resolve_hud_config(hud_config, layout)
    widgets = sorted((widget for widget in resolved_hud_config.widgets if widget.visible), key=lambda item: item.z_index)
    for widget in widgets:
        _render_widget(draw, widget, hud_value, route_points, elapsed_seconds, resolved_hud_config.theme)
    return image


def _resolve_hud_config(hud_config: HudConfig | HudLayout | None, layout: HudLayout | None) -> HudConfig:
    if isinstance(hud_config, HudLayout):
        layout = hud_config
        hud_config = None
    if hud_config is not None:
        return hud_config
    return (layout or HudLayout.default()).to_hud_config()


def _render_widget(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    route_points: list[tuple[float, float]],
    elapsed_seconds: int,
    theme: HudThemeConfig,
) -> None:
    if widget.type == "progress_bar":
        _draw_progress_bar(draw, widget, hud_value.distance_m, theme)
    elif widget.type == "route_map":
        _draw_route_map(draw, widget, route_points, theme)
    elif widget.type == "hero_metric":
        _draw_hero_metric(draw, widget, hud_value.pace_seconds_per_km, theme)
    elif widget.type == "metric_card":
        _draw_metric_card(draw, widget, hud_value, elapsed_seconds, theme)
    elif widget.type == "context_card":
        _draw_context_card(draw, widget, hud_value.timestamp, theme)


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    distance_m: float | None,
    theme: HudThemeConfig,
) -> None:
    left, top = widget.x, widget.y
    right, bottom = left + widget.width, top + widget.height
    draw.rounded_rectangle((left, top, right, bottom), radius=18, fill=tuple(theme.panel_rgba))
    track_left = left + 108
    track_top = top + 28
    track_right = right - 124
    track_bottom = top + 38
    draw.rounded_rectangle((track_left, track_top, track_right, track_bottom), radius=999, fill=(255, 255, 255, 40))
    progress = min(max((distance_m or 0.0) / 42195.0, 0.0), 1.0)
    filled = track_left + int((widget.width - 232) * progress)
    draw.rounded_rectangle((track_left, track_top, max(track_left, filled), track_bottom), radius=999, fill=tuple(theme.accent_rgba))
    draw.text((left + 22, top + 18), str(widget.style.get("label", "Distance")), fill=tuple(theme.text_rgba))
    draw.text((right - 94, top + 18), f"{(distance_m or 0.0) / 1000:.1f} km", fill=tuple(theme.text_rgba))


def _draw_route_map(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    route_points: list[tuple[float, float]],
    theme: HudThemeConfig,
) -> None:
    left, top = widget.x, widget.y
    right, bottom = left + widget.width, top + widget.height
    draw.rounded_rectangle((left, top, right, bottom), radius=16, fill=tuple(theme.panel_rgba), outline=(255, 255, 255, 120))
    if len(route_points) < 2:
        return

    latitudes = [point[0] for point in route_points]
    longitudes = [point[1] for point in route_points]
    lat_min, lat_max = min(latitudes), max(latitudes)
    lon_min, lon_max = min(longitudes), max(longitudes)

    def project(point: tuple[float, float]) -> tuple[float, float]:
        lat, lon = point
        x = left + 12 + ((lon - lon_min) / max(lon_max - lon_min, 1e-9)) * (widget.width - 24)
        y = bottom - 12 - ((lat - lat_min) / max(lat_max - lat_min, 1e-9)) * (widget.height - 24)
        return (x, y)

    projected = [project(point) for point in route_points]
    draw.line(projected, fill=tuple(theme.accent_rgba), width=4)
    x, y = projected[-1]
    draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 90, 90, 255))


def _draw_hero_metric(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    pace_seconds_per_km: float | None,
    theme: HudThemeConfig,
) -> None:
    left, top = widget.x, widget.y
    right, bottom = left + widget.width, top + widget.height
    draw.rounded_rectangle((left, top, right, bottom), radius=22, fill=tuple(theme.panel_rgba))
    draw.text((left + 20, top + 18), str(widget.style.get("label", "Pace")), fill=tuple(theme.text_rgba))
    draw.text((left + 20, top + 54), _format_pace(pace_seconds_per_km), fill=tuple(theme.text_rgba))
    draw.text((left + 220, top + 62), "/km", fill=tuple(theme.text_rgba))


def _draw_metric_card(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    hud_value: HudSample,
    elapsed_seconds: int,
    theme: HudThemeConfig,
) -> None:
    left, top = widget.x, widget.y
    right, bottom = left + widget.width, top + widget.height
    draw.rounded_rectangle((left, top, right, bottom), radius=18, fill=tuple(theme.panel_rgba))
    label = str(widget.style.get("label", "Metric"))
    draw.text((left + 16, top + 16), label, fill=tuple(theme.text_rgba))
    draw.text((left + 16, top + 52), _metric_value(widget, hud_value, elapsed_seconds), fill=tuple(theme.text_rgba))
    draw.text((left + 16, bottom - 24), _metric_suffix(widget), fill=(255, 255, 255, 160))


def _draw_context_card(
    draw: ImageDraw.ImageDraw,
    widget: HudWidgetConfig,
    timestamp: datetime,
    theme: HudThemeConfig,
) -> None:
    left, top = widget.x, widget.y
    right, bottom = left + widget.width, top + widget.height
    draw.rounded_rectangle((left, top, right, bottom), radius=22, fill=tuple(theme.panel_rgba))
    draw.text((left + 20, top + 20), "Context", fill=tuple(theme.text_rgba))
    draw.text((left + 20, top + 70), timestamp.astimezone().strftime("%H:%M"), fill=tuple(theme.text_rgba))
    draw.text((left + 20, top + 122), timestamp.astimezone().strftime("%Y.%m.%d"), fill=tuple(theme.text_rgba))
    draw.text((left + 140, top + 70), theme.note_text, fill=tuple(theme.text_rgba))


def _metric_value(widget: HudWidgetConfig, hud_value: HudSample, elapsed_seconds: int) -> str:
    binding = widget.bindings.get("value")
    if binding == "heart_rate_bpm":
        return "--" if hud_value.heart_rate_bpm is None else str(hud_value.heart_rate_bpm)
    if binding == "cadence_spm":
        return "--" if hud_value.cadence_spm is None else str(hud_value.cadence_spm)
    if binding == "elapsed_seconds":
        hours, remainder = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    if binding == "speed_mps":
        return f"{(hud_value.speed_mps or 0.0) * 3.6:.1f}"
    return "--"


def _metric_suffix(widget: HudWidgetConfig) -> str:
    binding = widget.bindings.get("value")
    if binding == "heart_rate_bpm":
        return "bpm"
    if binding == "cadence_spm":
        return "spm"
    if binding == "elapsed_seconds":
        return "hh:mm:ss"
    if binding == "speed_mps":
        return "km/h"
    return ""


def _format_pace(pace_seconds_per_km: float | None) -> str:
    if pace_seconds_per_km is None:
        return "--:--"
    total_seconds = max(int(round(pace_seconds_per_km)), 0)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"
