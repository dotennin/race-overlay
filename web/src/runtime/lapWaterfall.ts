import type { HudConfig, HudWidgetConfig } from "./hudConfig";
import type { ActivityLap } from "./models";

export const LAP_WATERFALL_DEFAULT_VISIBLE_ROWS = 5;
export const LAP_WATERFALL_DEFAULT_FADE_AFTER_SECONDS = 5;
export const LAP_WATERFALL_SCROLL_SECONDS = 0.45;

export interface LapWaterfallRow {
  lap: ActivityLap;
  lapIndex: number;
  isDimmed: boolean;
}

export interface LapWaterfallState {
  completedLaps: ActivityLap[];
  visibleRows: LapWaterfallRow[];
  newestLapIndex: number | null;
  oldestRowDimmed: boolean;
  opacity: number;
  transitionPreviousRows: LapWaterfallRow[] | null;
  transitionProgress: number;
}

export interface LapWaterfallOptions {
  visibleRows?: number;
  alwaysShow?: boolean;
  fadeAfterSeconds?: number;
}

function widgetVisibleRows(widget: HudWidgetConfig): number {
  const value = widget.style.visible_rows;
  if (value == null) {
    return LAP_WATERFALL_DEFAULT_VISIBLE_ROWS;
  }
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
    throw new Error(`widget '${widget.id}' style.visible_rows must be a positive integer`);
  }
  return value;
}

function widgetAlwaysShow(widget: HudWidgetConfig): boolean {
  const value = widget.style.always_show;
  if (value == null) {
    return false;
  }
  if (typeof value !== "boolean") {
    throw new Error(`widget '${widget.id}' style.always_show must be a boolean`);
  }
  return value;
}

function widgetFadeAfterSeconds(widget: HudWidgetConfig): number {
  const value = widget.style.fade_after_seconds;
  if (value == null) {
    return LAP_WATERFALL_DEFAULT_FADE_AFTER_SECONDS;
  }
  if (typeof value !== "number" || value <= 0) {
    throw new Error(`widget '${widget.id}' style.fade_after_seconds must be a positive number`);
  }
  return value;
}

function addSeconds(value: string, seconds: number): number {
  return new Date(value).getTime() + seconds * 1000;
}

function secondsBetween(leftMs: number, rightMs: number): number {
  return (leftMs - rightMs) / 1000;
}

function row(lap: ActivityLap, lapIndex: number, isDimmed: boolean): LapWaterfallRow {
  return { lap, lapIndex, isDimmed };
}

export function lapWaterfallState(
  laps: ActivityLap[],
  when: string,
  options: LapWaterfallOptions = {},
): LapWaterfallState {
  const visibleRows = options.visibleRows ?? LAP_WATERFALL_DEFAULT_VISIBLE_ROWS;
  const alwaysShow = options.alwaysShow ?? false;
  const fadeAfterSeconds = options.fadeAfterSeconds ?? LAP_WATERFALL_DEFAULT_FADE_AFTER_SECONDS;
  if (!Number.isInteger(visibleRows) || visibleRows < 1) {
    throw new Error(`visibleRows must be >= 1, got ${visibleRows}`);
  }

  const whenMs = new Date(when).getTime();
  const completed = laps
    .map((lap, index) => ({ lap, index }))
    .filter(({ lap }) => addSeconds(lap.startTime, lap.totalTimeSeconds) <= whenMs);

  if (!completed.length) {
    return {
      completedLaps: [],
      visibleRows: [],
      newestLapIndex: null,
      oldestRowDimmed: false,
      opacity: 0,
      transitionPreviousRows: null,
      transitionProgress: 1,
    };
  }

  const newest = completed[completed.length - 1];
  const newestLapEndMs = addSeconds(newest.lap.startTime, newest.lap.totalTimeSeconds);
  const elapsedSinceEnd = secondsBetween(whenMs, newestLapEndMs);
  const opacity = alwaysShow
    ? 1
    : elapsedSinceEnd >= fadeAfterSeconds
      ? 0
      : Math.max(0, 1 - elapsedSinceEnd / fadeAfterSeconds);

  const window = completed.slice(-visibleRows);
  const windowFull = completed.length >= visibleRows;
  let transitionPreviousRows: LapWaterfallRow[] | null = null;
  let transitionProgress = 1;

  if (elapsedSinceEnd >= 0 && elapsedSinceEnd < LAP_WATERFALL_SCROLL_SECONDS) {
    transitionProgress = Math.max(0, Math.min(elapsedSinceEnd / LAP_WATERFALL_SCROLL_SECONDS, 1));
    if (windowFull && completed.length > visibleRows) {
      transitionPreviousRows = completed
        .slice(-visibleRows - 1, -1)
        .map(({ lap, index }, position) => row(lap, index, position === 0));
    }
  }

  return {
    completedLaps: completed.map(({ lap }) => lap),
    visibleRows: window.map(({ lap, index }, position) => row(lap, index, windowFull && position === 0)),
    newestLapIndex: newest.index,
    oldestRowDimmed: windowFull,
    opacity,
    transitionPreviousRows,
    transitionProgress,
  };
}

export function lapWaterfallStatesForWidgets(
  hudConfig: HudConfig,
  laps: ActivityLap[],
  when: string,
): Record<string, LapWaterfallState> {
  return Object.fromEntries(
    hudConfig.widgets
      .filter((widget) => widget.visible && widget.type === "lap_waterfall")
      .map((widget) => [
        widget.id,
        lapWaterfallState(laps, when, {
          visibleRows: widgetVisibleRows(widget),
          alwaysShow: widgetAlwaysShow(widget),
          fadeAfterSeconds: widgetFadeAfterSeconds(widget),
        }),
      ]),
  );
}
