import typer

app = typer.Typer(help="Overlay running telemetry onto race videos.")


@app.command()
def init() -> None:
    """Create a starter overlay config in the current folder."""


@app.command()
def render() -> None:
    """Render all configured videos with telemetry overlays."""
