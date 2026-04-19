# Race Overlay

## Quick start

```bash
uv sync --dev
uv run race-overlay init --activity-file activity_22577902433.tcx
uv run race-overlay edit-hud --config-path overlay.yaml
uv run race-overlay render --config-path overlay.yaml
```

`edit-hud` starts a local server and prints a URL in the terminal. Keep that
command running, open the URL in your browser, make your HUD changes, and save
them back to `overlay.yaml` before continuing with `render`.

## HUD presets

The default HUD now uses the `broadcast-runner` preset. Customize it in either of two ways:

1. Edit `overlay.yaml` directly under `hud.theme` and `hud.widgets`
2. Run `uv run race-overlay edit-hud --config-path overlay.yaml`, then open the
   printed local URL in your browser, keep the server running while you edit,
   and save the result back to YAML

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
