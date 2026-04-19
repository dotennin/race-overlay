# Race Overlay

## Quick start

```bash
uv sync --dev
uv run race-overlay init --activity-file activity_22577902433.tcx
uv run race-overlay render --config-path overlay.yaml
```

## Per-video offset example

```yaml
overrides:
  DJI_20260419090559_0002_D.MP4:
    offset_seconds: 1.5
    outside_activity: skip
```

## Output folders

- `cache/`: normalized samples, frame sequences, overlay clips, render reports
- `rendered/`: final burned-in videos
