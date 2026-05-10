from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import subprocess

from race_overlay.ffmpeg import build_cache_compose_command, build_stream_compose_command, compose_video, resolve_output_encoding_plan
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
        has_attached_pic=False,
        attached_pic_stream_index=None,
    )
    return replace(clip, **overrides)


def test_resolve_output_encoding_plan_preserves_supported_source_settings() -> None:
    plan = resolve_output_encoding_plan(make_clip())

    assert plan.video_codec == "libx264"
    assert plan.video_preset == "veryfast"
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
    assert plan.color_space is None
    assert plan.color_transfer is None
    assert plan.color_primaries is None
    assert plan.audio_args == ("-c:a", "copy")
    assert plan.warnings == (
        "Unsupported source video codec 'vp9'; using 'libx264' instead.",
        "Pixel format 'yuv444p12le' is incompatible with 'libx264'; using 'yuv420p' instead.",
        "Color space 'bt2020nc' is incompatible with output plan 'libx264/yuv420p'; dropping it.",
        "Color transfer 'smpte2084' is incompatible with output plan 'libx264/yuv420p'; dropping it.",
        "Color primaries 'bt2020' are incompatible with output plan 'libx264/yuv420p'; dropping them.",
    )


def test_resolve_output_encoding_plan_preserves_supported_hdr10_metadata_for_hevc_10bit() -> None:
    plan = resolve_output_encoding_plan(
        make_clip(
            video_codec="hevc",
            pixel_format="yuv420p10le",
            color_space="bt2020nc",
            color_transfer="smpte2084",
            color_primaries="bt2020",
        )
    )

    assert plan.video_codec == "libx265"
    assert plan.pixel_format == "yuv420p10le"
    assert plan.color_space == "bt2020nc"
    assert plan.color_transfer == "smpte2084"
    assert plan.color_primaries == "bt2020"
    assert plan.warnings == ()


def test_resolve_output_encoding_plan_chooses_hdr_compatible_pixel_format_when_needed() -> None:
    plan = resolve_output_encoding_plan(
        make_clip(
            video_codec="hevc",
            pixel_format="yuv444p12le",
            color_space="bt2020nc",
            color_transfer="smpte2084",
            color_primaries="bt2020",
        )
    )

    assert plan.video_codec == "libx265"
    assert plan.pixel_format == "yuv420p10le"
    assert plan.color_space == "bt2020nc"
    assert plan.color_transfer == "smpte2084"
    assert plan.color_primaries == "bt2020"
    assert plan.warnings == (
        "Pixel format 'yuv444p12le' cannot preserve HDR10 color metadata with 'libx265'; using 'yuv420p10le' instead.",
    )


def test_resolve_output_encoding_plan_upgrades_supported_hevc_pixel_format_for_hdr10() -> None:
    plan = resolve_output_encoding_plan(
        make_clip(
            video_codec="hevc",
            pixel_format="yuv420p",
            color_space="bt2020nc",
            color_transfer="smpte2084",
            color_primaries="bt2020",
        )
    )

    assert plan.video_codec == "libx265"
    assert plan.pixel_format == "yuv420p10le"
    assert plan.color_space == "bt2020nc"
    assert plan.color_transfer == "smpte2084"
    assert plan.color_primaries == "bt2020"
    assert plan.warnings == (
        "Pixel format 'yuv420p' cannot preserve HDR10 color metadata with 'libx265'; using 'yuv420p10le' instead.",
    )


def test_resolve_output_encoding_plan_preserves_supported_hdr10_hevc_pixel_format() -> None:
    plan = resolve_output_encoding_plan(
        make_clip(
            video_codec="hevc",
            pixel_format="yuv444p10le",
            color_space="bt2020nc",
            color_transfer="smpte2084",
            color_primaries="bt2020",
        )
    )

    assert plan.video_codec == "libx265"
    assert plan.pixel_format == "yuv444p10le"
    assert plan.color_space == "bt2020nc"
    assert plan.color_transfer == "smpte2084"
    assert plan.color_primaries == "bt2020"
    assert plan.warnings == ()


def test_resolve_output_encoding_plan_drops_only_incompatible_color_field() -> None:
    plan = resolve_output_encoding_plan(
        make_clip(
            video_codec="hevc",
            pixel_format="yuv420p10le",
            color_space="bt2020nc",
            color_transfer="smpte2084",
            color_primaries="bt709",
        )
    )

    assert plan.video_codec == "libx265"
    assert plan.pixel_format == "yuv420p10le"
    assert plan.color_space == "bt2020nc"
    assert plan.color_transfer == "smpte2084"
    assert plan.color_primaries is None
    assert plan.warnings == (
        "Color primaries 'bt709' are incompatible with color metadata profile for 'libx265/yuv420p10le'; dropping them.",
    )


def test_resolve_output_encoding_plan_reencodes_unsafe_audio_copy_codecs() -> None:
    plan = resolve_output_encoding_plan(make_clip(audio_codec="mp3", audio_bitrate=128_000))

    assert plan.audio_args == ("-c:a", "aac", "-b:a", "128000")
    assert plan.warnings == (
        "Audio codec 'mp3' is not safe to stream-copy after compositing; re-encoding audio as 'aac' at 128000 bps.",
    )


def test_resolve_output_encoding_plan_uses_default_audio_bitrate_for_unsafe_audio_copy_codecs() -> None:
    plan = resolve_output_encoding_plan(make_clip(audio_codec="pcm_s16le", audio_bitrate=None))

    assert plan.audio_args == ("-c:a", "aac", "-b:a", "192000")
    assert plan.warnings == (
        "Audio codec 'pcm_s16le' is not safe to stream-copy after compositing; re-encoding audio as 'aac' at 192000 bps.",
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
        "0:a:0?",
        "-c:v:0",
        "libx264",
        "-preset:v:0",
        "veryfast",
        "-pix_fmt:v:0",
        "yuv420p",
        "-b:v:0",
        "16000000",
        "-colorspace:v:0",
        "bt709",
        "-color_trc:v:0",
        "bt709",
        "-color_primaries:v:0",
        "bt709",
        "-c:a",
        "copy",
        "output.MP4",
    ]


def test_build_stream_compose_command_uses_audio_fallback_args() -> None:
    clip = make_clip(audio_codec="mp3", audio_bitrate=128_000)
    plan = resolve_output_encoding_plan(clip)

    command = build_stream_compose_command(
        source_path=Path("source.MP4"),
        clip=clip,
        output_path=Path("output.MP4"),
        plan=plan,
    )

    assert command[-5:] == ["-c:a", "aac", "-b:a", "128000", "output.MP4"]


def test_build_cache_compose_command_uses_single_audio_stream() -> None:
    clip = make_clip()
    plan = resolve_output_encoding_plan(clip)

    command = build_cache_compose_command(
        source_path=Path("source.MP4"),
        overlay_path=Path("overlay.mov"),
        output_path=Path("output.MP4"),
        plan=plan,
        attached_pic_stream_index=None,
    )

    assert command == [
        "ffmpeg",
        "-y",
        "-i",
        "source.MP4",
        "-i",
        "overlay.mov",
        "-filter_complex",
        "[0:v][1:v]overlay=0:0[video]",
        "-map",
        "[video]",
        "-map",
        "0:a:0?",
        "-c:v:0",
        "libx264",
        "-preset:v:0",
        "veryfast",
        "-pix_fmt:v:0",
        "yuv420p",
        "-b:v:0",
        "16000000",
        "-colorspace:v:0",
        "bt709",
        "-color_trc:v:0",
        "bt709",
        "-color_primaries:v:0",
        "bt709",
        "-c:a",
        "copy",
        "output.MP4",
    ]


def test_stream_and_cache_compose_commands_select_the_same_audio_stream() -> None:
    clip = make_clip()
    plan = resolve_output_encoding_plan(clip)

    stream_command = build_stream_compose_command(
        source_path=Path("source.MP4"),
        clip=clip,
        output_path=Path("output.MP4"),
        plan=plan,
    )
    cache_command = build_cache_compose_command(
        source_path=Path("source.MP4"),
        overlay_path=Path("overlay.mov"),
        output_path=Path("output.MP4"),
        plan=plan,
        attached_pic_stream_index=None,
    )

    assert stream_command[stream_command.index("-map") + 1] == "[video]"
    assert cache_command[cache_command.index("-map") + 1] == "[video]"
    assert stream_command[stream_command.index("0:a:0?")] == "0:a:0?"
    assert cache_command[cache_command.index("0:a:0?")] == "0:a:0?"


def test_build_stream_compose_command_omits_non_positive_bitrate() -> None:
    clip = make_clip(video_bitrate=0)
    plan = resolve_output_encoding_plan(clip)

    command = build_stream_compose_command(
        source_path=Path("source.MP4"),
        clip=clip,
        output_path=Path("output.MP4"),
        plan=plan,
    )

    assert "-b:v:0" not in command


def test_build_stream_compose_command_omits_dropped_color_metadata() -> None:
    clip = make_clip(
        video_codec="vp9",
        pixel_format="yuv444p12le",
        color_space="bt2020nc",
        color_transfer="smpte2084",
        color_primaries="bt2020",
    )
    plan = resolve_output_encoding_plan(clip)

    command = build_stream_compose_command(
        source_path=Path("source.MP4"),
        clip=clip,
        output_path=Path("output.MP4"),
        plan=plan,
    )

    assert "-colorspace:v:0" not in command
    assert "-color_trc:v:0" not in command
    assert "-color_primaries:v:0" not in command


def test_resolve_output_encoding_plan_accepts_custom_video_preset() -> None:
    plan = resolve_output_encoding_plan(make_clip(), video_preset="fast")

    assert plan.video_preset == "fast"


def test_resolve_output_encoding_plan_rejects_unsupported_video_preset() -> None:
    try:
        resolve_output_encoding_plan(make_clip(), video_preset="placebo")
    except ValueError as exc:
        assert "video_preset" in str(exc)
    else:
        raise AssertionError("unsupported preset should fail")


def test_build_stream_compose_command_omits_preset_for_prores() -> None:
    clip = make_clip(video_codec="prores", pixel_format="yuv422p10le")
    plan = resolve_output_encoding_plan(clip)

    command = build_stream_compose_command(
        source_path=Path("source.MOV"),
        clip=clip,
        output_path=Path("output.MOV"),
        plan=plan,
    )

    assert plan.video_codec == "prores_ks"
    assert "-preset:v:0" not in command


def test_compose_video_uses_resolved_encoding_plan(monkeypatch) -> None:
    clip = make_clip(
        video_codec="hevc",
        pixel_format="yuv420p10le",
        color_space="bt2020nc",
        color_transfer="smpte2084",
        color_primaries="bt2020",
        audio_codec="mp3",
        audio_bitrate=128_000,
    )
    plan = resolve_output_encoding_plan(clip)
    captured: dict[str, object] = {}

    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[bytes]:
        captured["command"] = command
        captured["check"] = check
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("race_overlay.ffmpeg.subprocess.run", fake_run)

    compose_video(
        source_path=Path("source.MP4"),
        overlay_path=Path("overlay.mov"),
        output_path=Path("output.MP4"),
        plan=plan,
        attached_pic_stream_index=4,
    )

    assert captured["check"] is True
    assert captured["command"] == [
        "ffmpeg",
        "-y",
        "-i",
        "source.MP4",
        "-i",
        "overlay.mov",
        "-filter_complex",
        "[0:v][1:v]overlay=0:0[video]",
        "-map",
        "[video]",
        "-map",
        "0:a:0?",
        "-c:v:0",
        "libx265",
        "-preset:v:0",
        "veryfast",
        "-pix_fmt:v:0",
        "yuv420p10le",
        "-b:v:0",
        "16000000",
        "-colorspace:v:0",
        "bt2020nc",
        "-color_trc:v:0",
        "smpte2084",
        "-color_primaries:v:0",
        "bt2020",
        "-c:a",
        "aac",
        "-b:a",
        "128000",
        "-map",
        "0:4",
        "-c:v:1",
        "copy",
        "-disposition:v:1",
        "attached_pic",
        "output.MP4",
    ]
