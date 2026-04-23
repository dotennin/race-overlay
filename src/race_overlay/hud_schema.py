import math
from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class HudThemeConfig:
    panel_rgba: list[int] = field(default_factory=lambda: [12, 18, 28, 168])
    accent_rgba: list[int] = field(default_factory=lambda: [255, 196, 92, 255])
    text_rgba: list[int] = field(default_factory=lambda: [255, 255, 255, 255])
    note_text: str = "Race Day"
    font_family: str = "broadcast_ui"
    font_weight: str = "regular"
    font_size_px: int = 18
    title_font_family: str | None = "broadcast_ui"
    title_font_weight: str | None = None
    title_font_size_px: int | None = None
    value_font_family: str | None = "broadcast_value"
    value_font_weight: str | None = None
    value_font_size_px: int | None = None
    unit_font_family: str | None = "broadcast_ui"
    unit_font_weight: str | None = None
    unit_font_size_px: int | None = None
    show_units: bool = True


@dataclass(slots=True)
class HudWidgetConfig:
    id: str
    type: str
    bindings: dict[str, str]
    anchor: str
    x: int
    y: int
    width: int
    height: int
    z_index: int = 0
    visible: bool = True
    style: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(slots=True)
class HudConfig:
    preset: str = "broadcast-runner"
    theme: HudThemeConfig = field(default_factory=HudThemeConfig)
    widgets: list[HudWidgetConfig] = field(default_factory=list)


_HUD_KEYS = frozenset(HudConfig.__dataclass_fields__)
_HUD_THEME_KEYS = frozenset(HudThemeConfig.__dataclass_fields__)
_HUD_WIDGET_KEYS = frozenset(HudWidgetConfig.__dataclass_fields__)
HUD_FONT_FAMILY_OPTIONS = ("sans", "serif", "mono", "broadcast_ui", "broadcast_value")
HUD_FONT_WEIGHT_OPTIONS = ("regular", "bold")


def deserialize_hud_config(payload: dict[str, object], *, require_complete: bool = False) -> HudConfig:
    if not isinstance(payload, dict):
        raise TypeError("hud config must be a mapping")
    if "fields" in payload:
        raise ValueError("editor save requires a complete HUD document with preset, theme, and widgets")
    _reject_unexpected_keys(payload, _HUD_KEYS, "hud")
    if require_complete:
        missing = [key for key in ("preset", "theme", "widgets") if key not in payload]
        if missing:
            raise ValueError("editor save requires a complete HUD document with preset, theme, and widgets")

    theme_payload = payload.get("theme", {})
    widgets_payload = payload.get("widgets", [])
    if not isinstance(theme_payload, dict):
        raise TypeError("hud.theme must be a mapping")
    if not isinstance(widgets_payload, list):
        raise TypeError("hud.widgets must be a list")

    widgets = [_deserialize_widget(widget_payload) for widget_payload in widgets_payload]
    _require_unique_widget_ids(widgets)

    return HudConfig(
        preset=_require_string(payload.get("preset", "broadcast-runner"), "hud.preset"),
        theme=_deserialize_theme(theme_payload),
        widgets=widgets,
    )


def serialize_hud_config(config: HudConfig) -> dict[str, object]:
    return asdict(config)


def _deserialize_widget(payload: object) -> HudWidgetConfig:
    if not isinstance(payload, dict):
        raise TypeError("hud.widgets entries must be mappings")
    _reject_unexpected_keys(payload, _HUD_WIDGET_KEYS, "hud.widgets")
    return HudWidgetConfig(
        id=_require_string(payload.get("id"), "hud.widgets[].id"),
        type=_require_string(payload.get("type"), "hud.widgets[].type"),
        bindings=_require_string_mapping(payload.get("bindings"), "hud.widgets[].bindings"),
        anchor=_require_string(payload.get("anchor"), "hud.widgets[].anchor"),
        x=_coerce_int(payload.get("x"), "x"),
        y=_coerce_int(payload.get("y"), "y"),
        width=_coerce_int(payload.get("width"), "width"),
        height=_coerce_int(payload.get("height"), "height"),
        z_index=_coerce_int(payload.get("z_index", 0), "z_index"),
        visible=_coerce_bool(payload.get("visible", True), "hud.widgets[].visible"),
        style=_require_style_mapping(payload.get("style", {}), "hud.widgets[].style"),
    )


def _deserialize_theme(payload: object) -> HudThemeConfig:
    if not isinstance(payload, dict):
        raise TypeError("hud.theme must be a mapping")
    _reject_unexpected_keys(payload, _HUD_THEME_KEYS, "hud.theme")
    defaults = HudThemeConfig()
    return validate_hud_theme_config(
        HudThemeConfig(
            panel_rgba=_require_rgba_list(payload.get("panel_rgba", defaults.panel_rgba), "panel_rgba"),
            accent_rgba=_require_rgba_list(payload.get("accent_rgba", defaults.accent_rgba), "accent_rgba"),
            text_rgba=_require_rgba_list(payload.get("text_rgba", defaults.text_rgba), "text_rgba"),
            note_text=_require_text(payload.get("note_text", defaults.note_text), "note_text"),
            font_family=_require_enum_string(
                payload.get("font_family", defaults.font_family), "font_family", HUD_FONT_FAMILY_OPTIONS
            ),
            font_weight=_require_enum_string(
                payload.get("font_weight", defaults.font_weight), "font_weight", HUD_FONT_WEIGHT_OPTIONS
            ),
            font_size_px=_require_min_int(payload.get("font_size_px", defaults.font_size_px), "font_size_px", 8),
            title_font_family=_require_enum_string(
                payload["title_font_family"],
                "title_font_family",
                HUD_FONT_FAMILY_OPTIONS,
            )
            if "title_font_family" in payload and payload["title_font_family"] is not None
            else (None if "title_font_family" in payload else defaults.title_font_family),
            title_font_weight=_require_enum_string(
                payload["title_font_weight"],
                "title_font_weight",
                HUD_FONT_WEIGHT_OPTIONS,
            )
            if "title_font_weight" in payload and payload["title_font_weight"] is not None
            else None,
            title_font_size_px=_require_min_int(
                payload["title_font_size_px"], "title_font_size_px", 8
            )
            if "title_font_size_px" in payload and payload["title_font_size_px"] is not None
            else None,
            value_font_family=_require_enum_string(
                payload["value_font_family"],
                "value_font_family",
                HUD_FONT_FAMILY_OPTIONS,
            )
            if "value_font_family" in payload and payload["value_font_family"] is not None
            else (None if "value_font_family" in payload else defaults.value_font_family),
            value_font_weight=_require_enum_string(
                payload["value_font_weight"],
                "value_font_weight",
                HUD_FONT_WEIGHT_OPTIONS,
            )
            if "value_font_weight" in payload and payload["value_font_weight"] is not None
            else None,
            value_font_size_px=_require_min_int(
                payload["value_font_size_px"], "value_font_size_px", 8
            )
            if "value_font_size_px" in payload and payload["value_font_size_px"] is not None
            else None,
            unit_font_family=_require_enum_string(
                payload["unit_font_family"],
                "unit_font_family",
                HUD_FONT_FAMILY_OPTIONS,
            )
            if "unit_font_family" in payload and payload["unit_font_family"] is not None
            else (None if "unit_font_family" in payload else defaults.unit_font_family),
            unit_font_weight=_require_enum_string(
                payload["unit_font_weight"],
                "unit_font_weight",
                HUD_FONT_WEIGHT_OPTIONS,
            )
            if "unit_font_weight" in payload and payload["unit_font_weight"] is not None
            else None,
            unit_font_size_px=_require_min_int(
                payload["unit_font_size_px"], "unit_font_size_px", 8
            )
            if "unit_font_size_px" in payload and payload["unit_font_size_px"] is not None
            else None,
            show_units=_coerce_bool(payload.get("show_units", defaults.show_units), "show_units"),
        )
    )


def validate_hud_theme_config(theme: HudThemeConfig) -> HudThemeConfig:
    theme.panel_rgba = _require_rgba_list(theme.panel_rgba, "panel_rgba")
    theme.accent_rgba = _require_rgba_list(theme.accent_rgba, "accent_rgba")
    theme.text_rgba = _require_rgba_list(theme.text_rgba, "text_rgba")
    theme.note_text = _require_text(theme.note_text, "note_text")
    theme.font_family = _require_enum_string(theme.font_family, "font_family", HUD_FONT_FAMILY_OPTIONS)
    theme.font_weight = _require_enum_string(theme.font_weight, "font_weight", HUD_FONT_WEIGHT_OPTIONS)
    theme.font_size_px = _require_min_int(theme.font_size_px, "font_size_px", 8)
    theme.title_font_family = _require_optional_enum_string(
        theme.title_font_family, "title_font_family", HUD_FONT_FAMILY_OPTIONS
    )
    theme.title_font_weight = _require_optional_enum_string(
        theme.title_font_weight, "title_font_weight", HUD_FONT_WEIGHT_OPTIONS
    )
    theme.title_font_size_px = _require_optional_min_int(theme.title_font_size_px, "title_font_size_px", 8)
    theme.value_font_family = _require_optional_enum_string(
        theme.value_font_family, "value_font_family", HUD_FONT_FAMILY_OPTIONS
    )
    theme.value_font_weight = _require_optional_enum_string(
        theme.value_font_weight, "value_font_weight", HUD_FONT_WEIGHT_OPTIONS
    )
    theme.value_font_size_px = _require_optional_min_int(theme.value_font_size_px, "value_font_size_px", 8)
    theme.unit_font_family = _require_optional_enum_string(
        theme.unit_font_family, "unit_font_family", HUD_FONT_FAMILY_OPTIONS
    )
    theme.unit_font_weight = _require_optional_enum_string(
        theme.unit_font_weight, "unit_font_weight", HUD_FONT_WEIGHT_OPTIONS
    )
    theme.unit_font_size_px = _require_optional_min_int(theme.unit_font_size_px, "unit_font_size_px", 8)
    theme.show_units = _coerce_bool(theme.show_units, "show_units")
    return theme


def _require_unique_widget_ids(widgets: list[HudWidgetConfig]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for widget in widgets:
        if widget.id in seen and widget.id not in duplicates:
            duplicates.append(widget.id)
            continue
        seen.add(widget.id)
    if duplicates:
        suffix = "s" if len(duplicates) != 1 else ""
        raise ValueError(f"duplicate HUD widget id{suffix}: {', '.join(duplicates)}")


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_string_mapping(value: object, field_name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a mapping")
    mapping: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ValueError(f"{field_name} must contain only string keys and values")
        mapping[key] = item
    return mapping


def _require_style_mapping(value: object, field_name: str) -> dict[str, str | int | float | bool]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a mapping")
    mapping: dict[str, str | int | float | bool] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} must contain only string keys")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError(f"{field_name} values must be strings, booleans, or finite numbers")
        if isinstance(item, bool | str | int | float):
            mapping[key] = item
            continue
        raise ValueError(f"{field_name} values must be strings, booleans, or finite numbers")
    return mapping


def _require_rgba_list(value: object, field_name: str) -> list[int]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"{field_name} must be a list of 4 integers")
    return [_coerce_color_channel(channel, field_name) for channel in value]


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _require_enum_string(value: object, field_name: str, allowed: tuple[str, ...]) -> str:
    text = _require_string(value, field_name)
    if text not in allowed:
        allowed_values = ", ".join(allowed)
        raise ValueError(f"{field_name} must be one of: {allowed_values}")
    return text


def _require_optional_enum_string(value: object, field_name: str, allowed: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    return _require_enum_string(value, field_name, allowed)


def _require_min_int(value: object, field_name: str, minimum: int) -> int:
    number = _coerce_int(value, field_name)
    if number < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    return number


def _require_optional_min_int(value: object, field_name: str, minimum: int) -> int | None:
    if value is None:
        return None
    return _require_min_int(value, field_name, minimum)


def _coerce_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field_name} must be a finite integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    raise ValueError(f"{field_name} must be a finite integer")


def _coerce_color_channel(value: object, field_name: str) -> int:
    channel = _coerce_int(value, field_name)
    if channel < 0 or channel > 255:
        raise ValueError(f"{field_name} must contain integers between 0 and 255")
    return channel


def _coerce_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _reject_unexpected_keys(payload: dict[str, object], allowed: frozenset[str], field_name: str) -> None:
    unexpected = sorted(set(payload) - allowed)
    if unexpected:
        suffix = "s" if len(unexpected) != 1 else ""
        raise ValueError(f"unexpected {field_name} key{suffix}: {', '.join(unexpected)}")
