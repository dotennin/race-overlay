# Running Video Overlay Design

## Goal

Build a reusable standalone program that reads a FIT or TCX activity file, aligns it to all videos in the current media folder by timestamp, and burns a running-focused telemetry HUD onto each output clip with a single repeatable command.

## Current State

- The workspace is a media folder, not an existing application repository.
- Source media currently includes 46 video files (`.MP4` and `.mov`).
- There is currently no `.fit` file in the folder; the available activity file is `activity_22577902433.tcx`.
- `ffmpeg` and `ffprobe` are already installed and available in the environment.
- The available TCX activity spans `2026-04-19T00:45:05Z` to `2026-04-19T03:20:05Z`, with 9,343 trackpoints and a maximum distance of about 42.5 km.
- Some video files begin before the activity starts, so the design must explicitly handle clips that fall outside the activity timeline.

## Chosen Approach

Use a standalone Python CLI as the control plane and FFmpeg as the rendering engine.

Python is responsible for:

- parsing FIT and TCX into one internal sample model
- probing video metadata
- aligning each clip to the activity timeline
- computing display values for every overlay timestamp
- rendering a transparent HUD layer per clip

FFmpeg is responsible for:

- reading the source clip
- compositing the transparent HUD layer onto the video
- writing the final burned-in output

This approach is preferred because it is repeatable, easy to automate, and well-suited to batch processing many clips with a stable visual preset.

## User Workflow

### First-time setup

1. Put the activity file and source videos in a working folder.
2. Run an initialization command that creates a reusable configuration file.
3. Adjust the configuration once for layout, colors, offsets, and behavior.

### Repeatable production flow

1. Replace the input activity file and videos for a new event if needed.
2. Run a single render command.
3. The tool reads the saved configuration and produces all rendered clips.

The design intentionally optimizes for repeatability over interactive editing.

## Core Features

### Input support

- Support both FIT and TCX activity files.
- Accept a single activity file per run.
- Discover source videos by configurable glob patterns.

### Timeline alignment

- Read each video's creation timestamp from metadata using `ffprobe`.
- Align the clip start time against the activity timeline automatically.
- Allow one global offset for the whole batch.
- Allow per-video fine adjustment when individual clips need correction.
- Detect clips that start before the activity begins or end after it finishes.

### Overlay content

The default overlay preset should emphasize running metrics with this priority:

1. current pace
2. elapsed activity time
3. cumulative distance
4. current speed
5. heart rate
6. cadence
7. mini-map route with current position

Placement is configurable, but the default preset should ship with a usable layout so the tool works without custom design effort.

### Batch rendering

- Process all matching source videos in one run.
- Write outputs to a dedicated render directory.
- Store analysis and reusable intermediate files separately from final outputs.

## Architecture

## CLI layer

The CLI exposes the minimum surface needed for repeatable production:

- `init`: create a starter configuration for the current folder
- `render`: analyze, align, render overlays, and export final videos

Optional filtering for a single file or subset can be added if it stays small and supports debugging without changing the main workflow.

## Configuration layer

The configuration file should be YAML-based and contain:

- activity file path
- video input glob(s)
- output directory
- cache directory
- global time offset
- per-video overrides
- HUD field enable/disable switches
- layout positions
- font, color, spacing, and panel style settings
- behavior for out-of-range clips

Per-video overrides are keyed by filename and allow specific adjustments without changing the global preset.

## Activity parsing layer

This layer converts FIT and TCX into one normalized timeline structure that includes:

- timestamp
- latitude / longitude
- altitude
- distance
- speed
- pace
- heart rate
- cadence

The internal model must hide format differences so the rest of the pipeline treats FIT and TCX identically.

## Video analysis layer

This layer probes each source clip and produces:

- filename
- creation timestamp
- duration
- resolution
- frame rate

This metadata is the basis for alignment and output sizing.

## Alignment layer

For each clip:

1. Determine clip start and end timestamps from metadata.
2. Apply the configured global offset.
3. Apply any per-video fine adjustment.
4. Slice the activity timeline to the clip range.
5. Flag whether the clip is fully inside, partially overlapping, or fully outside the activity timeline.

This layer must produce explicit statuses rather than silently skipping data.

## HUD rendering layer

Python renders a transparent overlay layer for each clip using the normalized timeline.

The renderer is responsible for:

- interpolating values smoothly between activity samples
- drawing text panels for selected metrics
- drawing the route mini-map
- marking the runner's current position on the route
- scaling the overlay to the target video size

The visual preset should be deterministic and configuration-driven so future jobs can reuse the same look.

## Composition layer

FFmpeg composites:

- source video
- generated transparent overlay layer

into the final rendered file.

The composition stage should not contain business logic. All alignment and metric decisions should already be resolved before FFmpeg runs.

## Output Layout

The output folder structure should separate generated artifacts by purpose:

- `rendered/` for final videos
- `cache/` for analysis data, normalized samples, and temporary render assets
- configuration file at the project root or chosen working directory

This structure supports fast reruns and easier troubleshooting.

## Error Handling

The tool should fail loudly and specifically for:

- missing activity file
- unsupported or malformed FIT/TCX content
- unreadable video metadata
- missing `ffmpeg` or `ffprobe`
- invalid configuration

For per-video timeline issues, the program should report the clip status clearly and follow configured behavior instead of silently producing misleading overlays.

## Out-of-Scope

This design intentionally excludes:

- desktop GUI
- drag-and-drop timeline editing
- interactive visual layout editor
- advanced non-running sports profiles
- multi-activity merging in one render pass

These are deferred to keep the first version focused on repeatable batch production.

## Testing Strategy

The implementation plan should cover tests for these risk areas:

### Parser tests

- FIT parsing produces the normalized internal structure
- TCX parsing produces the same normalized internal structure
- missing optional metrics are handled explicitly and predictably

### Alignment tests

- automatic clip-to-activity matching based on creation time
- global offset application
- per-video offset application
- clips partially outside the activity window
- clips fully outside the activity window

### Renderer tests

- default overlay preset generates a transparent HUD asset
- enabled and disabled fields change the output composition inputs correctly
- mini-map route and current-position marker are produced from route data

### Pipeline tests

- one config can drive a whole batch render
- cached analysis can be reused on repeated runs when inputs have not changed

## Implementation Notes

- Because this is not currently a git repository, the design document can be saved locally but cannot be committed until the project is placed under git.
- The implementation should prefer stable, low-surprise libraries and keep the dependency surface small.
- The first version should optimize for correctness, repeatability, and maintainability rather than maximum rendering throughput.
