import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { alignClip } from "./alignment";
import { broadcastRunnerPreset, serializeHudConfig } from "./hudConfig";
import { lapWaterfallState } from "./lapWaterfall";
import type { ActivityTrack, VideoClip } from "./models";
import contract from "../../../tests/fixtures/portability_contract.json";
import { resolveRouteProjection, splitRoutePoints } from "./routeMap";
import { sampleAt } from "./sampling";
import { readTcx } from "./tcx";

type Contract = typeof contract;

function toBrowserClip(clip: Contract["alignClip"][number]["clip"]): VideoClip {
  return {
    name: clip.path,
    creationTime: clip.creationTime,
    durationSeconds: clip.durationSeconds,
    width: clip.width,
    height: clip.height,
    fps: clip.fps,
  };
}

describe("Python portability contract", () => {
  it("parses the TCX fixture into the same browser model shape", () => {
    const xml = readFileSync(resolve("..", "tests", "fixtures", "sample_activity.tcx"), "utf8");

    expect(readTcx(xml)).toEqual(contract.activity);
  });

  it("parses portable lap fixture with Python-compatible derived lap fields", () => {
    const xml = readFileSync(resolve("..", "tests", "fixtures", "portable_laps.tcx"), "utf8");

    expect(readTcx(xml)).toEqual(contract.lapActivity);
  });

  it("samples activity data with Python-compatible interpolation", () => {
    const activity = contract.activity as ActivityTrack;

    for (const example of contract.sampleAt) {
      expect(sampleAt(activity, example.when)).toEqual(example.sample);
    }
  });

  it("classifies clip alignment with Python-compatible boundaries", () => {
    const activity = contract.activity as ActivityTrack;

    for (const example of contract.alignClip) {
      const clip = toBrowserClip(example.clip);

      expect(alignClip(activity, clip, { globalOffsetSeconds: 0, perVideoOffsetSeconds: 0 })).toEqual({
        clip,
        status: example.status,
        clipStart: example.clipStart,
        clipEnd: example.clipEnd,
        overlayStart: example.overlayStart,
        overlayEnd: example.overlayEnd,
      });
    }
  });

  it("serializes the default HUD preset to the Python contract", () => {
    expect(serializeHudConfig(broadcastRunnerPreset())).toEqual(contract.hudPreset);
  });

  it("computes lap waterfall state with Python-compatible semantics", () => {
    for (const example of contract.lapWaterfallState) {
      expect(
        lapWaterfallState(contract.lapActivity.laps, example.when, {
          visibleRows: 2,
          alwaysShow: true,
        }),
      ).toEqual(example.state);
    }
  });

  it("projects route map positions with Python-compatible semantics", () => {
    const routePoints = contract.activity.samples
      .filter((sample) => sample.latitude != null && sample.longitude != null)
      .map((sample) => [sample.latitude, sample.longitude] as const);

    for (const example of contract.routeProjection) {
      const projection = resolveRouteProjection(routePoints, example.sample);

      expect(projection).toEqual(example.projection);
      expect(splitRoutePoints(routePoints, projection!)).toEqual(example.split);
    }
  });
});
