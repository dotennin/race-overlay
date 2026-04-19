from race_overlay.hud_presets import broadcast_runner_preset


def test_broadcast_runner_preset_contains_reference_layout_widgets() -> None:
    config = broadcast_runner_preset()
    ids = [widget.id for widget in config.widgets]
    assert ids == [
        "route-map",
        "distance-progress",
        "hero-pace",
        "metric-heart-rate",
        "metric-cadence",
        "metric-elapsed",
        "metric-speed",
        "context-card",
    ]
