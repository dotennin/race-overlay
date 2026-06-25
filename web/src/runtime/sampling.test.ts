import { describe, expect, it } from "vitest";

import type { ActivityTrack } from "./models";
import { sampleAt } from "./sampling";

describe("sampleAt", () => {
  it("interpolates distance, heart rate, speed, and altitude", () => {
    const activity: ActivityTrack = {
      sport: "Running",
      laps: [],
      samples: [
        {
          timestamp: "2026-04-19T00:45:05.000Z",
          latitude: 36,
          longitude: 140,
          altitudeM: -1.4,
          distanceM: 0,
          speedMps: 4,
          heartRateBpm: 120,
          cadenceSpm: 90,
        },
        {
          timestamp: "2026-04-19T00:45:15.000Z",
          latitude: 36.1,
          longitude: 140.1,
          altitudeM: -1,
          distanceM: 40,
          speedMps: 5,
          heartRateBpm: 130,
          cadenceSpm: 92,
        },
      ],
    };

    const sample = sampleAt(activity, "2026-04-19T00:45:10.000Z");

    expect(sample.distanceM).toBeCloseTo(20);
    expect(sample.heartRateBpm).toBe(125);
    expect(sample.speedMps).toBeCloseTo(4.5);
    expect(sample.altitudeM).toBeCloseTo(-1.2);
    expect(sample.paceSecondsPerKm).toBeCloseTo(222.22, 2);
  });

  it("matches Python round() for exactly half-way integer metrics", () => {
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
          speedMps: null,
          heartRateBpm: 103,
          cadenceSpm: 91,
        },
        {
          timestamp: "2026-04-19T00:45:06.000Z",
          latitude: null,
          longitude: null,
          altitudeM: null,
          distanceM: 1,
          speedMps: null,
          heartRateBpm: 102,
          cadenceSpm: 92,
        },
      ],
    };

    const sample = sampleAt(activity, "2026-04-19T00:45:05.500Z");

    expect(sample.heartRateBpm).toBe(102);
    expect(sample.cadenceSpm).toBe(92);
  });
});
