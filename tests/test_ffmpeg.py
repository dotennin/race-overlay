from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from race_overlay.ffmpeg import build_stream_compose_command, resolve_output_encoding_plan
from race_overlay.models import VideoClip


def make_clip(**overrides) -> VideoClip:
    clip = VideoClip(
        path=Path("clip.MP4"),
        creation_time=datetime(2026, 4, 19, 9, 5, 59, tzinfo=timezone.utc),
        duration_seconds=1.0,
        width=1280,
        height=720,
        fps=29.97,
        video_codec="h264",
        pixel_format="yuv420p",
        video_bitrate=16_000_000,
        color_space="bt709",
        color_primaries="bt709",
        color_transfer="bt709",
        audio_codec="aac",
        audio_bitrate=192_000,
    )
    return replace(clip, **overrides)


def test_resolve_output_encoding_plan_preserves_supported_source_settings() -> None:
    plan = resolve_output_encoding_plan(make_clip())

    assert plan.video_codec == "libx264"
    assert plan.pixel_format == "yuv420p"
    assert plan.video_bitrate == 16_000_000
    assert plan.color_space == "bt709"
    assert plan.color_transfer == "bt709"
    assert plan.color_primaries == "bt709"
    assert plan.audio_args == ("-c:a", "copy")
    assert plan.warnings == ()


def test_resolve_output_encoding_plan_downgrades_unsupported_source_settings() -> None:
    plan = resolve_output_encoding_plan(
        make_clip(
            path=Path("clip.MOV"),
            video_codec="vp9",
            pixel_format="yuv444p12le",
            color_space="bt2020nc",
            color_transfer="smpte2084",
            color_primaries="bt2020",
        )
    )

    assert plan.video_codec == "libx264"
    assert plan.pixel_format == "yuv420p"
    assert plan.color_space == "bt2020nc"
    assert plan.color_transfer == "smpte2084"
    assert plan.color_primaries == "bt2020"
    assert plan.audio_args == ("-c:a", "copy")
    assert plan.warnings == (
        "Unsupported source video codec 'vp9'; using 'libx264' instead.",
        "Pixel format 'yuv444p12le' is incompatible with 'libx264'; using 'yuv420p' instead.",
    )


def test_build_stream_compose_command_uses_raw_rgba_stdin() -> None:
    clip = make_clip()
    plan = resolve_output_encoding_plan(clip)
    source_path = Path("source.MP4")
    output_path = Path("output.MP4")

    command = build_stream_compose_command(
        source_path=source_path,
        clip=clip,
        output_path=output_path,
        plan=plan,
    )

    assert command == [
        "ffmpeg",
        "-y",
        "-i",
        "source.MP4",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        "1280x720",
        "-r",
        "29.97",
        "-i",
        "-",
        "-filter_complex",
        "[0:v][1:v]overlay=0:0[video]",
        "-map",
        "[video]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-b:v",
        "16000000",
        "-colorspace",
        "bt709",
        "-color_trc",
        "bt709",
        "-color_primaries",
        "bt709",
        "-c:a",
        "copy",
        "output.MP4",
    ]


def test_build_stream_compose_command_omits_non_positive_bitrate() -> None:
    clip = make_clip(video_bitrate=0)
    plan = resolve_output_encoding_plan(clip)

    command = build_stream_compose_command(
        source_path=Path("source.MP4"),
        clip=clip,
        output_path=Path("output.MP4"),
        plan=plan,
    )

    assert "-b:v" not in command
