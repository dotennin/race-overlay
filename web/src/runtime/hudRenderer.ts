import type { HudConfig, HudWidgetConfig } from "./hudConfig";
import type { LapWaterfallRow, LapWaterfallState } from "./lapWaterfall";
import type { HudSample } from "./models";
import {
  projectRoutePoints,
  resolveRouteProjection,
  splitRoutePoints,
  type ProjectedPoint,
  type RoutePoint,
} from "./routeMap";

export interface DrawHudFrameOptions {
  sample: HudSample | null;
  hasVideo: boolean;
  hudConfig: HudConfig;
  routePoints?: RoutePoint[];
  lapStates?: Record<string, LapWaterfallState>;
  clearCanvas?: boolean;
}

function formatDistance(sample: HudSample): string {
  if (sample.distanceM == null) {
    return "-- km";
  }
  return `${(sample.distanceM / 1000).toFixed(2)} km`;
}

function rgba(value: unknown, fallback: string): string {
  if (!Array.isArray(value) || value.length !== 4 || !value.every((item) => typeof item === "number")) {
    return fallback;
  }
  return `rgba(${value[0]}, ${value[1]}, ${value[2]}, ${value[3] / 255})`;
}

function styleString(widget: HudWidgetConfig, key: string, fallback = ""): string {
  const value = widget.style[key];
  return typeof value === "string" ? value : fallback;
}

function styleNumber(widget: HudWidgetConfig, key: string, fallback: number): number {
  const value = widget.style[key];
  return typeof value === "number" ? value : fallback;
}

function styleBoolean(widget: HudWidgetConfig, key: string, fallback: boolean): boolean {
  const value = widget.style[key];
  return typeof value === "boolean" ? value : fallback;
}

function widgetBounds(
  widget: HudWidgetConfig,
  canvas: HTMLCanvasElement,
): { left: number; top: number; width: number; height: number } {
  const left = widget.anchor.includes("right") ? widget.x + (canvas.width - 1280) : widget.x;
  const top = widget.anchor.includes("bottom") ? widget.y + (canvas.height - 720) : widget.y;
  return { left, top, width: widget.width, height: widget.height };
}

function boundValue(sample: HudSample | null, binding: string): number | string | null {
  if (!sample) {
    return null;
  }
  switch (binding) {
    case "altitude_m":
      return sample.altitudeM;
    case "cadence_spm":
      return sample.cadenceSpm;
    case "distance_m":
      return sample.distanceM;
    case "heart_rate_bpm":
      return sample.heartRateBpm;
    case "pace_seconds_per_km":
      return sample.paceSecondsPerKm;
    case "speed_mps":
      return sample.speedMps;
    case "timestamp":
      return sample.timestamp;
    default:
      return null;
  }
}

function formatWidgetValue(widget: HudWidgetConfig, value: number | string | null): string {
  if (value == null) {
    return "--";
  }
  const binding = widget.bindings.value;
  if (binding === "timestamp") {
    return String(value);
  }
  if (typeof value !== "number") {
    return value;
  }
  if (binding === "distance_m" && styleString(widget, "unit").toUpperCase() === "KM") {
    return (value / 1000).toFixed(styleNumber(widget, "decimals", 2));
  }
  if (binding === "pace_seconds_per_km") {
    const minutes = Math.floor(value / 60);
    const seconds = Math.round(value % 60).toString().padStart(2, "0");
    return `${minutes}:${seconds}`;
  }
  if (binding === "speed_mps") {
    return value.toFixed(1);
  }
  return Math.round(value).toString();
}

function drawPanel(context: CanvasRenderingContext2D, left: number, top: number, width: number, height: number): void {
  context.fillStyle = "rgba(8, 12, 20, 0.72)";
  context.fillRect(left, top, width, height);
}

function drawStatBlock(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  widget: HudWidgetConfig,
  sample: HudSample | null,
  theme: HudConfig["theme"],
): void {
  const { left, top, width, height } = widgetBounds(widget, canvas);
  drawPanel(context, left, top, width, height);
  context.fillStyle = rgba(theme.textRgba, "#f7fbff");
  context.font = `${theme.titleFontWeight === "bold" ? "700" : "500"} ${theme.titleFontSizePx ?? 16}px sans-serif`;
  context.fillText(styleString(widget, "label"), left + 14, top + 24);
  context.font = `${theme.valueFontWeight === "bold" ? "700" : "500"} ${theme.valueFontSizePx ?? 32}px sans-serif`;
  context.fillText(formatWidgetValue(widget, boundValue(sample, widget.bindings.value)), left + 14, top + 58);
  const unit = styleString(widget, "unit");
  if (unit && theme.showUnits) {
    context.font = `${theme.unitFontWeight === "bold" ? "700" : "500"} ${theme.unitFontSizePx ?? 13}px sans-serif`;
    context.fillText(unit, left + width - 46, top + height - 14);
  }
}

function drawMetricCard(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  widget: HudWidgetConfig,
  sample: HudSample | null,
  theme: HudConfig["theme"],
): void {
  const { left, top, width, height } = widgetBounds(widget, canvas);
  drawPanel(context, left, top, width, height);
  context.fillStyle = rgba(theme.textRgba, "#f7fbff");
  context.font = `${theme.titleFontWeight === "bold" ? "700" : "500"} 14px sans-serif`;
  context.fillText(styleString(widget, "label"), left + 12, top + 22);
  context.font = `${theme.valueFontWeight === "bold" ? "700" : "500"} 24px sans-serif`;
  context.fillText(formatWidgetValue(widget, boundValue(sample, widget.bindings.value)), left + 12, top + 52);
}

function drawProgressBar(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  widget: HudWidgetConfig,
  sample: HudSample | null,
  theme: HudConfig["theme"],
): void {
  const { left, top, width, height } = widgetBounds(widget, canvas);
  const distance = typeof sample?.distanceM === "number" ? sample.distanceM : 0;
  const progress = Math.min(Math.max(distance / 5000, 0), 1);
  context.fillStyle = rgba(widget.style.rail_rgba, "rgba(8, 12, 20, 0.86)");
  context.fillRect(left, top + height - 18, width, 10);
  context.fillStyle = rgba(widget.style.fill_rgba, "#22ff8a");
  context.fillRect(left, top + height - 18, width * progress, 10);
  context.fillStyle = rgba(theme.textRgba, "#f7fbff");
  context.font = "700 18px sans-serif";
  context.fillText(styleString(widget, "label", "Distance"), left, top + 22);
  context.fillText(sample ? formatDistance(sample).toUpperCase() : "-- KM", left + width - 92, top + 22);
}

function drawContextCard(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  widget: HudWidgetConfig,
  sample: HudSample | null,
  theme: HudConfig["theme"],
): void {
  const { left, top, width, height } = widgetBounds(widget, canvas);
  drawPanel(context, left, top, width, height);
  context.fillStyle = rgba(theme.textRgba, "#f7fbff");
  context.font = "600 16px sans-serif";
  context.fillText(sample?.timestamp ?? theme.noteText, left + 14, top + 34);
}

function drawPolyline(context: CanvasRenderingContext2D, points: ProjectedPoint[]): void {
  if (points.length < 2) {
    return;
  }
  context.beginPath();
  context.moveTo(points[0][0], points[0][1]);
  for (const point of points.slice(1)) {
    context.lineTo(point[0], point[1]);
  }
  context.stroke();
}

function routeMapZoomPercent(widget: HudWidgetConfig): number {
  const value = widget.style.zoom_percent;
  return typeof value === "number" ? value : 100;
}

function drawRouteMap(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  widget: HudWidgetConfig,
  sample: HudSample | null,
  routePoints: RoutePoint[] | undefined,
): void {
  const { left, top, width, height } = widgetBounds(widget, canvas);
  context.fillStyle = rgba(widget.style.background_rgba, "rgba(6, 10, 18, 0.58)");
  context.fillRect(left, top, width, height);
  if (!routePoints || routePoints.length < 2) {
    return;
  }

  const label = styleString(widget, "label");
  const mapLeft = left + 12;
  const mapTop = top + (label ? 36 : 12);
  const mapRight = left + width - 12;
  const mapBottom = top + height - 12;
  const projected = projectRoutePoints(routePoints, {
    left: mapLeft,
    top: mapTop,
    right: mapRight,
    bottom: mapBottom,
    zoomPercent: routeMapZoomPercent(widget),
  });
  context.lineWidth = 4;
  context.strokeStyle = rgba(widget.style.remaining_rgba, "#0d90c3");
  drawPolyline(context, projected.points);

  const projection = sample ? resolveRouteProjection(routePoints, sample) : null;
  if (!projection) {
    return;
  }
  const split = splitRoutePoints(routePoints, projection);
  context.strokeStyle = rgba(widget.style.completed_rgba, "#22ff8a");
  drawPolyline(context, split.completed.map(projected.project));
  const marker = projected.project(projection.point);
  context.fillStyle = "#e4ffee";
  context.beginPath();
  context.arc(marker[0], marker[1], 5, 0, Math.PI * 2);
  context.fill();
}

function lapWaterfallColumns(widget: HudWidgetConfig): string[] {
  const columns = ["lap"];
  if (styleBoolean(widget, "show_distance", true)) {
    columns.push("distance");
  }
  if (styleBoolean(widget, "show_pace", true)) {
    columns.push("pace");
  }
  if (styleBoolean(widget, "show_elevation", true)) {
    columns.push("elevation");
  }
  if (styleBoolean(widget, "show_heart_rate", true)) {
    columns.push("heart_rate");
  }
  return columns;
}

function lapWaterfallHeader(column: string): string {
  switch (column) {
    case "lap":
      return "Lap";
    case "distance":
      return "Dist";
    case "pace":
      return "Pace";
    case "elevation":
      return "Elev";
    case "heart_rate":
      return "HR";
    default:
      return column;
  }
}

function formatLapPace(row: LapWaterfallRow): string {
  if (row.lap.distanceM <= 0 || row.lap.totalTimeSeconds <= 0) {
    return "--";
  }
  const secondsPerKm = row.lap.totalTimeSeconds / (row.lap.distanceM / 1000);
  const minutes = Math.floor(secondsPerKm / 60);
  const seconds = Math.round(secondsPerKm % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function lapWaterfallValue(row: LapWaterfallRow, column: string): string {
  switch (column) {
    case "lap":
      return String(row.lapIndex + 1);
    case "distance":
      return (row.lap.distanceM / 1000).toFixed(2);
    case "pace":
      return formatLapPace(row);
    case "elevation":
      if (row.lap.elevationDeltaM == null) {
        return "--";
      }
      return `${row.lap.elevationDeltaM >= 0 ? "+" : ""}${Math.round(row.lap.elevationDeltaM)}`;
    case "heart_rate":
      return row.lap.avgHeartRateBpm == null ? "--" : String(row.lap.avgHeartRateBpm);
    default:
      return "--";
  }
}

function drawLapWaterfall(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  widget: HudWidgetConfig,
  theme: HudConfig["theme"],
  state: LapWaterfallState | null,
): void {
  if (!state || state.opacity <= 0 || !state.visibleRows.length) {
    return;
  }
  const { left, top, width, height } = widgetBounds(widget, canvas);
  drawPanel(context, left, top, width, height);
  const columns = lapWaterfallColumns(widget);
  const colWidth = Math.max(34, Math.floor((width - 24) / columns.length));
  const rowHeight = 26;
  context.fillStyle = rgba(theme.textRgba, "#f7fbff");
  context.font = `${theme.titleFontWeight === "bold" ? "700" : "500"} 12px sans-serif`;
  columns.forEach((column, index) => {
    context.fillText(lapWaterfallHeader(column), left + 12 + index * colWidth, top + 22);
  });
  context.font = `${theme.valueFontWeight === "bold" ? "700" : "500"} 14px sans-serif`;
  state.visibleRows.forEach((row, rowIndex) => {
    const rowTop = top + 46 + rowIndex * rowHeight;
    columns.forEach((column, columnIndex) => {
      context.fillText(lapWaterfallValue(row, column), left + 12 + columnIndex * colWidth, rowTop);
    });
  });
}

function drawConfiguredWidget(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  widget: HudWidgetConfig,
  sample: HudSample | null,
  theme: HudConfig["theme"],
  lapStates: Record<string, LapWaterfallState> | undefined,
  routePoints: RoutePoint[] | undefined,
): void {
  if (widget.type === "stat_block") {
    drawStatBlock(context, canvas, widget, sample, theme);
    return;
  }
  if (widget.type === "metric_card") {
    drawMetricCard(context, canvas, widget, sample, theme);
    return;
  }
  if (widget.type === "progress_bar") {
    drawProgressBar(context, canvas, widget, sample, theme);
    return;
  }
  if (widget.type === "context_card") {
    drawContextCard(context, canvas, widget, sample, theme);
    return;
  }
  if (widget.type === "route_map") {
    drawRouteMap(context, canvas, widget, sample, routePoints);
    return;
  }
  if (widget.type === "lap_waterfall") {
    drawLapWaterfall(context, canvas, widget, theme, lapStates?.[widget.id] ?? null);
  }
}

export function drawHudFrame(canvas: HTMLCanvasElement, options: DrawHudFrameOptions): void {
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  if (options.clearCanvas ?? true) {
    context.clearRect(0, 0, canvas.width, canvas.height);
  }
  if (!options.hasVideo) {
    context.fillStyle = "#18201b";
    context.fillRect(0, 0, canvas.width, canvas.height);
  }
  const visibleWidgets = [...options.hudConfig.widgets]
    .filter((widget) => widget.visible)
    .sort((left, right) => left.zIndex - right.zIndex);
  for (const widget of visibleWidgets) {
    drawConfiguredWidget(
      context,
      canvas,
      widget,
      options.sample,
      options.hudConfig.theme,
      options.lapStates,
      options.routePoints,
    );
  }
}
