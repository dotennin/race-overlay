from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig


def broadcast_runner_preset() -> HudConfig:
    return HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig("route-map", "route_map", {"value": "route_points"}, "top-left", 24, 24, 176, 128, 10, True, {"label": "Route map"}),
            HudWidgetConfig("distance-progress", "progress_bar", {"value": "distance_m"}, "top-left", 222, 28, 1034, 64, 10, True, {"label": "Distance"}),
            HudWidgetConfig("hero-pace", "hero_metric", {"value": "pace_seconds_per_km"}, "top-left", 24, 172, 336, 116, 20, True, {"label": "Pace"}),
            HudWidgetConfig("metric-heart-rate", "metric_card", {"value": "heart_rate_bpm"}, "top-left", 24, 312, 160, 96, 10, True, {"label": "Heart rate"}),
            HudWidgetConfig("metric-cadence", "metric_card", {"value": "cadence_spm"}, "top-left", 196, 312, 160, 96, 10, True, {"label": "Cadence"}),
            HudWidgetConfig("metric-elapsed", "metric_card", {"value": "elapsed_seconds"}, "top-left", 24, 420, 160, 96, 10, True, {"label": "Elapsed"}),
            HudWidgetConfig("metric-speed", "metric_card", {"value": "speed_mps"}, "top-left", 196, 420, 160, 96, 10, True, {"label": "Speed"}),
            HudWidgetConfig("context-card", "context_card", {"value": "timestamp"}, "top-right", 996, 120, 260, 196, 20, True, {"label": "Context"}),
        ],
    )


def apply_legacy_field_visibility(config: HudConfig, fields: dict[str, bool]) -> HudConfig:
    visibility_map = {
        "route-map": fields.get("mini_map", True),
        "hero-pace": fields.get("pace", True),
        "distance-progress": fields.get("distance", True),
        "metric-heart-rate": fields.get("heart_rate", True),
        "metric-cadence": fields.get("cadence", True),
        "metric-elapsed": fields.get("elapsed", True),
        "metric-speed": fields.get("speed", True),
    }
    for widget in config.widgets:
        if widget.id in visibility_map:
            widget.visible = visibility_map[widget.id]
    return config
