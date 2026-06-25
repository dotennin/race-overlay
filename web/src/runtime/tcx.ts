import type { ActivityLap, ActivitySample, ActivityTrack } from "./models";
import { toIsoUtc } from "./time";

const TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2";
const EXT_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2";

function firstText(parent: Element, namespace: string, name: string): string | null {
  return parent.getElementsByTagNameNS(namespace, name)[0]?.textContent ?? null;
}

function childText(parent: Element, namespace: string, name: string): string | null {
  return childElement(parent, namespace, name)?.textContent ?? null;
}

function optionalFloatFromText(value: string | null): number | null {
  return value == null ? null : Number.parseFloat(value);
}

function optionalIntFromText(value: string | null): number | null {
  return value == null ? null : Number.parseInt(value, 10);
}

function optionalFloat(parent: Element, namespace: string, name: string): number | null {
  return optionalFloatFromText(firstText(parent, namespace, name));
}

function optionalInt(parent: Element, namespace: string, name: string): number | null {
  return optionalIntFromText(firstText(parent, namespace, name));
}

function optionalChildFloat(parent: Element, namespace: string, name: string): number | null {
  return optionalFloatFromText(childText(parent, namespace, name));
}

function optionalChildInt(parent: Element, namespace: string, name: string): number | null {
  return optionalIntFromText(childText(parent, namespace, name));
}

function childElement(parent: Element, namespace: string, name: string): Element | null {
  return Array.from(parent.children).find((child) => child.namespaceURI === namespace && child.localName === name) ?? null;
}

function heartRateValue(parent: Element, wrapperName: "AverageHeartRateBpm" | "MaximumHeartRateBpm" | "HeartRateBpm"): number | null {
  const wrapper = childElement(parent, TCX_NS, wrapperName);
  return wrapper ? optionalInt(wrapper, TCX_NS, "Value") : null;
}

function trackpointsIn(parent: Element): Element[] {
  return Array.from(parent.getElementsByTagNameNS(TCX_NS, "Trackpoint"));
}

function parseTime(value: string): string {
  return toIsoUtc(value);
}

function parseCadence(point: Element, sport: string): number | null {
  const runCadence = optionalInt(point, EXT_NS, "RunCadence");
  if (sport.toLowerCase() === "running") {
    return runCadence == null ? null : runCadence * 2;
  }
  return optionalInt(point, TCX_NS, "Cadence") ?? runCadence;
}

function deriveElevationDelta(lap: Element): number | null {
  const altitudes = trackpointsIn(lap)
    .map((point) => optionalFloat(point, TCX_NS, "AltitudeMeters"))
    .filter((value): value is number => value != null);
  if (altitudes.length < 2) {
    return null;
  }
  return altitudes[altitudes.length - 1] - altitudes[0];
}

function deriveTotalTimeSeconds(lap: Element): number {
  const times = trackpointsIn(lap)
    .map((point) => firstText(point, TCX_NS, "Time"))
    .filter((value): value is string => value != null)
    .map((value) => new Date(value).getTime());
  if (times.length < 2) {
    return 0;
  }
  return (times[times.length - 1] - times[0]) / 1000;
}

function deriveDistanceM(lap: Element): number {
  const distances = trackpointsIn(lap)
    .map((point) => optionalFloat(point, TCX_NS, "DistanceMeters"))
    .filter((value): value is number => value != null);
  if (!distances.length) {
    return 0;
  }
  return distances[distances.length - 1] - distances[0];
}

function deriveMaxSpeedMps(lap: Element): number | null {
  const speeds = trackpointsIn(lap)
    .map((point) => optionalFloat(point, EXT_NS, "Speed"))
    .filter((value): value is number => value != null);
  return speeds.length ? Math.max(...speeds) : null;
}

function parseLap(lap: Element): ActivityLap {
  const startTime = lap.getAttribute("StartTime");
  if (!startTime) {
    throw new Error("TCX lap is missing StartTime");
  }
  return {
    startTime: parseTime(startTime),
    totalTimeSeconds: optionalChildFloat(lap, TCX_NS, "TotalTimeSeconds") ?? deriveTotalTimeSeconds(lap),
    distanceM: optionalChildFloat(lap, TCX_NS, "DistanceMeters") ?? deriveDistanceM(lap),
    avgHeartRateBpm: heartRateValue(lap, "AverageHeartRateBpm"),
    maxHeartRateBpm: heartRateValue(lap, "MaximumHeartRateBpm"),
    maxSpeedMps: optionalChildFloat(lap, TCX_NS, "MaximumSpeed") ?? deriveMaxSpeedMps(lap),
    elevationDeltaM: deriveElevationDelta(lap),
    calories: optionalChildInt(lap, TCX_NS, "Calories"),
  };
}

export function readTcx(xml: string): ActivityTrack {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  const parseError = doc.getElementsByTagName("parsererror")[0];
  if (parseError) {
    throw new Error("invalid TCX XML");
  }
  const activity = doc.getElementsByTagNameNS(TCX_NS, "Activity")[0];
  if (!activity) {
    throw new Error("TCX activity is missing");
  }
  const sport = activity.getAttribute("Sport") ?? "Running";
  const samples: ActivitySample[] = trackpointsIn(activity).map((point) => ({
    timestamp: parseTime(firstText(point, TCX_NS, "Time") ?? ""),
    latitude: optionalFloat(point, TCX_NS, "LatitudeDegrees"),
    longitude: optionalFloat(point, TCX_NS, "LongitudeDegrees"),
    altitudeM: optionalFloat(point, TCX_NS, "AltitudeMeters"),
    distanceM: optionalFloat(point, TCX_NS, "DistanceMeters"),
    speedMps: optionalFloat(point, EXT_NS, "Speed"),
    heartRateBpm: heartRateValue(point, "HeartRateBpm"),
    cadenceSpm: parseCadence(point, sport),
  }));
  const laps = Array.from(activity.getElementsByTagNameNS(TCX_NS, "Lap")).map(parseLap);
  return { sport, samples, laps };
}
