import { describe, expect, it } from "vitest";

import { alignClip } from "./alignment";
import type { ActivityTrack, VideoClip } from "./models";

describe("alignClip", () => {
  it("marks a clip that starts before the activity as partial", () => {
    const activity: ActivityTrack = {
      sport: "Running",
      laps: [],
      samples: [
        {
          timestamp: "2026-04-19T00:45:05.000Z",
          latitude: null,
          longitude: null,
          altitudeM: null,
          distanceM: 0,
          speedMps: 4,
          heartRateBpm: 120,
          cadenceSpm: 90,
        },
        {
          timestamp: "2026-04-19T00:45:15.000Z",
          latitude: null,
          longitude: null,
          altitudeM: null,
          distanceM: 40,
          speedMps: 4,
          heartRateBpm: 122,
          cadenceSpm: 92,
        },
      ],
    };
    const clip: VideoClip = {
      name: "before-start.MP4",
      creationTime: "2026-04-19T00:45:00.000Z",
      durationSeconds: 10,
      width: 1920,
      height: 1080,
      fps: 30,
    };

    const alignment = alignClip(activity, clip, {
      globalOffsetSeconds: 0,
      perVideoOffsetSeconds: 0,
    });

    expect(alignment.status).toBe("partial");
    expect(alignment.overlayStart).toBe("2026-04-19T00:45:05.000Z");
  });
});
