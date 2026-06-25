import { describe, expect, it } from "vitest";

import { broadcastRunnerPreset, serializeHudConfig } from "./hudConfig";

describe("HUD config portability", () => {
  it("provides the Python broadcast-runner preset shape", () => {
    const preset = broadcastRunnerPreset();

    expect(preset.preset).toBe("broadcast-runner");
    expect(preset.theme).toMatchObject({
      textRgba: [247, 251, 255, 255],
      fontFamily: "broadcast_value",
      valueFontWeight: "bold",
      showUnits: true,
    });
    expect(preset.widgets.map((widget) => widget.id)).toEqual([
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
    ]);
    expect(preset.widgets.find((widget) => widget.id === "heart-rate-stat")).toMatchObject({
      type: "stat_block",
      bindings: { value: "heart_rate_bpm" },
      anchor: "top-right",
      x: 1092,
      y: 118,
      width: 152,
      height: 82,
      zIndex: 30,
      visible: true,
      style: { label: "Heart rate", unit: "BPM", align: "right" },
    });
  });

  it("serializes to Python-compatible snake_case keys", () => {
    expect(serializeHudConfig(broadcastRunnerPreset()).widgets[0]).toMatchObject({
      id: "time-chip",
      type: "context_card",
      z_index: 36,
      bindings: { value: "timestamp" },
      style: { variant: "timestamp_chip", format: "%Y/%m/%d %H:%M:%S" },
    });
  });
});
