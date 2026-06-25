import { describe, expect, it } from "vitest";

import type { HudSample } from "./models";
import { projectRoutePoints, resolveRouteProjection, splitRoutePoints } from "./routeMap";

function sample(latitude: number | null, longitude: number | null): HudSample {
  return {
    timestamp: "2026-04-19T09:48:10.000Z",
    latitude,
    longitude,
    altitudeM: 25,
    distanceM: 24600,
    speedMps: 3.58,
    paceSecondsPerKm: 278,
    heartRateBpm: 162,
    cadenceSpm: 178,
  };
}

describe("route map runtime", () => {
  it("resolves the current sample onto the nearest route segment", () => {
    const routePoints = [
      [35, 139],
      [35.5, 139.5],
      [36, 140],
    ] as const;

    expect(resolveRouteProjection(routePoints, sample(35.5, 139.5))).toEqual({
      point: [35.5, 139.5],
      tangent: [0.5, 0.5],
      segmentStart: [35, 139],
      segmentEnd: [35.5, 139.5],
      segmentIndex: 0,
    });
  });

  it("returns null when current GPS is missing", () => {
    expect(resolveRouteProjection([[35, 139], [36, 140]], sample(null, 139.5))).toBeNull();
  });

  it("splits route points at the projected current position", () => {
    const routePoints = [
      [35, 139],
      [35.5, 139.5],
      [36, 140],
    ] as const;
    const projection = resolveRouteProjection(routePoints, sample(35.75, 139.75));
    expect(projection?.segmentIndex).toBe(1);

    expect(splitRoutePoints(routePoints, projection!)).toEqual({
      completed: [
        [35, 139],
        [35.5, 139.5],
        [35.75, 139.75],
      ],
      remaining: [
        [35.75, 139.75],
        [36, 140],
      ],
    });
  });

  it("projects route points into a bounded widget area while preserving aspect", () => {
    const projected = projectRoutePoints(
      [
        [35, 139],
        [35.5, 139.5],
        [36, 140],
      ],
      { left: 12, top: 12, right: 108, bottom: 108, zoomPercent: 100 },
    );

    expect(projected.project([36, 140])).toEqual([108, 12]);
    expect(projected.project([35, 139])).toEqual([12, 108]);
    expect(projected.points).toEqual([
      [12, 108],
      [60, 60],
      [108, 12],
    ]);
  });
});
