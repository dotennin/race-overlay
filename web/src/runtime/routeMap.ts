import type { HudSample } from "./models";

export type RoutePoint = readonly [number, number];
export type ProjectedPoint = [number, number];

export interface RouteProjection {
  point: ProjectedPoint;
  tangent: ProjectedPoint;
  segmentStart: ProjectedPoint;
  segmentEnd: ProjectedPoint;
  segmentIndex: number;
}

export interface RouteProjectionBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
  zoomPercent: number;
}

export interface ProjectedRoute {
  points: ProjectedPoint[];
  project: (point: RoutePoint) => ProjectedPoint;
}

function distanceSquared(left: RoutePoint, right: RoutePoint): number {
  return (left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2;
}

function isZeroVector(vector: RoutePoint): boolean {
  return Math.abs(vector[0]) <= 1e-12 && Math.abs(vector[1]) <= 1e-12;
}

function projectPointOntoSegment(current: RoutePoint, start: RoutePoint, end: RoutePoint): ProjectedPoint {
  const deltaLat = end[0] - start[0];
  const deltaLon = end[1] - start[1];
  const segmentLengthSq = deltaLat * deltaLat + deltaLon * deltaLon;
  if (segmentLengthSq <= 0) {
    return [start[0], start[1]];
  }
  const projection = ((current[0] - start[0]) * deltaLat + (current[1] - start[1]) * deltaLon) / segmentLengthSq;
  const clamped = Math.min(Math.max(projection, 0), 1);
  return [start[0] + deltaLat * clamped, start[1] + deltaLon * clamped];
}

export function resolveRouteProjection(routePoints: readonly RoutePoint[], sample: HudSample): RouteProjection | null {
  if (sample.latitude == null || sample.longitude == null || routePoints.length < 2) {
    return null;
  }
  const current: RoutePoint = [sample.latitude, sample.longitude];
  let closestPoint: ProjectedPoint = [routePoints[routePoints.length - 1][0], routePoints[routePoints.length - 1][1]];
  let closestSegmentStart: ProjectedPoint = [routePoints[0][0], routePoints[0][1]];
  let closestSegmentEnd: ProjectedPoint = [routePoints[1][0], routePoints[1][1]];
  let closestTangent: ProjectedPoint = [0, 0];
  let closestDistanceSq = Number.POSITIVE_INFINITY;
  let segmentIndex = 0;

  for (let index = 0; index < routePoints.length - 1; index += 1) {
    const segmentStart = routePoints[index];
    const segmentEnd = routePoints[index + 1];
    const candidate = projectPointOntoSegment(current, segmentStart, segmentEnd);
    const candidateDistanceSq = distanceSquared(current, candidate);
    const candidateTangent: ProjectedPoint = [segmentEnd[0] - segmentStart[0], segmentEnd[1] - segmentStart[1]];
    if (
      candidateDistanceSq < closestDistanceSq ||
      (Math.abs(candidateDistanceSq - closestDistanceSq) <= 1e-12 &&
        isZeroVector(closestTangent) &&
        !isZeroVector(candidateTangent))
    ) {
      closestPoint = candidate;
      closestSegmentStart = [segmentStart[0], segmentStart[1]];
      closestSegmentEnd = [segmentEnd[0], segmentEnd[1]];
      closestTangent = candidateTangent;
      closestDistanceSq = candidateDistanceSq;
      segmentIndex = index;
    }
  }

  return {
    point: closestPoint,
    tangent: closestTangent,
    segmentStart: closestSegmentStart,
    segmentEnd: closestSegmentEnd,
    segmentIndex,
  };
}

export function splitRoutePoints(
  routePoints: readonly RoutePoint[],
  projection: RouteProjection,
): { completed: ProjectedPoint[]; remaining: ProjectedPoint[] } {
  const point: ProjectedPoint = [projection.point[0], projection.point[1]];
  return {
    completed: [...routePoints.slice(0, projection.segmentIndex + 1).map((item) => [item[0], item[1]] as ProjectedPoint), point],
    remaining: [point, ...routePoints.slice(projection.segmentIndex + 1).map((item) => [item[0], item[1]] as ProjectedPoint)],
  };
}

export function projectRoutePoints(routePoints: readonly RoutePoint[], bounds: RouteProjectionBounds): ProjectedRoute {
  const latitudes = routePoints.map((point) => point[0]);
  const longitudes = routePoints.map((point) => point[1]);
  const latMin = Math.min(...latitudes);
  const latMax = Math.max(...latitudes);
  const lonMin = Math.min(...longitudes);
  const lonMax = Math.max(...longitudes);
  const latRange = Math.max(latMax - latMin, 1e-9);
  const lonRange = Math.max(lonMax - lonMin, 1e-9);
  const innerWidth = Math.max(bounds.right - bounds.left, 1);
  const innerHeight = Math.max(bounds.bottom - bounds.top, 1);
  const zoomScale = bounds.zoomPercent / 100;
  const projectionScale = Math.min(innerWidth / lonRange, innerHeight / latRange) * zoomScale;
  const contentWidth = lonRange * projectionScale;
  const contentHeight = latRange * projectionScale;
  const offsetX = bounds.left + (innerWidth - contentWidth) / 2;
  const offsetY = bounds.top + (innerHeight - contentHeight) / 2;

  const project = (point: RoutePoint): ProjectedPoint => [
    offsetX + (point[1] - lonMin) * projectionScale,
    offsetY + (latMax - point[0]) * projectionScale,
  ];

  return {
    points: routePoints.map(project),
    project,
  };
}
