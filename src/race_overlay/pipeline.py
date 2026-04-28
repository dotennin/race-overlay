from collections.abc import Callable
from datetime import timedelta
from glob import glob
from pathlib import Path
import subprocess

from PIL import Image

from race_overlay.activity.loader import load_activity
from race_overlay.alignment import align_clip
from race_overlay.config import (
    load_config,
    resolve_override,
    resolve_path_from_config,
    resolve_video_globs_from_config,
)
from race_overlay.ffmpeg import (
    build_overlay_video,
    compose_video,
    open_stream_compose_process,
    resolve_output_encoding_plan,
)
from race_overlay.hud import render_hud_frame
from race_overlay.sampling import lap_waterfall_states_for_widgets, sample_at
from race_overlay.video_probe import probe_video

ProgressReporter = Callable[[str], None]


class StreamingComposeError(OSError):
    """Transport/process failure while streaming overlay frames into ffmpeg."""


class RecoverableStreamingComposeError(StreamingComposeError):
    """Streaming-only transport failure that may succeed through the cache path."""


class FatalStreamingComposeError(StreamingComposeError):
    """ffmpeg setup or process failure that should abort instead of falling back."""


def _emit(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _discover_videos(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(match) for match in glob(pattern))
    return sorted(set(paths))


def _render_overlay_frame(
    *,
    activity,
    clip,
    alignment,
    index: int,
    route_points: list[tuple[float, float]],
    hud_config,
    total_distance_m: float | None,
) -> Image.Image:
    when = alignment.clip_start + timedelta(seconds=index / clip.fps)
    if alignment.overlay_start is None or when < alignment.overlay_start or when > alignment.overlay_end:
        return Image.new("RGBA", (clip.width, clip.height), (0, 0, 0, 0))

    hud_value = sample_at(activity, when)
    lap_states = lap_waterfall_states_for_widgets(hud_config, activity.laps, when)
    return render_hud_frame(
        width=clip.width,
        height=clip.height,
        hud_value=hud_value,
        route_points=route_points,
        hud_config=hud_config,
        elapsed_seconds=int((when - activity.samples[0].timestamp).total_seconds()),
        total_distance_m=total_distance_m,
        lap_states=lap_states,
    )


def _frame_count(clip) -> int:
    return int(clip.duration_seconds * clip.fps)


def _emit_encoding_plan(progress: ProgressReporter | None, clip, plan) -> None:
    audio_description = " ".join(plan.audio_args) if plan.audio_args else "none"
    _emit(
        progress,
        f"Encoding plan: {clip.path.name} video={plan.video_codec} pix_fmt={plan.pixel_format} audio={audio_description}",
    )
    for warning in plan.warnings:
        _emit(progress, f"Encoding fallback for {clip.path.name}: {warning}")


def _wait_for_process_exit(process: subprocess.Popen[bytes], timeout: float | None = None) -> int:
    if timeout is None:
        return process.wait()
    try:
        return process.wait(timeout=timeout)
    except TypeError:
        return process.wait()


def _cleanup_stream_process(process: subprocess.Popen[bytes]) -> None:
    stdin = process.stdin
    if stdin is not None:
        try:
            stdin.close()
        except OSError:
            pass

    try:
        if process.poll() is not None:
            return
    except (AttributeError, OSError, subprocess.SubprocessError):
        pass

    try:
        process.terminate()
    except (AttributeError, OSError, subprocess.SubprocessError):
        return

    try:
        _wait_for_process_exit(process, timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    except (OSError, subprocess.SubprocessError):
        return

    try:
        process.kill()
    except (AttributeError, OSError, subprocess.SubprocessError):
        return

    try:
        _wait_for_process_exit(process, timeout=5)
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        pass


def _process_return_code(process: subprocess.Popen[bytes]) -> int | None:
    try:
        return process.poll()
    except (AttributeError, OSError, subprocess.SubprocessError):
        return None


def _raise_stream_write_error(process: subprocess.Popen[bytes], action: str, exc: OSError) -> None:
    return_code = _process_return_code(process)
    if return_code not in (None, 0):
        raise FatalStreamingComposeError(
            f"ffmpeg exited with non-zero status {return_code} during stdin {action}: {exc}"
        ) from exc
    raise RecoverableStreamingComposeError(f"ffmpeg stdin {action} failed: {exc}") from exc


def _render_clip_streaming(
    *,
    activity,
    clip,
    alignment,
    route_points: list[tuple[float, float]],
    hud_config,
    total_distance_m: float | None,
    output_path: Path,
    plan,
) -> None:
    try:
        process = open_stream_compose_process(source_path=clip.path, clip=clip, output_path=output_path, plan=plan)
    except OSError as exc:
        raise FatalStreamingComposeError(f"ffmpeg streaming setup failed: {exc}") from exc

    if process.stdin is None:
        _cleanup_stream_process(process)
        raise RecoverableStreamingComposeError("ffmpeg stdin pipe unavailable")

    try:
        for index in range(_frame_count(clip)):
            image = _render_overlay_frame(
                activity=activity,
                clip=clip,
                alignment=alignment,
                index=index,
                route_points=route_points,
                hud_config=hud_config,
                total_distance_m=total_distance_m,
            )
            try:
                process.stdin.write(image.tobytes())
            except OSError as exc:
                _raise_stream_write_error(process, "write", exc)

        try:
            process.stdin.close()
        except OSError as exc:
            _raise_stream_write_error(process, "close", exc)

        try:
            return_code = process.wait()
        except (OSError, subprocess.SubprocessError) as exc:
            raise FatalStreamingComposeError(f"ffmpeg process wait failed: {exc}") from exc

        if return_code != 0:
            raise FatalStreamingComposeError(
                f"ffmpeg exited with non-zero status {return_code}"
            ) from subprocess.CalledProcessError(return_code, "ffmpeg")
    except Exception:
        _cleanup_stream_process(process)
        raise


def _render_clip_via_cache(
    *,
    activity,
    clip,
    alignment,
    route_points: list[tuple[float, float]],
    hud_config,
    total_distance_m: float | None,
    cache_dir: Path,
    output_dir: Path,
    progress: ProgressReporter | None,
    plan,
) -> None:
    frame_dir = cache_dir / clip.path.stem / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    _emit(progress, f"Generating frame cache at {frame_dir}")
    for index in range(_frame_count(clip)):
        image = _render_overlay_frame(
            activity=activity,
            clip=clip,
            alignment=alignment,
            index=index,
            route_points=route_points,
            hud_config=hud_config,
            total_distance_m=total_distance_m,
        )
        image.save(frame_dir / f"{index:06d}.png")

    overlay_path = cache_dir / clip.path.stem / "overlay.mov"
    output_path = output_dir / clip.path.name
    _emit(progress, f"Building overlay cache at {overlay_path}")
    build_overlay_video(frame_dir, clip.fps, overlay_path)
    _emit(progress, f"Composing final video at {output_path}")
    compose_video(clip.path, overlay_path, output_path, plan=plan)


def run_pipeline(config_path: Path, only: str | None = None, *, progress: ProgressReporter | None = None) -> None:
    _emit(progress, f"Loading config from {config_path}")
    config = load_config(config_path)
    activity_path = resolve_path_from_config(config_path, config.activity_file)
    _emit(progress, f"Loading activity from {activity_path}")
    activity = load_activity(activity_path)
    total_distance_m = activity.samples[-1].distance_m if activity.samples else None
    route_points = [
        (sample.latitude, sample.longitude)
        for sample in activity.samples
        if sample.latitude is not None and sample.longitude is not None
    ]
    output_dir = resolve_path_from_config(config_path, config.output_dir)
    cache_dir = resolve_path_from_config(config_path, config.cache_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    for video_path in _discover_videos(resolve_video_globs_from_config(config_path, config.video_globs)):
        if only and video_path.name != only:
            continue
        _emit(progress, f"Processing {video_path.name}")
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
            _emit(progress, f"Skipping {clip.path.name}: outside activity window and policy=skip")
            continue

        output_path = output_dir / clip.path.name
        plan = resolve_output_encoding_plan(clip)
        _emit_encoding_plan(progress, clip, plan)

        try:
            _emit(progress, f"Render path: streaming for {clip.path.name}")
            _render_clip_streaming(
                activity=activity,
                clip=clip,
                alignment=alignment,
                route_points=route_points,
                hud_config=config.hud,
                total_distance_m=total_distance_m,
                output_path=output_path,
                plan=plan,
            )
        except RecoverableStreamingComposeError as exc:
            _emit(progress, f"Streaming unavailable for {clip.path.name}; falling back to cache: {exc}")
            _emit(progress, f"Render path: cache for {clip.path.name}")
            _render_clip_via_cache(
                activity=activity,
                clip=clip,
                alignment=alignment,
                route_points=route_points,
                hud_config=config.hud,
                total_distance_m=total_distance_m,
                cache_dir=cache_dir,
                output_dir=output_dir,
                progress=progress,
                plan=plan,
            )
        _emit(progress, f"Finished {clip.path.name}")
