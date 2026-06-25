import { describe, expect, it } from "vitest";

import type { ActivityLap } from "./models";
import { lapWaterfallState } from "./lapWaterfall";

function addSeconds(start: string, seconds: number): string {
  return new Date(new Date(start).getTime() + seconds * 1000).toISOString();
}

function makeLap(startTime: string, index: number, durationSeconds = 300): ActivityLap {
  return {
    startTime,
    totalTimeSeconds: durationSeconds,
    distanceM: 1000 + index,
    avgHeartRateBpm: 120 + index,
    maxHeartRateBpm: 150 + index,
    maxSpeedMps: 4,
    elevationDeltaM: index,
    calories: 80,
  };
}

describe("lapWaterfallState", () => {
  it("returns zero opacity when no laps are completed", () => {
    const start = "2026-04-19T09:00:00.000Z";
    const state = lapWaterfallState([makeLap(start, 0)], addSeconds(start, 100));

    expect(state.opacity).toBe(0);
    expect(state.completedLaps).toEqual([]);
    expect(state.visibleRows).toEqual([]);
    expect(state.newestLapIndex).toBeNull();
  });

  it("applies Python-compatible fade and visible row windowing", () => {
    const start = "2026-04-19T09:00:00.000Z";
    const laps = Array.from({ length: 6 }, (_, index) => makeLap(addSeconds(start, index * 300), index));
    const state = lapWaterfallState(laps, addSeconds(start, 6 * 300 + 30), {
      visibleRows: 4,
      fadeAfterSeconds: 60,
    });

    expect(state.opacity).toBeCloseTo(0.5);
    expect(state.completedLaps).toHaveLength(6);
    expect(state.visibleRows.map((row) => row.lapIndex)).toEqual([2, 3, 4, 5]);
    expect(state.oldestRowDimmed).toBe(true);
    expect(state.visibleRows[0].isDimmed).toBe(true);
  });

  it("keeps previous rows during the scroll transition", () => {
    const start = "2026-04-19T09:00:00.000Z";
    const laps = Array.from({ length: 6 }, (_, index) => makeLap(addSeconds(start, index * 300), index));
    const state = lapWaterfallState(laps, addSeconds(start, 6 * 300 + 0.225), {
      visibleRows: 5,
      alwaysShow: true,
    });

    expect(state.opacity).toBe(1);
    expect(state.transitionProgress).toBeCloseTo(0.5);
    expect(state.transitionPreviousRows?.map((row) => row.lapIndex)).toEqual([0, 1, 2, 3, 4]);
    expect(state.visibleRows.map((row) => row.lapIndex)).toEqual([1, 2, 3, 4, 5]);
    expect(state.transitionPreviousRows?.[0].isDimmed).toBe(true);
  });

  it("rejects invalid visible row counts", () => {
    expect(() => lapWaterfallState([], "2026-04-19T09:00:00.000Z", { visibleRows: 0 })).toThrow(
      "visibleRows",
    );
  });
});
