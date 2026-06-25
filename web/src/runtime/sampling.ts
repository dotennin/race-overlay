import type { ActivitySample, ActivityTrack, HudSample } from "./models";
import { secondsBetween } from "./time";

function lerp(start: number | null, end: number | null, ratio: number): number | null {
  if (start == null || end == null) {
    return null;
  }
  return start + (end - start) * ratio;
}

function roundHalfEven(value: number): number {
  const lower = Math.floor(value);
  const fraction = value - lower;
  if (fraction < 0.5) {
    return lower;
  }
  if (fraction > 0.5) {
    return lower + 1;
  }
  return lower % 2 === 0 ? lower : lower + 1;
}

function roundLerped(start: number | null, end: number | null, ratio: number): number | null {
  const value = lerp(start, end, ratio);
  return value == null ? null : roundHalfEven(value);
}

function boundingSamples(samples: ActivitySample[], when: string): [ActivitySample, ActivitySample] {
  if (samples.length < 2) {
    throw new Error("Need at least 2 samples");
  }
  const whenMs = new Date(when).getTime();
  for (let index = 0; index < samples.length - 1; index += 1) {
    const before = samples[index];
    const after = samples[index + 1];
    if (new Date(before.timestamp).getTime() <= whenMs && whenMs <= new Date(after.timestamp).getTime()) {
      return [before, after];
    }
  }
  return [samples[samples.length - 2], samples[samples.length - 1]];
}

export function sampleAt(activity: ActivityTrack, when: string): HudSample {
  const [before, after] = boundingSamples(activity.samples, when);
  const spanSeconds = secondsBetween(before.timestamp, after.timestamp);
  const ratio = spanSeconds === 0 ? 0 : secondsBetween(before.timestamp, when) / spanSeconds;
  const speedMps = lerp(before.speedMps, after.speedMps, ratio);
  return {
    timestamp: when,
    latitude: lerp(before.latitude, after.latitude, ratio),
    longitude: lerp(before.longitude, after.longitude, ratio),
    altitudeM: lerp(before.altitudeM, after.altitudeM, ratio),
    distanceM: lerp(before.distanceM, after.distanceM, ratio),
    speedMps,
    paceSecondsPerKm: speedMps ? 1000 / speedMps : null,
    heartRateBpm: roundLerped(before.heartRateBpm, after.heartRateBpm, ratio),
    cadenceSpm: roundLerped(before.cadenceSpm, after.cadenceSpm, ratio),
  };
}
