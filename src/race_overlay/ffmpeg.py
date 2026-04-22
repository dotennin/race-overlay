import subprocess
from dataclasses import dataclass
from pathlib import Path

from race_overlay.models import VideoClip

SUPPORTED_VIDEO_CODEC_MAP = {
    "h264": "libx264",
    "hevc": "libx265",
    "prores": "prores_ks",
}

DEFAULT_VIDEO_CODEC = "libx264"
DEFAULT_PIXEL_FORMATS = {
    "libx264": "yuv420p",
    "libx265": "yuv420p",
    "prores_ks": "yuv422p10le",
}
SUPPORTED_PIXEL_FORMATS = {
    "libx264": {"nv12", "yuv420p", "yuv422p", "yuv444p", "yuvj420p", "yuvj422p", "yuvj444p"},
    "libx265": {"yuv420p", "yuv420p10le", "yuv422p", "yuv422p10le", "yuv444p", "yuv444p10le"},
    "prores_ks": {"yuv422p10le", "yuv444p10le", "yuva444p10le"},
}


@dataclass(slots=True, frozen=True)
class OutputEncodingPlan:
    video_codec: str
    pixel_format: str
    video_bitrate: int | None
    color_space: str | None
    color_transfer: str | None
    color_primaries: str | None
    audio_args: tuple[str, ...]
    warnings: tuple[str, ...]


def build_overlay_video(frame_dir: Path, fps: float, output_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "%06d.png"),
            "-c:v",
            "qtrle",
            str(output_path),
        ],
        check=True,
    )


def compose_video(source_path: Path, overlay_path: Path, output_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-i",
            str(overlay_path),
            "-filter_complex",
            "[0:v][1:v]overlay=0:0",
            "-c:a",
            "copy",
            str(output_path),
        ],
        check=True,
    )


def resolve_output_encoding_plan(clip: VideoClip) -> OutputEncodingPlan:
    warnings: list[str] = []
    source_codec = clip.video_codec
    video_codec = SUPPORTED_VIDEO_CODEC_MAP.get(source_codec or "", DEFAULT_VIDEO_CODEC)
    if source_codec not in SUPPORTED_VIDEO_CODEC_MAP:
        if source_codec:
            warnings.append(
                f"Unsupported source video codec '{source_codec}'; using '{video_codec}' instead."
            )
        else:
            warnings.append(f"Source video codec missing; using '{video_codec}'.")

    source_pixel_format = clip.pixel_format
    supported_pixel_formats = SUPPORTED_PIXEL_FORMATS[video_codec]
    pixel_format = source_pixel_format or DEFAULT_PIXEL_FORMATS[video_codec]
    if pixel_format not in supported_pixel_formats:
        pixel_format = DEFAULT_PIXEL_FORMATS[video_codec]
        if source_pixel_format:
            warnings.append(
                f"Pixel format '{source_pixel_format}' is incompatible with '{video_codec}'; using '{pixel_format}' instead."
            )

    audio_args: tuple[str, ...] = ("-c:a", "copy") if clip.audio_codec else ()

    return OutputEncodingPlan(
        video_codec=video_codec,
        pixel_format=pixel_format,
        video_bitrate=clip.video_bitrate,
        color_space=clip.color_space,
        color_transfer=clip.color_transfer,
        color_primaries=clip.color_primaries,
        audio_args=audio_args,
        warnings=tuple(warnings),
    )


def build_stream_compose_command(
    *, source_path: Path, clip: VideoClip, output_path: Path, plan: OutputEncodingPlan
) -> list[str]:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{clip.width}x{clip.height}",
        "-r",
        str(clip.fps),
        "-i",
        "-",
        "-filter_complex",
        "[0:v][1:v]overlay=0:0[video]",
        "-map",
        "[video]",
        "-map",
        "0:a?",
        "-c:v",
        plan.video_codec,
        "-pix_fmt",
        plan.pixel_format,
    ]
    if plan.video_bitrate is not None and plan.video_bitrate > 0:
        command.extend(["-b:v", str(plan.video_bitrate)])
    if plan.color_space is not None:
        command.extend(["-colorspace", plan.color_space])
    if plan.color_transfer is not None:
        command.extend(["-color_trc", plan.color_transfer])
    if plan.color_primaries is not None:
        command.extend(["-color_primaries", plan.color_primaries])
    command.extend(plan.audio_args)
    command.append(str(output_path))
    return command
