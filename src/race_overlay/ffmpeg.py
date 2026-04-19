import subprocess
from pathlib import Path


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
