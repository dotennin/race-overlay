from pathlib import Path

import typer

from race_overlay.config import write_default_config
from race_overlay.editor_server import launch_editor
from race_overlay.pipeline import run_pipeline

app = typer.Typer(help="Overlay running telemetry onto race videos.")


@app.command()
def init(
    activity_file: str = typer.Option(..., "--activity-file"),
    config_path: Path = typer.Option(Path("overlay.yaml"), "--config-path"),
) -> None:
    """Create a starter overlay config in the current folder."""
    write_default_config(config_path, activity_file)
    typer.echo(f"Wrote config to {config_path}")


@app.command()
def render(
    config_path: Path = typer.Option(Path("overlay.yaml"), "--config-path"),
    only: str | None = typer.Option(None, "--only"),
) -> None:
    """Render all configured videos with telemetry overlays."""
    run_pipeline(config_path, only)
    typer.echo("Render completed")


@app.command()
def edit_hud(
    config_path: Path = typer.Option(Path("overlay.yaml"), "--config-path"),
    width: int = typer.Option(1280, "--width"),
    height: int = typer.Option(720, "--height"),
) -> None:
    """Launch the local HUD editor."""
    url = launch_editor(config_path=config_path, width=width, height=height)
    typer.echo(f"HUD editor available at {url}")
