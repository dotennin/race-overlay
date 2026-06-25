export type HudStyleValue = string | number | boolean | number[];

export interface HudThemeConfig {
  textRgba: number[];
  noteText: string;
  fontFamily: string;
  fontWeight: string;
  fontSizePx: number;
  titleFontFamily: string | null;
  titleFontWeight: string | null;
  titleFontSizePx: number | null;
  valueFontFamily: string | null;
  valueFontWeight: string | null;
  valueFontSizePx: number | null;
  unitFontFamily: string | null;
  unitFontWeight: string | null;
  unitFontSizePx: number | null;
  showUnits: boolean;
}

export interface HudWidgetConfig {
  id: string;
  type: string;
  bindings: Record<string, string>;
  anchor: string;
  x: number;
  y: number;
  width: number;
  height: number;
  zIndex: number;
  visible: boolean;
  style: Record<string, HudStyleValue>;
}

export interface HudConfig {
  preset: string;
  theme: HudThemeConfig;
  widgets: HudWidgetConfig[];
}

export interface SerializedHudThemeConfig {
  text_rgba: number[];
  note_text: string;
  font_family: string;
  font_weight: string;
  font_size_px: number;
  title_font_family: string | null;
  title_font_weight: string | null;
  title_font_size_px: number | null;
  value_font_family: string | null;
  value_font_weight: string | null;
  value_font_size_px: number | null;
  unit_font_family: string | null;
  unit_font_weight: string | null;
  unit_font_size_px: number | null;
  show_units: boolean;
}

export interface SerializedHudWidgetConfig {
  id: string;
  type: string;
  bindings: Record<string, string>;
  anchor: string;
  x: number;
  y: number;
  width: number;
  height: number;
  z_index: number;
  visible: boolean;
  style: Record<string, HudStyleValue>;
}

export interface SerializedHudConfig {
  preset: string;
  theme: SerializedHudThemeConfig;
  widgets: SerializedHudWidgetConfig[];
}

export function broadcastRunnerPreset(): HudConfig {
  return {
    preset: "broadcast-runner",
    theme: {
      textRgba: [247, 251, 255, 255],
      noteText: "Race Day",
      fontFamily: "broadcast_value",
      fontWeight: "regular",
      fontSizePx: 18,
      titleFontFamily: "broadcast_value",
      titleFontWeight: "regular",
      titleFontSizePx: 16,
      valueFontFamily: "broadcast_value",
      valueFontWeight: "bold",
      valueFontSizePx: 32,
      unitFontFamily: "broadcast_value",
      unitFontWeight: "regular",
      unitFontSizePx: 13,
      showUnits: true,
    },
    widgets: [
      widget("time-chip", "context_card", { value: "timestamp" }, "top-left", 44, 40, 292, 56, 36, {
        variant: "timestamp_chip",
        format: "%Y/%m/%d %H:%M:%S",
      }),
      widget("distance-ruler", "progress_bar", { value: "distance_m" }, "top-left", 359, 40, 560, 56, 40, {
        label: "Distance",
        variant: "ruler",
        show_current_value: true,
        show_total_value: true,
        fill_rgba: [34, 255, 138, 255],
        rail_rgba: [8, 12, 20, 220],
        tick_rgba: [230, 238, 245, 168],
      }),
      widget("elevation-stat", "stat_block", { value: "altitude_m" }, "top-left", 44, 122, 152, 82, 30, {
        label: "Elevation",
        unit: "M",
      }),
      widget("distance-stat", "stat_block", { value: "distance_m" }, "top-left", 44, 208, 196, 84, 30, {
        label: "Distance",
        unit: "KM",
        decimals: 2,
      }),
      widget("heart-rate-stat", "stat_block", { value: "heart_rate_bpm" }, "top-right", 1092, 118, 152, 82, 30, {
        label: "Heart rate",
        unit: "BPM",
        align: "right",
      }),
      widget("pace-chip", "metric_card", { value: "pace_seconds_per_km" }, "bottom-right", 978, 552, 126, 76, 20, {
        label: "Pace",
        variant: "compact",
      }),
      widget("cadence-chip", "metric_card", { value: "cadence_spm" }, "bottom-right", 1110, 552, 126, 76, 20, {
        label: "Cadence",
        variant: "compact",
      }),
      widget("elapsed-chip", "metric_card", { value: "elapsed_seconds" }, "bottom-right", 978, 636, 126, 76, 20, {
        label: "Elapsed",
        variant: "compact",
      }),
      widget("speed-chip", "metric_card", { value: "speed_mps" }, "bottom-right", 1110, 636, 126, 126, 20, {
        label: "Speed",
        variant: "speed_gauge",
      }),
      widget("route-map", "route_map", { value: "route_points" }, "top-left", 21, 488, 196, 196, 20, {
        label: "",
        shape: "circle",
        zoom_percent: 90,
        show_panel: true,
        show_north_marker: true,
        show_bearing_label: true,
        background_rgba: [6, 10, 18, 148],
        completed_rgba: [34, 255, 138, 255],
        remaining_rgba: [13, 144, 195, 255],
      }),
    ],
  };
}

export function serializeHudConfig(config: HudConfig): SerializedHudConfig {
  return {
    preset: config.preset,
    theme: {
      text_rgba: [...config.theme.textRgba],
      note_text: config.theme.noteText,
      font_family: config.theme.fontFamily,
      font_weight: config.theme.fontWeight,
      font_size_px: config.theme.fontSizePx,
      title_font_family: config.theme.titleFontFamily,
      title_font_weight: config.theme.titleFontWeight,
      title_font_size_px: config.theme.titleFontSizePx,
      value_font_family: config.theme.valueFontFamily,
      value_font_weight: config.theme.valueFontWeight,
      value_font_size_px: config.theme.valueFontSizePx,
      unit_font_family: config.theme.unitFontFamily,
      unit_font_weight: config.theme.unitFontWeight,
      unit_font_size_px: config.theme.unitFontSizePx,
      show_units: config.theme.showUnits,
    },
    widgets: config.widgets.map((hudWidget) => ({
      id: hudWidget.id,
      type: hudWidget.type,
      bindings: { ...hudWidget.bindings },
      anchor: hudWidget.anchor,
      x: hudWidget.x,
      y: hudWidget.y,
      width: hudWidget.width,
      height: hudWidget.height,
      z_index: hudWidget.zIndex,
      visible: hudWidget.visible,
      style: { ...hudWidget.style },
    })),
  };
}

function widget(
  id: string,
  type: string,
  bindings: Record<string, string>,
  anchor: string,
  x: number,
  y: number,
  width: number,
  height: number,
  zIndex: number,
  style: Record<string, HudStyleValue>,
): HudWidgetConfig {
  return { id, type, bindings, anchor, x, y, width, height, zIndex, visible: true, style };
}
