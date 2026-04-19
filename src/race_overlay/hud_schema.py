from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class HudThemeConfig:
    panel_rgba: list[int] = field(default_factory=lambda: [12, 18, 28, 168])
    accent_rgba: list[int] = field(default_factory=lambda: [255, 196, 92, 255])
    text_rgba: list[int] = field(default_factory=lambda: [255, 255, 255, 255])
    note_text: str = "Race Day"


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


def serialize_hud_config(config: HudConfig) -> dict[str, object]:
    return asdict(config)
