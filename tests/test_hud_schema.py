import pytest

from race_overlay.hud_schema import HUD_FONT_FAMILY_OPTIONS, HudConfig, HudThemeConfig, HudWidgetConfig, deserialize_hud_config, serialize_hud_config
from race_overlay.hud_presets import apply_legacy_field_visibility


def test_serialize_hud_config_round_trips_widgets() -> None:
    config = HudConfig(
        preset="broadcast-runner",
        theme=HudThemeConfig(panel_rgba=[12, 18, 28, 168], accent_rgba=[255, 196, 92, 255], note_text="Race Day"),
        widgets=[
            HudWidgetConfig(
                id="hero-pace",
                type="hero_metric",
                bindings={"value": "pace_seconds_per_km", "unit": "pace_unit"},
                anchor="top-left",
                x=24,
                y=172,
                width=336,
                height=116,
                z_index=20,
                visible=True,
                style={"label": "Pace"},
            )
        ],
    )

    payload = serialize_hud_config(config)

    assert payload["preset"] == "broadcast-runner"
    assert payload["theme"]["note_text"] == "Race Day"
    assert payload["widgets"][0]["id"] == "hero-pace"


def test_apply_legacy_field_visibility_does_not_mutate_input() -> None:
    config = HudConfig(
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
            )
        ]
    )

    updated = apply_legacy_field_visibility(config, {"mini_map": False})

    assert updated is not config
    assert updated.widgets[0].visible is False
    assert config.widgets[0].visible is True


def test_deserialize_hud_config_rejects_duplicate_widget_ids() -> None:
    payload = serialize_hud_config(
        HudConfig(
            preset="broadcast-runner",
            theme=HudThemeConfig(),
            widgets=[
                HudWidgetConfig(
                    id="hero-pace",
                    type="hero_metric",
                    bindings={"value": "pace_seconds_per_km"},
                    anchor="top-left",
                    x=24,
                    y=172,
                    width=336,
                    height=116,
                ),
                HudWidgetConfig(
                    id="hero-pace",
                    type="metric_card",
                    bindings={"value": "heart_rate_bpm"},
                    anchor="top-right",
                    x=980,
                    y=32,
                    width=160,
                    height=108,
                ),
            ],
        )
    )

    with pytest.raises(ValueError, match="duplicate HUD widget id"):
        deserialize_hud_config(payload)


def test_deserialize_hud_config_supports_typography_roles_and_extended_widget_styles() -> None:
    payload = {
        "preset": "custom",
        "theme": {
            "panel_rgba": [12, 18, 28, 168],
            "accent_rgba": [255, 196, 92, 255],
            "text_rgba": [255, 255, 255, 255],
            "note_text": "Race Day",
            "font_family": "sans",
            "font_weight": "regular",
            "font_size_px": 18,
            "show_units": True,
            "title_font_family": "serif",
            "title_font_weight": "bold",
            "title_font_size_px": 20,
            "value_font_family": "mono",
            "value_font_weight": "regular",
            "value_font_size_px": 28,
            "unit_font_family": "sans",
            "unit_font_weight": "bold",
            "unit_font_size_px": 14,
        },
        "widgets": [
            {
                "id": "route-map",
                "type": "route_map",
                "bindings": {"value": "route_points"},
                "anchor": "top-left",
                "x": 24,
                "y": 24,
                "width": 176,
                "height": 128,
                "style": {
                    "label": "",
                    "shape": "circle",
                    "show_panel": True,
                    "show_north_marker": True,
                    "show_bearing_label": False,
                    "show_heading_arrow": True,
                },
            },
            {
                "id": "time-card",
                "type": "context_card",
                "bindings": {"value": "timestamp"},
                "anchor": "top-right",
                "x": 24,
                "y": 24,
                "width": 240,
                "height": 128,
                "style": {
                    "label": "Context",
                    "variant": "timestamp_chip",
                    "format": "%H:%M",
                },
            },
        ],
    }

    config = deserialize_hud_config(payload)
    serialized = serialize_hud_config(config)

    assert config.theme.title_font_family == "serif"
    assert config.theme.title_font_weight == "bold"
    assert config.theme.title_font_size_px == 20
    assert config.theme.value_font_family == "mono"
    assert config.theme.value_font_weight == "regular"
    assert config.theme.value_font_size_px == 28
    assert config.theme.unit_font_family == "sans"
    assert config.theme.unit_font_weight == "bold"
    assert config.theme.unit_font_size_px == 14
    assert serialized["theme"]["title_font_family"] == "serif"
    assert serialized["theme"]["value_font_size_px"] == 28
    assert serialized["theme"]["unit_font_weight"] == "bold"
    assert serialized["widgets"][0]["style"]["show_north_marker"] is True
    assert serialized["widgets"][0]["style"]["show_bearing_label"] is False
    assert serialized["widgets"][0]["style"]["show_heading_arrow"] is True
    assert serialized["widgets"][1]["style"]["variant"] == "timestamp_chip"
    assert serialized["widgets"][1]["style"]["format"] == "%H:%M"


def test_deserialize_hud_config_applies_broadcast_defaults_for_absent_role_fields() -> None:
    config = deserialize_hud_config(
        {
            "preset": "custom",
            "theme": {
                "panel_rgba": [12, 18, 28, 168],
                "accent_rgba": [255, 196, 92, 255],
                "text_rgba": [255, 255, 255, 255],
                "note_text": "Race Day",
                "font_family": "mono",
                "font_weight": "bold",
                "font_size_px": 30,
                "show_units": True,
            },
            "widgets": [],
        }
    )

    serialized = serialize_hud_config(config)

    assert config.theme.title_font_family == "broadcast_ui"
    assert config.theme.value_font_family == "broadcast_value"
    assert config.theme.unit_font_family == "broadcast_ui"
    assert serialized["theme"]["title_font_family"] == "broadcast_ui"
    assert serialized["theme"]["value_font_family"] == "broadcast_value"
    assert serialized["theme"]["unit_font_family"] == "broadcast_ui"


def test_hud_font_family_options_includes_broadcast_families() -> None:
    assert "broadcast_ui" in HUD_FONT_FAMILY_OPTIONS
    assert "broadcast_value" in HUD_FONT_FAMILY_OPTIONS
    assert "sans" in HUD_FONT_FAMILY_OPTIONS
    assert "serif" in HUD_FONT_FAMILY_OPTIONS
    assert "mono" in HUD_FONT_FAMILY_OPTIONS


def test_hud_theme_config_defaults_to_broadcast_fonts_for_new_huds() -> None:
    theme = HudThemeConfig()
    
    assert theme.font_family == "broadcast_ui"
    assert theme.title_font_family == "broadcast_ui"
    assert theme.value_font_family == "broadcast_value"
    assert theme.unit_font_family == "broadcast_ui"


def test_deserialize_hud_config_supports_progress_bar_rgba_style_fields() -> None:
    config = deserialize_hud_config(
        {
            "preset": "custom",
            "theme": {
                "panel_rgba": [12, 18, 28, 168],
                "accent_rgba": [255, 196, 92, 255],
                "text_rgba": [255, 255, 255, 255],
                "note_text": "Race Day",
                "font_family": "broadcast_ui",
                "font_weight": "regular",
                "font_size_px": 18,
                "show_units": True,
            },
            "widgets": [
                {
                    "id": "distance-ruler",
                    "type": "progress_bar",
                    "bindings": {"value": "distance_m"},
                    "anchor": "top-left",
                    "x": 360,
                    "y": 28,
                    "width": 560,
                    "height": 56,
                    "style": {
                        "label": "Distance",
                        "fill_rgba": [34, 255, 138, 255],
                        "rail_rgba": [8, 12, 20, 220],
                        "tick_rgba": [230, 238, 245, 168],
                    },
                }
            ],
        }
    )

    ruler = config.widgets[0]
    serialized = serialize_hud_config(config)

    assert ruler.style["fill_rgba"] == [34, 255, 138, 255]
    assert ruler.style["rail_rgba"] == [8, 12, 20, 220]
    assert ruler.style["tick_rgba"] == [230, 238, 245, 168]
    assert serialized["widgets"][0]["style"]["fill_rgba"] == [34, 255, 138, 255]
    assert serialized["widgets"][0]["style"]["rail_rgba"] == [8, 12, 20, 220]
    assert serialized["widgets"][0]["style"]["tick_rgba"] == [230, 238, 245, 168]
