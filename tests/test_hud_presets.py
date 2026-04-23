from race_overlay.hud_presets import apply_legacy_field_visibility, broadcast_runner_preset


def test_broadcast_runner_preset_matches_hud_v2_widget_inventory() -> None:
    config = broadcast_runner_preset()
    ids = [widget.id for widget in config.widgets]

    assert ids == [
        "time-chip",
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

    time_chip = next(widget for widget in config.widgets if widget.id == "time-chip")
    ruler = next(widget for widget in config.widgets if widget.id == "distance-ruler")
    route_map = next(widget for widget in config.widgets if widget.id == "route-map")

    assert time_chip.style["variant"] == "timestamp_chip"
    assert time_chip.style["format"] == "%Y/%m/%d %H:%M:%S"
    assert config.theme.panel_rgba == [12, 18, 28, 148]
    assert config.theme.accent_rgba == [26, 230, 198, 255]
    assert config.theme.title_font_size_px == 14
    assert config.theme.value_font_family == "broadcast_value"
    assert config.theme.value_font_size_px == 32
    assert config.theme.unit_font_size_px == 12
    assert ruler.width == 560
    assert ruler.y == 28
    assert route_map.x == 22
    assert route_map.width == 196
    assert route_map.height == 196
    assert route_map.y == 488
    assert route_map.style["shape"] == "circle"
    assert route_map.style["show_north_marker"] is True
    assert route_map.style["show_bearing_label"] is True
    assert route_map.style["show_heading_arrow"] is True


def test_broadcast_runner_preset_keeps_route_map_refresh_scoped_to_route_map() -> None:
    config = broadcast_runner_preset()
    route_map = next(widget for widget in config.widgets if widget.id == "route-map")

    assert config.theme.panel_rgba == [12, 18, 28, 148]
    assert config.theme.accent_rgba == [26, 230, 198, 255]
    assert route_map.style["shape"] == "circle"
    assert route_map.style["show_panel"] is True
    assert route_map.style["show_north_marker"] is True
    assert route_map.style["show_bearing_label"] is True
    assert route_map.style["show_heading_arrow"] is True


def test_broadcast_runner_preset_uses_explicit_route_map_panel_toggle() -> None:
    config = broadcast_runner_preset()
    ruler = next(widget for widget in config.widgets if widget.id == "distance-ruler")
    route_map = next(widget for widget in config.widgets if widget.id == "route-map")

    assert "transparent_panel" not in ruler.style
    assert route_map.style["show_panel"] is True
    assert route_map.style["show_north_marker"] is True
    assert route_map.style["show_bearing_label"] is True
    assert route_map.style["show_heading_arrow"] is True


def test_apply_legacy_field_visibility_maps_distance_flag_to_elevation_stat_for_back_compat() -> None:
    config = apply_legacy_field_visibility(broadcast_runner_preset(), {"distance": False})
    visibility = {widget.id: widget.visible for widget in config.widgets}

    assert visibility["time-chip"] is True
    assert visibility["distance-ruler"] is False
    assert visibility["distance-stat"] is False
    assert visibility["elevation-stat"] is False
    assert visibility["heart-rate-stat"] is True


def test_apply_legacy_field_visibility_hides_time_chip_when_every_legacy_field_is_off() -> None:
    config = apply_legacy_field_visibility(
        broadcast_runner_preset(),
        {
            "pace": False,
            "elapsed": False,
            "distance": False,
            "speed": False,
            "heart_rate": False,
            "cadence": False,
            "mini_map": False,
        },
    )
    visibility = {widget.id: widget.visible for widget in config.widgets}

    assert visibility["time-chip"] is False
