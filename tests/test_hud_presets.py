from race_overlay.hud_presets import apply_legacy_field_visibility, broadcast_runner_preset


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
    assert route_map.x == 26
    assert route_map.width == 180
    assert route_map.height == 180
    assert route_map.y == 514
    assert route_map.style["shape"] == "circle"
    assert route_map.width * route_map.height > 176 * 128


def test_broadcast_runner_preset_uses_explicit_route_map_panel_toggle() -> None:
    config = broadcast_runner_preset()
    ruler = next(widget for widget in config.widgets if widget.id == "distance-ruler")
    route_map = next(widget for widget in config.widgets if widget.id == "route-map")

    assert "transparent_panel" not in ruler.style
    assert route_map.style["show_panel"] is True


def test_apply_legacy_field_visibility_maps_distance_flag_to_elevation_stat_for_back_compat() -> None:
    config = apply_legacy_field_visibility(broadcast_runner_preset(), {"distance": False})
    visibility = {widget.id: widget.visible for widget in config.widgets}

    assert visibility["distance-ruler"] is False
    assert visibility["distance-stat"] is False
    assert visibility["elevation-stat"] is False
    assert visibility["heart-rate-stat"] is True
