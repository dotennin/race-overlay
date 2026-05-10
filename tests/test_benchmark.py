from datetime import datetime, timezone
from pathlib import Path

import pytest

from race_overlay.benchmark import (
    BenchmarkResult,
    run_benchmark,
    format_benchmark_results,
)
from race_overlay.hud_schema import HudConfig, HudThemeConfig, HudWidgetConfig
from race_overlay.models import HudSample


def test_run_benchmark_measures_frame_render_time() -> None:
    """Benchmark should measure and return timing statistics for frame rendering."""
    hud_config = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="test-metric",
                type="metric_card",
                bindings={"value": "pace_seconds_per_km"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=80,
            )
        ],
    )
    hud_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    route_points = [(36.0832, 140.2106), (36.0834, 140.2108)]
    
    result = run_benchmark(
        width=1280,
        height=720,
        hud_config=hud_config,
        hud_sample=hud_sample,
        route_points=route_points,
        num_frames=50,
    )
    
    assert isinstance(result, BenchmarkResult)
    assert result.width == 1280
    assert result.height == 720
    assert result.num_frames == 50
    assert result.mean_ms > 0
    assert result.p50_ms > 0
    assert result.p95_ms > 0
    assert result.mean_ms <= result.p95_ms
    assert result.p50_ms <= result.p95_ms
    assert len(result.frame_times_ms) == 50


def test_run_benchmark_accepts_minimal_frames() -> None:
    """Benchmark should accept at least 10 frames for statistics."""
    hud_config = HudConfig(theme=HudThemeConfig(), widgets=[])
    hud_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=None,
        longitude=None,
        altitude_m=None,
        distance_m=None,
        speed_mps=None,
        pace_seconds_per_km=None,
        heart_rate_bpm=None,
        cadence_spm=None,
    )
    
    result = run_benchmark(
        width=640,
        height=480,
        hud_config=hud_config,
        hud_sample=hud_sample,
        route_points=[],
        num_frames=10,
    )
    
    assert result.num_frames == 10


def test_run_benchmark_rejects_too_few_frames() -> None:
    """Benchmark should reject fewer than 10 frames."""
    hud_config = HudConfig(theme=HudThemeConfig(), widgets=[])
    hud_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=None,
        longitude=None,
        altitude_m=None,
        distance_m=None,
        speed_mps=None,
        pace_seconds_per_km=None,
        heart_rate_bpm=None,
        cadence_spm=None,
    )
    
    with pytest.raises(ValueError, match="at least 10 frames"):
        run_benchmark(
            width=640,
            height=480,
            hud_config=hud_config,
            hud_sample=hud_sample,
            route_points=[],
            num_frames=5,
        )


def test_run_benchmark_passes_lap_states_to_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    hud_config = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="lap-waterfall",
                type="lap_waterfall",
                bindings={"value": "laps"},
                anchor="bottom-left",
                x=0,
                y=0,
                width=300,
                height=150,
            )
        ],
    )
    hud_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    lap_state = object()
    captured: list[dict] = []
    monkeypatch.setattr(
        "race_overlay.benchmark.render_hud_frame",
        lambda **kwargs: captured.append(kwargs) or None,
    )

    run_benchmark(
        width=1280,
        height=720,
        hud_config=hud_config,
        hud_sample=hud_sample,
        route_points=[],
        num_frames=10,
        lap_states={"lap-waterfall": lap_state},
        render_path="public",
    )

    assert captured
    assert captured[0]["lap_states"] == {"lap-waterfall": lap_state}


def test_run_benchmark_uses_prepared_renderer_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    hud_config = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="test-metric",
                type="metric_card",
                bindings={"value": "pace_seconds_per_km"},
                anchor="top-left",
                x=10,
                y=10,
                width=200,
                height=80,
            )
        ],
    )
    hud_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    calls: list[str] = []
    monkeypatch.setattr("race_overlay.benchmark.render_hud_frame", lambda **kwargs: calls.append("public") or None)
    monkeypatch.setattr("race_overlay.benchmark.render_prepared_hud_frame", lambda **kwargs: calls.append("prepared") or None)

    run_benchmark(
        width=1280,
        height=720,
        hud_config=hud_config,
        hud_sample=hud_sample,
        route_points=[(36.0832, 140.2106), (36.0834, 140.2108)],
        num_frames=10,
    )

    assert calls == ["prepared"] * 10


def test_run_benchmark_can_use_public_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    hud_config = HudConfig(theme=HudThemeConfig(), widgets=[])
    hud_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=None,
        longitude=None,
        altitude_m=None,
        distance_m=None,
        speed_mps=None,
        pace_seconds_per_km=None,
        heart_rate_bpm=None,
        cadence_spm=None,
    )
    calls: list[str] = []
    monkeypatch.setattr("race_overlay.benchmark.render_hud_frame", lambda **kwargs: calls.append("public") or None)
    monkeypatch.setattr("race_overlay.benchmark.render_prepared_hud_frame", lambda **kwargs: calls.append("prepared") or None)

    run_benchmark(
        width=1280,
        height=720,
        hud_config=hud_config,
        hud_sample=hud_sample,
        route_points=[],
        num_frames=10,
        render_path="public",
    )

    assert calls == ["public"] * 10


def test_format_benchmark_results_produces_human_readable_output() -> None:
    """Format function should produce readable statistics."""
    result = BenchmarkResult(
        width=1920,
        height=1080,
        num_frames=100,
        mean_ms=15.234,
        p50_ms=14.567,
        p95_ms=18.901,
        frame_times_ms=[15.0] * 100,
    )
    
    output = format_benchmark_results(result, variant_name="baseline")
    
    assert "1920x1080" in output
    assert "100" in output
    assert "15.23" in output or "15.2" in output
    assert "14.57" in output or "14.6" in output
    assert "18.90" in output or "18.9" in output
    assert "baseline" in output


def test_format_benchmark_results_shows_comparison_when_baseline_provided() -> None:
    """Format function should show percentage change when baseline is provided."""
    baseline = BenchmarkResult(
        width=1280,
        height=720,
        num_frames=100,
        mean_ms=20.0,
        p50_ms=19.0,
        p95_ms=25.0,
        frame_times_ms=[20.0] * 100,
    )
    
    current = BenchmarkResult(
        width=1280,
        height=720,
        num_frames=100,
        mean_ms=15.0,
        p50_ms=14.0,
        p95_ms=18.0,
        frame_times_ms=[15.0] * 100,
    )
    
    output = format_benchmark_results(current, variant_name="optimized", baseline=baseline)
    
    # Should show percentage improvement
    assert "%" in output
    # 15.0 is 25% faster than 20.0
    assert "25" in output or "-25" in output


def test_run_multi_variant_benchmark_compares_multiple_configs() -> None:
    """Multi-variant benchmark should run and compare multiple HUD configurations."""
    from race_overlay.benchmark import run_multi_variant_benchmark
    
    baseline_config = HudConfig(
        theme=HudThemeConfig(),
        widgets=[
            HudWidgetConfig(
                id="route-map",
                type="route_map",
                bindings={"value": "route_points"},
                anchor="top-left",
                x=0,
                y=0,
                width=200,
                height=200,
                visible=True,
            ),
            HudWidgetConfig(
                id="lap-waterfall",
                type="lap_waterfall",
                bindings={"value": "laps"},
                anchor="bottom-left",
                x=0,
                y=0,
                width=300,
                height=150,
                visible=True,
            ),
        ],
    )
    
    hud_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=36.0833,
        longitude=140.2106,
        altitude_m=25.0,
        distance_m=1000.0,
        speed_mps=3.58,
        pace_seconds_per_km=278.0,
        heart_rate_bpm=162,
        cadence_spm=178,
    )
    route_points = [(36.0832, 140.2106), (36.0834, 140.2108)]
    
    results = run_multi_variant_benchmark(
        width=1280,
        height=720,
        baseline_config=baseline_config,
        hud_sample=hud_sample,
        route_points=route_points,
        num_frames=50,
        widget_ids_to_toggle=["route-map", "lap-waterfall"],
    )
    
    # Should return dict with baseline and variant results
    assert "baseline" in results
    assert len(results) > 1  # baseline + at least one variant
    
    # Each result should be a BenchmarkResult
    for variant_name, result in results.items():
        assert isinstance(result, BenchmarkResult)
        assert result.num_frames == 50


def test_format_multi_variant_results_shows_all_comparisons() -> None:
    """Format function should display baseline and all variant comparisons."""
    from race_overlay.benchmark import format_multi_variant_results
    
    results = {
        "baseline": BenchmarkResult(
            width=1280,
            height=720,
            num_frames=50,
            mean_ms=20.0,
            p50_ms=19.0,
            p95_ms=25.0,
            frame_times_ms=[20.0] * 50,
        ),
        "no-route-map": BenchmarkResult(
            width=1280,
            height=720,
            num_frames=50,
            mean_ms=18.0,
            p50_ms=17.0,
            p95_ms=22.0,
            frame_times_ms=[18.0] * 50,
        ),
        "no-lap-waterfall": BenchmarkResult(
            width=1280,
            height=720,
            num_frames=50,
            mean_ms=16.0,
            p50_ms=15.0,
            p95_ms=20.0,
            frame_times_ms=[16.0] * 50,
        ),
    }
    
    output = format_multi_variant_results(results)
    
    # Should show baseline
    assert "baseline" in output.lower()
    assert "20.00" in output
    
    # Should show both variants
    assert "no-route-map" in output.lower()
    assert "18.00" in output
    assert "no-lap-waterfall" in output.lower()
    assert "16.00" in output
    
    # Should show comparisons
    assert "%" in output
