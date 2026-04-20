from race_overlay.hud_presets import broadcast_runner_preset


def test_broadcast_runner_preset_matches_hud_v2_widget_inventory() -> None:
    config = broadcast_runner_preset()
    ids = [widget.id for widget in config.widgets]

    assert ids == [
        "distance-ruler",
        "elevation-stat",
        "distance-stat",
        "heart-rate-stat",
        "pace-chip",
        "cadence-chip",
        "elapsed-chip",
        "speed-chip",
        "route-map",
    ]

    ruler = next(widget for widget in config.widgets if widget.id == "distance-ruler")
    route_map = next(widget for widget in config.widgets if widget.id == "route-map")

    assert ruler.width == 560
    assert ruler.y == 28
    assert route_map.width == 140
    assert route_map.height == 140
    assert route_map.y == 554
