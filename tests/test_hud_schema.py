from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig, serialize_hud_config
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
