from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from glob import glob
from io import BytesIO
import os
import fnmatch
from inspect import signature
from pathlib import Path
import subprocess

from PIL import Image

from race_overlay.activity.loader import load_activity
from race_overlay.alignment import align_clip
from race_overlay.config import (
    load_config,
    resolve_video_override,
    resolve_path_from_config,
    resolve_video_globs_from_config,
)
from race_overlay.ffmpeg import (
    build_overlay_video,
    compose_video,
    extract_video_frame,
    open_stream_compose_process,
    resolve_output_encoding_plan,
)
from race_overlay.editor_render import RenderJobCanceledError, RenderPreviewUpdate, RenderProgressUpdate
from race_overlay.hud import (
    RouteProjectionCursor,
    prime_route_map_caches,
    render_hud_frame as _render_hud_frame,
    render_prepared_hud_frame,
    validate_hud_config,
)
from race_overlay.hud_schema import HudConfig, HudWidgetConfig
from race_overlay.sampling import lap_waterfall_states_for_widgets, sample_at, SampleCursor
from race_overlay.video_probe import probe_video
from race_overlay.rotation import RotationSpec
from race_overlay.video_library import discover_video_paths

ProgressReporter = Callable[[str], None]
ProgressUpdateReporter = Callable[[RenderProgressUpdate], None]
PreviewUpdateReporter = Callable[[RenderPreviewUpdate | None], bool]


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
    route_projection_cursors: dict[str, RouteProjectionCursor]


@dataclass(slots=True, frozen=False)
class PreviewSourceFrameCache:
    source_path: Path | None = None
    bucket: int | None = None
    image: Image.Image | None = None

    def get(
        self,
        source_path: Path,
        *,
        bucket: int,
        timestamp_seconds: float,
        rotation_degrees: int,
    ) -> Image.Image:
        if self.source_path == source_path and self.bucket == bucket and self.image is not None:
            return self.image.copy()
        kwargs: dict[str, object] = {"timestamp_seconds": timestamp_seconds}
        if "rotation_degrees" in signature(extract_video_frame).parameters:
            kwargs["rotation_degrees"] = rotation_degrees
        image = extract_video_frame(source_path, **kwargs)
        self.source_path = source_path
        self.bucket = bucket
        self.image = image.copy()
        return image


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
    route_projection_cursors = {
        widget.id: RouteProjectionCursor()
        for widget in visible_widgets
        if widget.type == "route_map"
    }
    
    return RenderContext(
        hud_config=validated_hud_config,
        visible_widgets=visible_widgets,
        route_points=route_points,
        sample_cursor=sample_cursor,
        total_distance_m=total_distance_m,
        route_map_cache_keys=route_map_cache_keys,
        route_projection_cursors=route_projection_cursors,
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
    route_projection_cursors: dict[str, RouteProjectionCursor] | None = None,
    frame_index: int | None = None,
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
        route_projection_cursors=route_projection_cursors,
        frame_index=frame_index,
    )


def _emit(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _emit_progress_update(
    progress_update: ProgressUpdateReporter | None,
    *,
    clip_name: str,
    frame_index: int,
    frame_total: int,
    message: str,
) -> None:
    if progress_update is None:
        return
    progress_update(
        RenderProgressUpdate(
            phase="rendering",
            message=message,
            clip_name=clip_name,
            frame_index=frame_index,
            frame_total=frame_total,
            percent=int((frame_index / frame_total) * 100),
        )
    )


def _discover_videos_legacy(patterns: list[str]) -> list[Path]:
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


def _discover_videos(patterns: list[str]) -> list[Path]:
    return discover_video_paths(patterns)


def _render_overlay_frame(
    *,
    activity,
    clip,
    alignment,
    index: int,
    context: RenderContext,
) -> Image.Image | None:
    when = alignment.clip_start + timedelta(seconds=index / clip.fps)
    if alignment.overlay_start is None or when < alignment.overlay_start or when > alignment.overlay_end:
        return None

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
        route_projection_cursors=context.route_projection_cursors,
        frame_index=index,
    )


def _frame_count(clip) -> int:
    return int(clip.duration_seconds * clip.fps)


def _frame_time_seconds(*, index: int, fps: float) -> float:
    if fps <= 0:
        return 0.0
    return index / fps


def _preview_bucket(*, index: int, fps: float) -> int:
    if fps <= 0:
        return 0
    return int(_frame_time_seconds(index=index, fps=fps))


def _create_empty_frame_bytes(width: int, height: int) -> bytes:
    """Create pre-computed empty RGBA frame bytes for transparent overlay.
    
    This avoids creating a new PIL Image object for every transparent frame,
    significantly speeding up rendering of partial clips.
    """
    return Image.new("RGBA", (width, height), (0, 0, 0, 0)).tobytes()


def _compose_preview_frame(*, source_frame: Image.Image, overlay_frame: Image.Image | None) -> Image.Image:
    composed = source_frame.convert("RGBA")
    if overlay_frame is not None:
        composed.alpha_composite(overlay_frame.convert("RGBA"))
    return composed


def _encode_preview_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _maybe_publish_preview(
    *,
    clip,
    index: int,
    overlay_frame: Image.Image | None,
    preview_update: PreviewUpdateReporter | None,
    progress: ProgressReporter | None,
    last_preview_bucket: int | None,
    preview_source_cache: PreviewSourceFrameCache | None = None,
    rotation: RotationSpec | None = None,
) -> int | None:
    if preview_update is None:
        return last_preview_bucket
    current_bucket = _preview_bucket(index=index, fps=clip.fps)
    if current_bucket == last_preview_bucket:
        return last_preview_bucket
    if not preview_update(None):
        return last_preview_bucket
    frame_time_seconds = _frame_time_seconds(index=index, fps=clip.fps)
    try:
        if preview_source_cache is None:
            kwargs: dict[str, object] = {"timestamp_seconds": frame_time_seconds}
            if "rotation_degrees" in signature(extract_video_frame).parameters:
                kwargs["rotation_degrees"] = rotation.effective_degrees if rotation else 0
            source_frame = extract_video_frame(clip.path, **kwargs)
        else:
            source_frame = preview_source_cache.get(
                clip.path,
                bucket=current_bucket,
                timestamp_seconds=frame_time_seconds,
                rotation_degrees=rotation.effective_degrees if rotation else 0,
            )
        preview_image = _compose_preview_frame(source_frame=source_frame, overlay_frame=overlay_frame)
        preview_bytes = _encode_preview_png(preview_image)
    except Exception as exc:
        _emit(
            progress,
            f"Preview unavailable for {clip.path.name} frame {index + 1}/{max(_frame_count(clip), 1)}: {exc}",
        )
        return current_bucket
    preview_update(
        RenderPreviewUpdate(
            clip_name=clip.path.name,
            frame_index=index + 1,
            frame_time_seconds=frame_time_seconds,
            image_bytes=preview_bytes,
        )
    )
    return current_bucket


def _emit_encoding_plan(progress: ProgressReporter | None, clip, plan) -> None:
    audio_description = " ".join(plan.audio_args) if plan.audio_args else "none"
    preset_description = plan.video_preset or "none"
    _emit(
        progress,
        f"Encoding plan: {clip.path.name} video={plan.video_codec} pix_fmt={plan.pixel_format} preset={preset_description} audio={audio_description}",
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
    rotation: RotationSpec,
    progress: ProgressReporter | None = None,
    progress_update: ProgressUpdateReporter | None = None,
    preview_update: PreviewUpdateReporter | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    try:
        process = open_stream_compose_process(
            source_path=clip.path,
            clip=clip,
            output_path=output_path,
            plan=plan,
            rotation=rotation,
        )
    except OSError as exc:
        raise FatalStreamingComposeError(f"ffmpeg streaming setup failed: {exc}") from exc

    if process.stdin is None:
        _cleanup_stream_process(process)
        raise RecoverableStreamingComposeError("ffmpeg stdin pipe unavailable")

    try:
        frame_total = max(_frame_count(clip), 1)
        last_preview_bucket: int | None = None
        preview_source_cache = PreviewSourceFrameCache()
        empty_frame_bytes = _create_empty_frame_bytes(clip.width, clip.height)
        for index in range(frame_total):
            if cancel_requested is not None and cancel_requested():
                raise RenderJobCanceledError("render canceled")
            image = _render_overlay_frame(
                activity=activity,
                clip=clip,
                alignment=alignment,
                index=index,
                context=context,
            )
            frame_number = index + 1
            message = f"Rendering {clip.path.name} frame {frame_number}/{frame_total}"
            _emit(progress, message)
            _emit_progress_update(
                progress_update,
                clip_name=clip.path.name,
                frame_index=frame_number,
                frame_total=frame_total,
                message=message,
            )
            last_preview_bucket = _maybe_publish_preview(
                clip=clip,
                index=index,
                overlay_frame=image,
                preview_update=preview_update,
                progress=progress,
                last_preview_bucket=last_preview_bucket,
                preview_source_cache=preview_source_cache,
                rotation=rotation,
            )
            try:
                frame_bytes = empty_frame_bytes if image is None else image.tobytes()
                process.stdin.write(frame_bytes)
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
    rotation: RotationSpec,
    progress_update: ProgressUpdateReporter | None = None,
    preview_update: PreviewUpdateReporter | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
    frame_dir = cache_dir / clip.path.stem / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    _emit(progress, f"Generating frame cache at {frame_dir}")
    frame_total = max(_frame_count(clip), 1)
    last_preview_bucket: int | None = None
    preview_source_cache = PreviewSourceFrameCache()
    empty_frame = Image.new("RGBA", (clip.width, clip.height), (0, 0, 0, 0))
    for index in range(frame_total):
        if cancel_requested is not None and cancel_requested():
            raise RenderJobCanceledError("render canceled")
        image = _render_overlay_frame(
            activity=activity,
            clip=clip,
            alignment=alignment,
            index=index,
            context=context,
        )
        frame_number = index + 1
        message = f"Rendering {clip.path.name} frame {frame_number}/{frame_total}"
        _emit(progress, message)
        _emit_progress_update(
            progress_update,
            clip_name=clip.path.name,
            frame_index=frame_number,
            frame_total=frame_total,
            message=message,
        )
        last_preview_bucket = _maybe_publish_preview(
            clip=clip,
            index=index,
            overlay_frame=image,
            preview_update=preview_update,
            progress=progress,
            last_preview_bucket=last_preview_bucket,
            preview_source_cache=preview_source_cache,
            rotation=rotation,
        )
        frame_to_save = empty_frame if image is None else image
        frame_to_save.save(frame_dir / f"{index:06d}.png")

    overlay_path = cache_dir / clip.path.stem / "overlay.mov"
    output_path = output_dir / clip.path.name
    _emit(progress, f"Building overlay cache at {overlay_path}")
    build_overlay_video(frame_dir, clip.fps, overlay_path)
    _emit(progress, f"Composing final video at {output_path}")
    compose_kwargs: dict[str, object] = {
        "plan": plan,
        "attached_pic_stream_index": clip.attached_pic_stream_index,
    }
    if "rotation" in signature(compose_video).parameters:
        compose_kwargs["rotation"] = rotation
    compose_video(clip.path, overlay_path, output_path, **compose_kwargs)


def run_pipeline(
    config_path: Path,
    only: str | None = None,
    *,
    progress: ProgressReporter | None = None,
    progress_update: ProgressUpdateReporter | None = None,
    preview_update: PreviewUpdateReporter | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> None:
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

    video_paths = _discover_videos(
        resolve_video_globs_from_config(config_path, config.video_globs)
    )
    for video_path in video_paths:
        if only and video_path.name != only:
            continue
        _emit(progress, f"Processing {video_path.name}")
        source_clip = probe_video(video_path)
        override = resolve_video_override(config, config_path, video_path, video_paths)
        rotation = RotationSpec.from_clip(source_clip, override.rotation_degrees)
        clip = replace(
            source_clip,
            width=rotation.display_width,
            height=rotation.display_height,
        )
        alignment = align_clip(
            activity,
            clip,
            global_offset_seconds=config.timeline.global_offset_seconds,
            per_video_offset_seconds=override.offset_seconds,
        )
        outside_policy = override.outside_activity or config.timeline.outside_activity
        if alignment.status == "outside" and outside_policy == "skip":
            # Skipped clips must not enter any render/preview path.
            _emit(progress, f"Skipping {clip.path.name}: outside activity window and policy=skip")
            continue

        output_path = output_dir / clip.path.name
        plan = resolve_output_encoding_plan(
            source_clip,
            video_preset=config.encoding.video_preset,
        )
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
                rotation=rotation,
                progress=progress,
                progress_update=progress_update,
                preview_update=preview_update,
                cancel_requested=cancel_requested,
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
                rotation=rotation,
                progress_update=progress_update,
                preview_update=preview_update,
                cancel_requested=cancel_requested,
            )
        _emit(progress, f"Finished {clip.path.name}")
