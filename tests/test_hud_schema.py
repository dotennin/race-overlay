from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig, serialize_hud_config


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
