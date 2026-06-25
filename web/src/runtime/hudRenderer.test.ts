import { describe, expect, it } from "vitest";

import { broadcastRunnerPreset } from "./hudConfig";
import { drawHudFrame } from "./hudRenderer";
import { lapWaterfallState } from "./lapWaterfall";
import type { ActivityLap, HudSample } from "./models";

function sample(): HudSample {
  return {
    timestamp: "2026-04-19T00:45:00.000Z",
    latitude: 36,
    longitude: 140,
    altitudeM: 10,
    distanceM: 1200,
    speedMps: 4,
    paceSecondsPerKm: 250,
    heartRateBpm: 128,
    cadenceSpm: 180,
  };
}

function lap(index: number): ActivityLap {
  return {
    startTime: new Date(new Date("2026-04-19T09:00:00.000Z").getTime() + index * 300_000).toISOString(),
    totalTimeSeconds: 300,
    distanceM: 1000,
    avgHeartRateBpm: 120 + index,
    maxHeartRateBpm: 150 + index,
    maxSpeedMps: 4,
    elevationDeltaM: index % 2 === 0 ? 5 : -3,
    calories: 80,
  };
}

describe("HUD renderer", () => {
  it("draws visible widgets from HudConfig", () => {
    const hudConfig = broadcastRunnerPreset();
    hudConfig.widgets = hudConfig.widgets.filter((widget) => widget.id === "heart-rate-stat");
    const canvas = document.createElement("canvas");
    canvas.width = 960;
    canvas.height = 540;
    globalThis.__canvasText = [];

    drawHudFrame(canvas, {
      sample: sample(),
      hasVideo: false,
      hudConfig,
    });

    expect(globalThis.__canvasText).toContain("Heart rate");
    expect(globalThis.__canvasText).toContain("128");
    expect(globalThis.__canvasText).toContain("BPM");
  });

  it("draws lap waterfall rows from widget-scoped lap state", () => {
    const hudConfig = broadcastRunnerPreset();
    hudConfig.widgets = [
      {
        id: "lap-table",
        type: "lap_waterfall",
        bindings: { value: "laps" },
        anchor: "top-left",
        x: 20,
        y: 20,
        width: 360,
        height: 180,
        zIndex: 50,
        visible: true,
        style: { show_distance: true, show_pace: true, show_elevation: true, show_heart_rate: true },
      },
    ];
    const laps = [lap(0), lap(1)];
    const canvas = document.createElement("canvas");
    canvas.width = 960;
    canvas.height = 540;
    globalThis.__canvasText = [];

    drawHudFrame(canvas, {
      sample: sample(),
      hasVideo: false,
      hudConfig,
      lapStates: {
        "lap-table": lapWaterfallState(laps, "2026-04-19T09:10:01.000Z", { alwaysShow: true }),
      },
    });

    expect(globalThis.__canvasText).toContain("Lap");
    expect(globalThis.__canvasText).toContain("Dist");
    expect(globalThis.__canvasText).toContain("Pace");
    expect(globalThis.__canvasText).toContain("Elev");
    expect(globalThis.__canvasText).toContain("HR");
    expect(globalThis.__canvasText).toContain("1");
    expect(globalThis.__canvasText).toContain("2");
    expect(globalThis.__canvasText).toContain("1.00");
    expect(globalThis.__canvasText).toContain("+5");
    expect(globalThis.__canvasText).toContain("-3");
  });

  it("draws route map polylines and current position marker from route points", () => {
    const hudConfig = broadcastRunnerPreset();
    hudConfig.widgets = hudConfig.widgets.filter((widget) => widget.id === "route-map");
    const canvas = document.createElement("canvas");
    canvas.width = 960;
    canvas.height = 540;
    globalThis.__canvasLinePoints = [];
    globalThis.__canvasArcCenters = [];

    drawHudFrame(canvas, {
      sample: {
        ...sample(),
        latitude: 35.5,
        longitude: 139.5,
      },
      hasVideo: false,
      hudConfig,
      routePoints: [
        [35, 139],
        [35.5, 139.5],
        [36, 140],
      ],
    });

    expect(globalThis.__canvasLinePoints.length).toBeGreaterThanOrEqual(4);
    expect(globalThis.__canvasArcCenters).toContainEqual([119, 586]);
  });
});
