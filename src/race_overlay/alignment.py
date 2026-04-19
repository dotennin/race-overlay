from datetime import timedelta

from race_overlay.models import ActivityTrack, ClipAlignment, VideoClip


def align_clip(
    activity: ActivityTrack,
    clip: VideoClip,
    global_offset_seconds: float,
    per_video_offset_seconds: float,
) -> ClipAlignment:
    clip_start = clip.creation_time + timedelta(seconds=global_offset_seconds + per_video_offset_seconds)
    clip_end = clip_start + timedelta(seconds=clip.duration_seconds)
    activity_start = activity.samples[0].timestamp
    activity_end = activity.samples[-1].timestamp
    overlay_start = max(clip_start, activity_start)
    overlay_end = min(clip_end, activity_end)
    if clip_end <= activity_start or clip_start >= activity_end:
        return ClipAlignment(clip, "outside", clip_start, clip_end, None, None)
    if clip_start < activity_start or clip_end > activity_end:
        return ClipAlignment(clip, "partial", clip_start, clip_end, overlay_start, overlay_end)
    return ClipAlignment(clip, "inside", clip_start, clip_end, overlay_start, overlay_end)
