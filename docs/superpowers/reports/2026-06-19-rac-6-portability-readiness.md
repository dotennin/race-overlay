# RAC-6 Portability Readiness Report

Date: 2026-06-19

## Scope

This report records the current migration boundary for the RAC-6 web port. The web package is a TCX-only React/browser implementation for activity overlay preview and short clip export. FIT is intentionally out of scope for the web port.

The target runtime has no Python backend runtime. Browser-readable video creation time is handled in the browser when the container exposes it in the first scanned bytes. Containers that cannot be read reliably by the browser may use an injected external API provider, but that API is caller-owned and not coupled to this repository's Python backend.

## Portable Surface

- Package entrypoint: `web/src/index.ts`
- React component: `RaceOverlay`
- Activity input: TCX via `readTcx` or `activityFile`
- Video input: browser `File` via `videoFile`
- Metadata fallback: `createExternalVideoMetadataProvider`
- Export path: browser canvas plus `MediaRecorder`
- Export measurement hooks: `exportWidth`, `exportHeight`, `exportDurationSeconds`, `onExportProgress`, `onExportReport`, `onExportComplete`
- Export capability probe: `readBrowserWebmExportCapabilities` and `serializeBrowserWebmExportCapabilities`
- Evidence evaluator: `evaluateBrowserPortabilityEvidence`

## Metadata Boundary

The browser metadata reader scans a video file slice first. This keeps local preview portable and avoids uploading the whole video just to discover common MP4/MOV creation time metadata.

For containers where browser parsing is not reliable, `createExternalVideoMetadataProvider` performs a partial upload first. The provider uploads the full file only if the external API explicitly replies that it needs a full upload. The web runtime does not know about a backend video path, a Vite proxy, a local `/api/video` endpoint, or the Python `ffprobe` wrapper.

Expected external API behavior:

- Accept `FormData` with the video head as field `video`
- Read `mode=partial`, `filename`, `size`, and `contentType`
- Return metadata immediately when possible
- Return `needsFullUpload: true` only when the full file is required
- Accept a second request with `mode=full` if needed

## Export Measurement Matrix

Run the measurement flow from a host app or the demo UI with a TCX file and a local video file. The default short export duration is 5 seconds, which is enough to compare browser feasibility without committing to long-video production behavior.

The package includes `examples/host-integration.tsx`, a typechecked host wrapper that imports from `race-overlay-web`, wires TCX/video `File` inputs, injects the caller-owned metadata API, and serializes browser export evidence. `npm run check:examples` runs after the library declarations are built so this example exercises the published package entrypoint instead of private source paths.

`npm run verify:consumer` adds a stricter package-surface smoke test. It creates a real `npm pack` tarball, unpacks it into a temporary consumer-style `node_modules`, provides minimal React peer stubs, then verifies ESM import, CJS require, CSS export resolution, packaged examples, and packaged evidence scripts. This catches release packaging regressions that a source-tree test or dry-run file list can miss.

Required measurements:

- 1280x720, 5 seconds, with `exportWidth={1280}` and `exportHeight={720}`
- 1920x1080, 5 seconds, with `exportWidth={1920}` and `exportHeight={1080}`

The demo UI exposes `Export width`, `Export height`, and `Export duration seconds` fields so the same measurement matrix can be collected without writing a host wrapper. It also includes a demo-only `Load sample measurement inputs` action that generates a TCX file and a short synthetic WebM video in the browser, then passes them through the same `activityFile` and `videoFile` props used by host applications.

After a successful export, use `Download measurement JSON` to save the evidence artifact. The JSON uses `schemaVersion: 1`, includes `generatedAt`, optional `activityName` and `videoName`, and embeds the measured `report` payload. Host applications can generate the same artifact with `serializeBrowserWebmExportReport(report, context)`.

If the browser blocks or fails export before a report is available, use `Download failure JSON`. Failure evidence uses the same `schemaVersion: 1`, sets `status: failed`, records the error message, and stores the attempted dimensions, FPS, bitrate, and duration. Host applications can generate this artifact with `serializeBrowserWebmExportFailure(error, context)`. This matters for portability because browser policies such as user-activation playback rules are part of the migration evidence, not just successful runs.

Capture the `onExportReport` payload for each run:

- `width`
- `height`
- `fps`
- `bitrateMbps`
- `mimeType`
- `elapsedMs`
- `outputBytes`
- `durationSeconds`
- `audioTrackCount`
- `memoryUsedBytes`, when the browser exposes it
- `playbackMode`, either `normal` or `muted-fallback`

The current implementation is ready to collect these numbers. This report does not claim production performance until successful browser measurements are recorded on each target hardware/browser combination.

The demo UI exposes `Cancel export` while a browser WebM export is in progress. Canceling stops the active recorder, suppresses download/report callbacks from that canceled run, and leaves the UI ready to retry the same export settings.

Before recording target-browser measurements, capture the `Browser export capabilities` line from the demo UI or call `readBrowserWebmExportCapabilities(video)` from a host wrapper. This probe reports WebM MIME support, canvas capture, video capture, source audio track count, and browser memory measurement availability. The line is intentionally separate from success/failure export evidence because a target can support `MediaRecorder` while still missing source-video capture or audio-track retention.

Use `Download capability JSON` in the demo UI to save this probe as a schema-valid artifact before running the 720p and 1080p exports. Host applications can generate the same artifact with `serializeBrowserWebmExportCapabilities(capabilities, context)`. Capability evidence uses `schemaVersion: 1`, sets `status: capabilities`, and embeds the exact probed fields so Safari, Firefox, Chromium, and production-device runs can be compared without relying on screenshots.

## Evidence Evaluation

Host applications and CI checks can call `evaluateBrowserPortabilityEvidence()` with one capability artifact plus the collected measurement artifacts. For full target-browser matrices, call `evaluateBrowserPortabilityEvidenceMatrix()` with one entry per browser or device target. The default threshold requires successful 1280x720 and 1920x1080 exports at 5 seconds, positive output bytes, WebM support, and canvas capture support. Muted playback fallback is reported as a warning because it is acceptable for controlled migration evidence but should remain visible.

After building the package, the same gate is available as a Node CLI:

```bash
cd web
npm run build
npm run evaluate:evidence -- \
  --capabilities path/to/capabilities.json \
  --measurement path/to/720p-measurement.json \
  --measurement path/to/1080p-measurement.json
```

For the final Safari, Firefox, Chromium, and production-device matrix, generate a release evidence workspace:

```bash
npm run scaffold:evidence -- --out release-evidence
```

The scaffold writes `release-evidence/evidence-matrix.json` plus per-target folders for capability, measurement, and failure artifacts. By default it requires Chromium, Firefox, Safari, a production device/browser target, 1280x720 5 seconds, 1920x1080 5 seconds, and 1920x1080 60 seconds. Use `--target <name>` to override the target list and `--require-audio-retention` when the release claim includes audio-retaining parity.

Evaluate the generated manifest after filling it with downloaded artifacts:

```bash
npm run evaluate:evidence -- --manifest release-evidence/evidence-matrix.json
```

The manifest lists target names, one capability artifact path, and measurement artifact paths for each target. Paths are resolved relative to the manifest file.

Set `requiredTargets` in the manifest so omitted targets fail the gate instead of silently disappearing from the matrix. A final migration manifest should list every target that matters for release, for example `chromium`, `firefox`, `safari`, and the production device/browser combination.

Set `requiredExports` in the same manifest when the release gate needs more than the default 1280x720 and 1920x1080 5-second checks. This is the intended path for long-duration, large-file, or additional resolution evidence: add the required width, height, and duration to the manifest, collect matching measurement artifacts for every required target, and let the matrix gate report missing evidence per target.

Manifest validation runs before evidence evaluation. Invalid manifest shapes, such as non-string target names or non-numeric export dimensions, fail with exit code 2 and a `Manifest ...` error. Capability and measurement evidence files are also validated before evaluation; existing malformed evidence payloads fail with exit code 2 and identify the bad file and field. Missing referenced artifacts are treated as incomplete evidence, so a newly scaffolded release workspace returns No-Go with exit code 1 until the files are collected.

Set `requireAudioRetention: true` only when claiming audio-retention parity. In that mode, evidence with `audioTrackCount: 0` or capability evidence with no source audio tracks becomes a No-Go instead of a warning. This keeps the current in-app browser evidence classified correctly: ready for controlled video-overlay migration evidence, not ready for audio-retention parity claims.

For audio parity gates, use:

```bash
npm run evaluate:evidence -- \
  --capabilities path/to/capabilities.json \
  --measurement path/to/720p-measurement.json \
  --measurement path/to/1080p-measurement.json \
  --require-audio-retention
```

## Current Target-Browser Evidence

The in-app browser target on 2026-06-19 produced successful 5 seconds measurement evidence for both required dimensions after muted playback fallback was added:

- `docs/superpowers/reports/evidence/2026-06-19-rac-6-iab-720p-success.json`
- `docs/superpowers/reports/evidence/2026-06-19-rac-6-iab-1080p-success.json`

These files prove that the demo can generate schema-valid completed 1280x720 and 1920x1080 evidence artifacts from a real browser run. Both reports used `playbackMode: muted-fallback` and recorded `audioTrackCount: 0`, so they prove video overlay export in this target but do not prove audio retention.

After user-activation playback priming, `RaceOverlay` starts `video.play()` inside the export button click handler and passes that promise into the browser export runtime. If a browser or automation target still rejects the first playback request, `startBrowserWebmExport()` retries with muted playback before failing the export. Successful measurement reports identify this path with `playbackMode: muted-fallback`; if the muted retry also fails, the failure evidence remains the authoritative artifact.

The demo sample generator has an opt-in `includeAudio` mode that mixes a generated Web Audio track into the sample WebM stream for host-side audio tests. The default in-app browser evidence remains video-only because that target did not reliably play the generated Web Audio WebM as a `<video>` source. Audio-retaining parity therefore still requires a real playable source video with audio, or a target-browser-compatible generated audio fixture, and a completed evidence report with `audioTrackCount` greater than `0`.

## Evidence

Use these commands as the portability evidence set:

```bash
cd web && npm run verify:portability
cd web && npm test -- --run
cd web && npm run build
cd web && npm run check:examples
cd web && npm run verify:consumer
cd web && npm run scaffold:evidence -- --out /tmp/race-overlay-release-evidence
cd web && npm run evaluate:evidence -- --capabilities src/test/fixtures/iab-capabilities.json --measurement ../docs/superpowers/reports/evidence/2026-06-19-rac-6-iab-720p-success.json --measurement ../docs/superpowers/reports/evidence/2026-06-19-rac-6-iab-1080p-success.json --json
cd web && npm run evaluate:evidence -- --manifest src/test/fixtures/evidence-matrix.json --json
PYTHONPATH=src uv run pytest -q tests/test_tcx_reader.py tests/test_sampling.py tests/test_alignment.py tests/test_portability_contract.py
git diff --check
```

`npm run verify:portability` is the package-level gate for host handoff. It runs the web tests, production build, host integration example typecheck, packed tarball consumer smoke, npm package dry-run, current in-app-browser evidence gate, and final release matrix No-Go check. Passing this gate means the package boundary is currently portable and the missing final evidence is still being reported; it does not mean the Safari, Firefox, Chromium, production-device, audio-retention, or long-duration gates are complete.

The web tests cover TCX reading, sampling, alignment, HUD config, browser metadata scan, partial-first external metadata API fallback, browser export reports, browser export capability evidence, browser portability evidence evaluation, release evidence scaffolding, host integration example typechecking, packed package consumer smoke, export cancellation/retry behavior, muted playback fallback, optional sample audio generation, React integration, public package exports, package build artifacts, and the no-Python-backend portability boundary.

The Python portability contract tests compare shared TCX, sampling, alignment, HUD preset, lap waterfall, and route projection fixtures against the web contract. This keeps the migration grounded in existing behavior without carrying Python into the browser runtime.

## Go / No-Go

Go for controlled migration of the React package into a host web application when the required workflow is TCX-only, uses local browser `File` objects, accepts WebM browser export, and can inject an external metadata API for containers whose creation time cannot be read in the browser.

Go for in-app browser package evidence because 1280x720 and 1920x1080 schema-valid completed target-browser measurement artifacts now exist.

No-Go for claiming audio-retaining export parity from the muted fallback evidence. The current in-app browser success reports recorded `audioTrackCount: 0`.

No-Go for claiming successful browser export performance across Safari, Firefox, Chromium, and production hardware until each target has its own successful 5 seconds measurement reports.

No-Go for production long-video batch export until target-browser measurements cover long durations, memory growth, audio retention, and large source files. The demo now covers basic cancellation and retry behavior for a single in-progress browser export, but not full batch orchestration.

No-Go for assuming all video creation time can be read locally in the browser. Some containers require a caller-owned API fallback.

No-Go for claiming parity with a native ffmpeg/ffprobe pipeline. WebCodecs and FFmpeg WASM are not implemented in this package; the current portable export path is `MediaRecorder`.

No-Go for FIT workflows in the web package. The accepted web input scope is TCX-only.

## Open Risks

- Browser `MediaRecorder` output format and codec support vary by browser.
- Safari, Firefox, and Chromium need separate measurement records.
- Long-video export can exceed browser memory or thermal limits.
- Batch export orchestration is not implemented; current cancellation/retry coverage is for one active browser export.
- Creation time metadata may be stored outside the scanned head slice or in unsupported container atoms.
- External metadata API privacy, size limits, authentication, and retention policy must be defined by the host application.
- OffscreenCanvas or Worker isolation is not implemented yet; the current canvas runtime is isolated enough to move later.
- WebCodecs and FFmpeg WASM remain possible future paths, but they are not prerequisites for this portable React package boundary.
