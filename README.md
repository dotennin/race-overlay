# Race Overlay

## Quick start

```bash
uv sync --dev
uv run race-overlay init --activity-file activity_22577902433.tcx
uv run race-overlay edit-hud --config-path overlay.yaml
uv run race-overlay render --config-path overlay.yaml
```

## HUD presets

The default HUD now uses the `broadcast-runner` preset. Customize it in either of two ways:

1. Edit `overlay.yaml` directly under `hud.theme` and `hud.widgets`
2. Run `uv run race-overlay edit-hud --config-path overlay.yaml` and save the result back to YAML

Legacy `hud.fields` configs still load and are mapped into widget visibility automatically.

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
