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
SDR_BT709_COLOR_PROFILE = ("bt709", "bt709", "bt709")
HDR10_COLOR_PROFILE = ("bt2020nc", "smpte2084", "bt2020")
SDR_ONLY_COLOR_METADATA_PIXEL_FORMATS = {
    "libx264": SUPPORTED_PIXEL_FORMATS["libx264"],
    "libx265": {"yuv420p", "yuv422p", "yuv444p"},
    "prores_ks": SUPPORTED_PIXEL_FORMATS["prores_ks"],
}
HDR10_COLOR_METADATA_PIXEL_FORMATS = {
    "libx265": {"yuv420p10le", "yuv422p10le", "yuv444p10le"},
}
HDR10_FALLBACK_PIXEL_FORMATS = {
    "libx265": "yuv420p10le",
}
COLOR_METADATA_FIELD_NAMES = {
    "color_space": "Color space",
    "color_transfer": "Color transfer",
    "color_primaries": "Color primaries",
}
COLOR_METADATA_DROP_PRONOUNS = {
    "color_space": "it",
    "color_transfer": "it",
    "color_primaries": "them",
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


def _supported_color_metadata_profiles(video_codec: str, pixel_format: str) -> tuple[tuple[str, str, str], ...]:
    profiles: list[tuple[str, str, str]] = []
    if pixel_format in SDR_ONLY_COLOR_METADATA_PIXEL_FORMATS.get(video_codec, set()):
        profiles.append(SDR_BT709_COLOR_PROFILE)
    if pixel_format in HDR10_COLOR_METADATA_PIXEL_FORMATS.get(video_codec, set()):
        profiles.extend((SDR_BT709_COLOR_PROFILE, HDR10_COLOR_PROFILE))
    return tuple(profiles)


def _is_exact_color_profile(
    color_space: str | None, color_transfer: str | None, color_primaries: str | None, profile: tuple[str, str, str]
) -> bool:
    return (color_space, color_transfer, color_primaries) == profile


def _preferred_pixel_format(
    *,
    video_codec: str,
    source_pixel_format: str | None,
    color_space: str | None,
    color_transfer: str | None,
    color_primaries: str | None,
) -> str:
    if _is_exact_color_profile(color_space, color_transfer, color_primaries, HDR10_COLOR_PROFILE):
        hdr10_supported_pixel_formats = HDR10_COLOR_METADATA_PIXEL_FORMATS.get(video_codec, set())
        if source_pixel_format in hdr10_supported_pixel_formats:
            return source_pixel_format
        hdr10_pixel_format = HDR10_FALLBACK_PIXEL_FORMATS.get(video_codec)
        if hdr10_pixel_format is not None:
            return hdr10_pixel_format
    supported_pixel_formats = SUPPORTED_PIXEL_FORMATS[video_codec]
    if source_pixel_format in supported_pixel_formats:
        return source_pixel_format
    return DEFAULT_PIXEL_FORMATS[video_codec]


def _drop_color_metadata_warning(
    *, field_name: str, value: str, video_codec: str, pixel_format: str, reason: str
) -> str:
    label = COLOR_METADATA_FIELD_NAMES[field_name]
    verb = "are" if field_name == "color_primaries" else "is"
    pronoun = COLOR_METADATA_DROP_PRONOUNS[field_name]
    output_plan = f"{video_codec}/{pixel_format}"
    if reason == "output plan":
        incompatibility = f"output plan '{output_plan}'"
    else:
        incompatibility = f"{reason} for '{output_plan}'"
    return (
        f"{label} '{value}' {verb} incompatible with {incompatibility}; dropping {pronoun}."
    )


def _resolve_color_metadata(
    *,
    video_codec: str,
    pixel_format: str,
    color_space: str | None,
    color_transfer: str | None,
    color_primaries: str | None,
    warnings: list[str],
) -> tuple[str | None, str | None, str | None]:
    supported_profiles = _supported_color_metadata_profiles(video_codec, pixel_format)
    resolved = {
        "color_space": color_space,
        "color_transfer": color_transfer,
        "color_primaries": color_primaries,
    }
    if not supported_profiles:
        for field_name, value in resolved.items():
            if value is not None:
                warnings.append(
                    _drop_color_metadata_warning(
                        field_name=field_name,
                        value=value,
                        video_codec=video_codec,
                        pixel_format=pixel_format,
                        reason="output plan",
                    )
                )
        return None, None, None

    allowed_values = {
        "color_space": {profile[0] for profile in supported_profiles},
        "color_transfer": {profile[1] for profile in supported_profiles},
        "color_primaries": {profile[2] for profile in supported_profiles},
    }
    for field_name, value in resolved.items():
        if value is not None and value not in allowed_values[field_name]:
            warnings.append(
                _drop_color_metadata_warning(
                    field_name=field_name,
                    value=value,
                    video_codec=video_codec,
                    pixel_format=pixel_format,
                    reason="output plan",
                )
            )
            resolved[field_name] = None

    specified_field_names = tuple(field_name for field_name, value in resolved.items() if value is not None)
    if specified_field_names and not any(
        all(resolved[field_name] == profile[index] for index, field_name in enumerate(resolved) if resolved[field_name] is not None)
        for profile in supported_profiles
    ):
        best_profile = max(
            supported_profiles,
            key=lambda profile: sum(
                resolved[field_name] == profile[index]
                for index, field_name in enumerate(resolved)
                if resolved[field_name] is not None
            ),
        )
        for index, field_name in enumerate(resolved):
            value = resolved[field_name]
            if value is not None and value != best_profile[index]:
                warnings.append(
                    _drop_color_metadata_warning(
                        field_name=field_name,
                        value=value,
                        video_codec=video_codec,
                        pixel_format=pixel_format,
                        reason="color metadata profile",
                    )
                )
                resolved[field_name] = None

    return resolved["color_space"], resolved["color_transfer"], resolved["color_primaries"]


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
    preserve_hdr10 = _is_exact_color_profile(
        clip.color_space,
        clip.color_transfer,
        clip.color_primaries,
        HDR10_COLOR_PROFILE,
    )
    pixel_format = _preferred_pixel_format(
        video_codec=video_codec,
        source_pixel_format=source_pixel_format,
        color_space=clip.color_space,
        color_transfer=clip.color_transfer,
        color_primaries=clip.color_primaries,
    )
    supported_pixel_formats = SUPPORTED_PIXEL_FORMATS[video_codec]
    if pixel_format not in supported_pixel_formats:
        pixel_format = DEFAULT_PIXEL_FORMATS[video_codec]
    if source_pixel_format and pixel_format != source_pixel_format:
        if preserve_hdr10 and pixel_format == HDR10_FALLBACK_PIXEL_FORMATS.get(video_codec):
            warnings.append(
                f"Pixel format '{source_pixel_format}' cannot preserve HDR10 color metadata with '{video_codec}'; using '{pixel_format}' instead."
            )
        else:
            warnings.append(
                f"Pixel format '{source_pixel_format}' is incompatible with '{video_codec}'; using '{pixel_format}' instead."
            )

    color_space, color_transfer, color_primaries = _resolve_color_metadata(
        video_codec=video_codec,
        pixel_format=pixel_format,
        color_space=clip.color_space,
        color_transfer=clip.color_transfer,
        color_primaries=clip.color_primaries,
        warnings=warnings,
    )

    audio_args: tuple[str, ...] = ("-c:a", "copy") if clip.audio_codec else ()

    return OutputEncodingPlan(
        video_codec=video_codec,
        pixel_format=pixel_format,
        video_bitrate=clip.video_bitrate,
        color_space=color_space,
        color_transfer=color_transfer,
        color_primaries=color_primaries,
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
