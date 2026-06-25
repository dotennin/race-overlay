import type { ActivityTrack, ClipAlignment, VideoClip } from "./models";
import { addSeconds, maxIso, minIso } from "./time";

export interface AlignClipOptions {
  globalOffsetSeconds: number;
  perVideoOffsetSeconds: number;
}

export function alignClip(activity: ActivityTrack, clip: VideoClip, options: AlignClipOptions): ClipAlignment {
  if (activity.samples.length < 2) {
    throw new Error("activity must contain at least 2 samples");
  }
  const clipStart = addSeconds(clip.creationTime, options.globalOffsetSeconds + options.perVideoOffsetSeconds);
  const clipEnd = addSeconds(clipStart, clip.durationSeconds);
  const activityStart = activity.samples[0].timestamp;
  const activityEnd = activity.samples[activity.samples.length - 1].timestamp;
  const overlayStart = maxIso(clipStart, activityStart);
  const overlayEnd = minIso(clipEnd, activityEnd);

  if (new Date(clipEnd).getTime() <= new Date(activityStart).getTime() || new Date(clipStart).getTime() >= new Date(activityEnd).getTime()) {
    return { clip, status: "outside", clipStart, clipEnd, overlayStart: null, overlayEnd: null };
  }
  if (new Date(clipStart).getTime() < new Date(activityStart).getTime() || new Date(clipEnd).getTime() > new Date(activityEnd).getTime()) {
    return { clip, status: "partial", clipStart, clipEnd, overlayStart, overlayEnd };
  }
  return { clip, status: "inside", clipStart, clipEnd, overlayStart, overlayEnd };
}
