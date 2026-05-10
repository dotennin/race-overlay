import time
from dataclasses import dataclass, replace

from race_overlay.hud import (
    RouteProjectionCursor,
    prime_route_map_caches,
    render_hud_frame,
    render_prepared_hud_frame,
    validate_hud_config,
)
from race_overlay.hud_schema import HudConfig
from race_overlay.models import HudSample


@dataclass(slots=True, frozen=True)
class BenchmarkResult:
    """Results from a frame rendering benchmark."""
    width: int
    height: int
    num_frames: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    frame_times_ms: list[float]


def run_benchmark(
    width: int,
    height: int,
    hud_config: HudConfig,
    hud_sample: HudSample,
    route_points: list[tuple[float, float]],
    num_frames: int,
    *,
    total_distance_m: float | None = None,
    lap_states: dict | None = None,
    render_path: str = "prepared",
) -> BenchmarkResult:
    """Run a benchmark rendering frames and measuring performance.
    
    Args:
        width: Frame width in pixels
        height: Frame height in pixels
        hud_config: HUD configuration to use
        hud_sample: Sample data to render
        route_points: GPS route points for the map
        num_frames: Number of frames to render (must be >= 10)
        total_distance_m: Optional total distance for progress bars
        
    Returns:
        BenchmarkResult with timing statistics
        
    Raises:
        ValueError: If num_frames < 10
    """
    if num_frames < 10:
        raise ValueError(f"num_frames must be at least 10 frames for statistics, got {num_frames}")
    if render_path not in {"prepared", "public"}:
        raise ValueError("render_path must be 'prepared' or 'public'")
    
    frame_times_ms: list[float] = []
    validated_hud_config = validate_hud_config(hud_config)
    visible_widgets = sorted(
        (widget for widget in validated_hud_config.widgets if widget.visible),
        key=lambda widget: widget.z_index,
    )
    route_map_cache_keys = prime_route_map_caches(
        widgets=visible_widgets,
        route_points=route_points,
        theme=validated_hud_config.theme,
        frame_width=width,
        frame_height=height,
    )
    route_projection_cursors = {
        widget.id: RouteProjectionCursor()
        for widget in visible_widgets
        if widget.type == "route_map"
    }
    
    for frame_index in range(num_frames):
        start = time.perf_counter()
        if render_path == "public":
            render_hud_frame(
                width=width,
                height=height,
                hud_value=hud_sample,
                route_points=route_points,
                hud_config=hud_config,
                elapsed_seconds=0,
                total_distance_m=total_distance_m,
                lap_states=lap_states,
            )
        else:
            render_prepared_hud_frame(
                width=width,
                height=height,
                hud_value=hud_sample,
                route_points=route_points,
                theme=validated_hud_config.theme,
                widgets=visible_widgets,
                elapsed_seconds=0,
                total_distance_m=total_distance_m,
                lap_states=lap_states,
                route_map_cache_keys=route_map_cache_keys,
                route_projection_cursors=route_projection_cursors,
                frame_index=frame_index,
            )
        end = time.perf_counter()
        frame_times_ms.append((end - start) * 1000)
    
    sorted_times = sorted(frame_times_ms)
    mean_ms = sum(frame_times_ms) / len(frame_times_ms)
    p50_ms = sorted_times[len(sorted_times) // 2]
    p95_ms = sorted_times[int(len(sorted_times) * 0.95)]
    
    return BenchmarkResult(
        width=width,
        height=height,
        num_frames=num_frames,
        mean_ms=mean_ms,
        p50_ms=p50_ms,
        p95_ms=p95_ms,
        frame_times_ms=frame_times_ms,
    )


def format_benchmark_results(
    result: BenchmarkResult,
    variant_name: str,
    *,
    baseline: BenchmarkResult | None = None,
) -> str:
    """Format benchmark results for display.
    
    Args:
        result: The benchmark result to format
        variant_name: Name of the variant being benchmarked
        baseline: Optional baseline result for comparison
        
    Returns:
        Formatted string with statistics
    """
    lines = [
        f"Benchmark: {variant_name}",
        f"  Resolution: {result.width}x{result.height}",
        f"  Frames:     {result.num_frames}",
        f"  Mean:       {result.mean_ms:.2f} ms/frame",
        f"  P50:        {result.p50_ms:.2f} ms/frame",
        f"  P95:        {result.p95_ms:.2f} ms/frame",
    ]
    
    if baseline is not None:
        mean_change = ((result.mean_ms - baseline.mean_ms) / baseline.mean_ms) * 100
        p50_change = ((result.p50_ms - baseline.p50_ms) / baseline.p50_ms) * 100
        p95_change = ((result.p95_ms - baseline.p95_ms) / baseline.p95_ms) * 100
        
        lines.extend([
            "",
            "  Comparison to baseline:",
            f"    Mean: {mean_change:+.1f}%",
            f"    P50:  {p50_change:+.1f}%",
            f"    P95:  {p95_change:+.1f}%",
        ])
    
    return "\n".join(lines)


def run_multi_variant_benchmark(
    width: int,
    height: int,
    baseline_config: HudConfig,
    hud_sample: HudSample,
    route_points: list[tuple[float, float]],
    num_frames: int,
    *,
    widget_ids_to_toggle: list[str] | None = None,
    total_distance_m: float | None = None,
    lap_states: dict | None = None,
    render_path: str = "prepared",
) -> dict[str, BenchmarkResult]:
    """Run benchmarks comparing baseline config with variants that toggle widgets.
    
    Args:
        width: Frame width in pixels
        height: Frame height in pixels
        baseline_config: Baseline HUD configuration
        hud_sample: Sample data to render
        route_points: GPS route points for the map
        num_frames: Number of frames to render (must be >= 10)
        widget_ids_to_toggle: List of widget IDs to toggle off for variants
        total_distance_m: Optional total distance for progress bars
        
    Returns:
        Dictionary mapping variant names to BenchmarkResult objects.
        Always includes "baseline" key, plus one entry per toggled widget.
        
    Raises:
        ValueError: If num_frames < 10
    """
    if widget_ids_to_toggle is None:
        widget_ids_to_toggle = []
    
    results: dict[str, BenchmarkResult] = {}
    
    # Run baseline
    results["baseline"] = run_benchmark(
        width=width,
        height=height,
        hud_config=baseline_config,
        hud_sample=hud_sample,
        route_points=route_points,
        num_frames=num_frames,
        total_distance_m=total_distance_m,
        lap_states=lap_states,
        render_path=render_path,
    )
    
    # Run variants with each widget toggled off
    for widget_id in widget_ids_to_toggle:
        # Create variant config with target widget disabled
        variant_widgets = [
            replace(w, visible=False) if w.id == widget_id else w
            for w in baseline_config.widgets
        ]
        variant_config = replace(baseline_config, widgets=variant_widgets)
        
        variant_name = f"no-{widget_id}"
        results[variant_name] = run_benchmark(
            width=width,
            height=height,
            hud_config=variant_config,
            hud_sample=hud_sample,
            route_points=route_points,
            num_frames=num_frames,
            total_distance_m=total_distance_m,
            lap_states=lap_states,
            render_path=render_path,
        )
    
    return results


def format_multi_variant_results(results: dict[str, BenchmarkResult]) -> str:
    """Format multi-variant benchmark results for display.
    
    Args:
        results: Dictionary mapping variant names to BenchmarkResult objects.
                Must include "baseline" key.
        
    Returns:
        Formatted string with baseline and all variant comparisons
    """
    if "baseline" not in results:
        raise ValueError("Results must include 'baseline' variant")
    
    baseline = results["baseline"]
    output_lines = []
    
    # Show baseline first
    output_lines.append(format_benchmark_results(baseline, variant_name="baseline"))
    
    # Show each variant with comparison to baseline
    for variant_name, result in results.items():
        if variant_name == "baseline":
            continue
        
        output_lines.append("")
        output_lines.append(format_benchmark_results(
            result,
            variant_name=variant_name,
            baseline=baseline,
        ))
    
    return "\n".join(output_lines)
