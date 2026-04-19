from pathlib import Path

import typer

from race_overlay.config import write_default_config

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
def render() -> None:
    """Render all configured videos with telemetry overlays."""
