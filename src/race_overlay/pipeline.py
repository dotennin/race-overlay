from datetime import timedelta
from glob import glob
from pathlib import Path

from PIL import Image

from race_overlay.activity.loader import load_activity
from race_overlay.alignment import align_clip
from race_overlay.config import load_config, resolve_override
from race_overlay.ffmpeg import build_overlay_video, compose_video
from race_overlay.hud import HudLayout, render_hud_frame
from race_overlay.sampling import sample_at
from race_overlay.video_probe import probe_video


def _discover_videos(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(match) for match in glob(pattern))
    return sorted(set(paths))


def run_pipeline(config_path: Path, only: str | None = None) -> None:
    config = load_config(config_path)
    activity = load_activity(Path(config.activity_file))
    route_points = [
        (sample.latitude, sample.longitude)
        for sample in activity.samples
        if sample.latitude is not None and sample.longitude is not None
    ]
    output_dir = Path(config.output_dir)
    cache_dir = Path(config.cache_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    for video_path in _discover_videos(config.video_globs):
        if only and video_path.name != only:
            continue
        clip = probe_video(video_path)
        override = resolve_override(config, clip.path.name)
        alignment = align_clip(
            activity,
            clip,
            global_offset_seconds=config.timeline.global_offset_seconds,
            per_video_offset_seconds=override.offset_seconds,
        )
        outside_policy = override.outside_activity or config.timeline.outside_activity
        if alignment.status == "outside" and outside_policy == "skip":
            continue

        frame_dir = cache_dir / clip.path.stem / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        for index in range(int(clip.duration_seconds * clip.fps)):
            when = alignment.clip_start + timedelta(seconds=index / clip.fps)
            if alignment.overlay_start is None or when < alignment.overlay_start or when > alignment.overlay_end:
                image = Image.new("RGBA", (clip.width, clip.height), (0, 0, 0, 0))
            else:
                hud_value = sample_at(activity, when)
                image = render_hud_frame(
                    width=clip.width,
                    height=clip.height,
                    hud_value=hud_value,
                    route_points=route_points,
                    layout=HudLayout.default(),
                    elapsed_seconds=int((when - activity.samples[0].timestamp).total_seconds()),
                )
            image.save(frame_dir / f"{index:06d}.png")

        overlay_path = cache_dir / clip.path.stem / "overlay.mov"
        output_path = output_dir / clip.path.name
        build_overlay_video(frame_dir, clip.fps, overlay_path)
        compose_video(clip.path, overlay_path, output_path)
