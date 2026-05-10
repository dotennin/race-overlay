from pathlib import Path
import cProfile
import io
import pstats

import click
import typer

from race_overlay.activity.loader import load_activity
from race_overlay.benchmark import format_multi_variant_results, run_multi_variant_benchmark
from race_overlay.config import load_config, resolve_path_from_config, write_default_config
from race_overlay.editor_server import launch_editor
from race_overlay.pipeline import run_pipeline
from race_overlay.sampling import lap_waterfall_states_for_widgets, sample_at

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
    run_pipeline(config_path, only, progress=typer.echo)
    typer.echo("Render completed")


@app.command()
def edit_hud(
    config_path: Path = typer.Option(Path("overlay.yaml"), "--config-path"),
    width: int = typer.Option(1280, "--width"),
    height: int = typer.Option(720, "--height"),
) -> None:
    """Launch the local HUD editor."""
    try:
        url = launch_editor(config_path=config_path, width=width, height=height)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc
    typer.echo(f"HUD editor available at {url}")


@app.command()
def benchmark_render(
    config_path: Path = typer.Option(Path("overlay.yaml"), "--config-path"),
    width: int = typer.Option(1280, "--width"),
    height: int = typer.Option(720, "--height"),
    num_frames: int = typer.Option(100, "--num-frames"),
    profile: bool = typer.Option(False, "--profile"),
    render_path: str = typer.Option("prepared", "--path"),
) -> None:
    """Benchmark HUD rendering performance with fixed sample data.
    
    Uses the activity and HUD config from the specified config file to
    measure frame rendering performance. Results include mean, p50, and p95
    timings per frame.
    """
    if num_frames < 10:
        raise click.BadParameter("num-frames must be at least 10")
    if render_path not in {"prepared", "public"}:
        raise click.BadParameter("path must be 'prepared' or 'public'")
    
    # Load config and activity
    try:
        config = load_config(config_path)
    except Exception as exc:
        raise click.BadParameter(f"Failed to load config: {exc}") from exc
    
    activity_path = resolve_path_from_config(config_path, config.activity_file)
    if not activity_path.exists():
        raise click.BadParameter(f"Activity file not found: {activity_path}")
    
    try:
        activity = load_activity(activity_path)
    except Exception as exc:
        raise click.BadParameter(f"Failed to load activity: {exc}") from exc
    
    if not activity.samples:
        raise click.BadParameter("Activity has no samples")
    if len(activity.samples) < 2:
        raise click.BadParameter("Activity must contain at least 2 samples")
    
    # Sample at midpoint of activity
    midpoint = activity.samples[len(activity.samples) // 2]
    hud_sample = sample_at(activity, midpoint.timestamp)
    
    # Extract route points
    route_points = [
        (sample.latitude, sample.longitude)
        for sample in activity.samples
        if sample.latitude is not None and sample.longitude is not None
    ]
    
    # Get total distance
    total_distance_m = None
    if activity.samples[-1].distance_m is not None:
        total_distance_m = activity.samples[-1].distance_m

    lap_states = lap_waterfall_states_for_widgets(config.hud, activity.laps, hud_sample.timestamp)
    
    # Find widgets to toggle (route_map and lap_waterfall)
    widget_ids_to_toggle = [
        widget.id
        for widget in config.hud.widgets
        if widget.type in ("route_map", "lap_waterfall") and widget.visible
    ]
    
    # Run multi-variant benchmark
    def run_benchmark_suite():
        return run_multi_variant_benchmark(
            width=width,
            height=height,
            baseline_config=config.hud,
            hud_sample=hud_sample,
            route_points=route_points,
            num_frames=num_frames,
            widget_ids_to_toggle=widget_ids_to_toggle,
            total_distance_m=total_distance_m,
            lap_states=lap_states,
            render_path=render_path,
        )

    if profile:
        profiler = cProfile.Profile()
        profiler.enable()
        results = run_benchmark_suite()
        profiler.disable()
    else:
        results = run_benchmark_suite()
    
    # Display results
    output = format_multi_variant_results(results)
    typer.echo(output)
    if profile:
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("cumtime").print_stats(25)
        typer.echo("")
        typer.echo(stream.getvalue())
