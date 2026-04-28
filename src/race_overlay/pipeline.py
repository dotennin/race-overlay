from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from glob import glob
import os
import fnmatch
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
from race_overlay.hud import (
    prime_route_map_caches,
    render_hud_frame as _render_hud_frame,
    render_prepared_hud_frame,
    validate_hud_config,
)
from race_overlay.hud_schema import HudConfig, HudWidgetConfig
from race_overlay.sampling import lap_waterfall_states_for_widgets, sample_at, SampleCursor
from race_overlay.video_probe import probe_video

ProgressReporter = Callable[[str], None]


@dataclass(slots=True, frozen=True)
class RenderContext:
    """Clip-level render context with precomputed/validated data.
    
    Created once per clip to move repeated work out of per-frame rendering.
    Contains validated config, visible widgets, route data, and sample cursor.
    """
    hud_config: HudConfig
    visible_widgets: list[HudWidgetConfig]
    route_points: list[tuple[float, float]]
    sample_cursor: SampleCursor
    total_distance_m: float | None
    route_map_cache_keys: dict[str, str]


def create_render_context(
    hud_config: HudConfig,
    samples: list,
    route_points: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
    total_distance_m: float | None = None,
) -> RenderContext:
    """Create a render context with precomputed data for a clip.
    
    Args:
        hud_config: Validated HUD configuration
        samples: Activity samples for cursor initialization
        route_points: GPS route points for the map
        total_distance_m: Optional total distance for progress bars
        
    Returns:
        RenderContext with visible widgets and sample cursor
    """
    validated_hud_config = validate_hud_config(hud_config)
    visible_widgets = sorted(
        (widget for widget in validated_hud_config.widgets if widget.visible),
        key=lambda widget: widget.z_index,
    )
    sample_cursor = SampleCursor(samples)
    route_map_cache_keys = prime_route_map_caches(
        widgets=visible_widgets,
        route_points=route_points,
        theme=validated_hud_config.theme,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    
    return RenderContext(
        hud_config=validated_hud_config,
        visible_widgets=visible_widgets,
        route_points=route_points,
        sample_cursor=sample_cursor,
        total_distance_m=total_distance_m,
        route_map_cache_keys=route_map_cache_keys,
    )


class StreamingComposeError(OSError):
    """Transport/process failure while streaming overlay frames into ffmpeg."""


class RecoverableStreamingComposeError(StreamingComposeError):
    """Streaming-only transport failure that may succeed through the cache path."""


class FatalStreamingComposeError(StreamingComposeError):
    """ffmpeg setup or process failure that should abort instead of falling back."""


def render_hud_frame(
    *,
    width: int,
    height: int,
    hud_value,
    route_points: list[tuple[float, float]],
    hud_config: HudConfig,
    elapsed_seconds: int = 0,
    total_distance_m: float | None = None,
    lap_states=None,
    visible_widgets: list[HudWidgetConfig] | None = None,
    route_map_cache_keys: dict[str, str] | None = None,
):
    if visible_widgets is None:
        return _render_hud_frame(
            width=width,
            height=height,
            hud_value=hud_value,
            route_points=route_points,
            hud_config=hud_config,
            elapsed_seconds=elapsed_seconds,
            total_distance_m=total_distance_m,
            lap_states=lap_states,
        )
    return render_prepared_hud_frame(
        width=width,
        height=height,
        hud_value=hud_value,
        route_points=route_points,
        theme=hud_config.theme,
        widgets=visible_widgets,
        elapsed_seconds=elapsed_seconds,
        total_distance_m=total_distance_m,
        lap_states=lap_states,
        route_map_cache_keys=route_map_cache_keys,
    )


def _emit(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _discover_videos(patterns: list[str]) -> list[Path]:
    """Discover files matching patterns, treating filename matching as case-insensitive.

    glob.glob() is used to respect directory patterns, but filesystems may be case-sensitive
    so also scan the candidate directory tree and match filenames case-insensitively
    against the pattern's name component.
    """
    matches: set[Path] = set()
    for pattern in patterns:
        # Add any exact glob matches first (respects directories/recursive globs)
        for match in glob(pattern):
            matches.add(Path(match))

        # Fall back to case-insensitive name matching within the pattern's directory
        dirpart, name_pat = os.path.split(pattern)
        # If the directory part contains glob meta-chars, search from repo root
        if dirpart and not any(ch in dirpart for ch in "*?["):
            base = Path(dirpart)
        else:
            base = Path('.')

        lower_name_pat = name_pat.lower()
        for candidate in base.rglob("*"):
            if not candidate.is_file():
                continue
            if fnmatch.fnmatch(candidate.name.lower(), lower_name_pat):
                matches.add(candidate)

    return sorted(matches)


def _render_overlay_frame(
    *,
    activity,
    clip,
    alignment,
    index: int,
    context: RenderContext,
) -> Image.Image:
    when = alignment.clip_start + timedelta(seconds=index / clip.fps)
    if alignment.overlay_start is None or when < alignment.overlay_start or when > alignment.overlay_end:
        return Image.new("RGBA", (clip.width, clip.height), (0, 0, 0, 0))

    hud_value = sample_at(activity, when, cursor=context.sample_cursor)
    lap_states = lap_waterfall_states_for_widgets(context.hud_config, activity.laps, when)
    return render_hud_frame(
        width=clip.width,
        height=clip.height,
        hud_value=hud_value,
        route_points=context.route_points,
        hud_config=context.hud_config,
        elapsed_seconds=int((when - activity.samples[0].timestamp).total_seconds()),
        total_distance_m=context.total_distance_m,
        lap_states=lap_states,
        visible_widgets=context.visible_widgets,
        route_map_cache_keys=context.route_map_cache_keys,
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
    context: RenderContext,
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
                context=context,
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
    context: RenderContext,
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
            context=context,
        )
        image.save(frame_dir / f"{index:06d}.png")

    overlay_path = cache_dir / clip.path.stem / "overlay.mov"
    output_path = output_dir / clip.path.name
    _emit(progress, f"Building overlay cache at {overlay_path}")
    build_overlay_video(frame_dir, clip.fps, overlay_path)
    _emit(progress, f"Composing final video at {output_path}")
    compose_video(
        clip.path,
        overlay_path,
        output_path,
        plan=plan,
        attached_pic_stream_index=clip.attached_pic_stream_index,
    )


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

        # Create render context once per clip to avoid repeated per-frame work
        context = create_render_context(
            hud_config=config.hud,
            samples=activity.samples,
            route_points=route_points,
            frame_width=clip.width,
            frame_height=clip.height,
            total_distance_m=total_distance_m,
        )

        try:
            _emit(progress, f"Render path: streaming for {clip.path.name}")
            _render_clip_streaming(
                activity=activity,
                clip=clip,
                alignment=alignment,
                context=context,
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
                context=context,
                cache_dir=cache_dir,
                output_dir=output_dir,
                progress=progress,
                plan=plan,
            )
        _emit(progress, f"Finished {clip.path.name}")
