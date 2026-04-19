from pathlib import Path

import typer

from race_overlay.config import write_default_config
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
