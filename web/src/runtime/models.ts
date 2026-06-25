export interface ActivitySample {
  timestamp: string;
  latitude: number | null;
  longitude: number | null;
  altitudeM: number | null;
  distanceM: number | null;
  speedMps: number | null;
  heartRateBpm: number | null;
  cadenceSpm: number | null;
}

export interface ActivityLap {
  startTime: string;
  totalTimeSeconds: number;
  distanceM: number;
  avgHeartRateBpm: number | null;
  maxHeartRateBpm: number | null;
  maxSpeedMps: number | null;
  elevationDeltaM: number | null;
  calories: number | null;
}

export interface ActivityTrack {
  sport: string;
  samples: ActivitySample[];
  laps: ActivityLap[];
}

export interface HudSample extends ActivitySample {
  paceSecondsPerKm: number | null;
}

export interface VideoClip {
  name: string;
  creationTime: string;
  durationSeconds: number;
  width: number;
  height: number;
  fps: number;
}

export interface ClipAlignment {
  clip: VideoClip;
  status: "outside" | "partial" | "inside";
  clipStart: string;
  clipEnd: string;
  overlayStart: string | null;
  overlayEnd: string | null;
}
