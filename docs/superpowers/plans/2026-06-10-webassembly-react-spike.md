# WebAssembly React Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first browser-accessible RAC-6 spike while keeping Python production behavior as the source of truth for portable activity parsing, sampling, and alignment.

**Architecture:** Add an isolated `web/` Vite + React + TypeScript package for browser validation only. Keep Python production rendering untouched. Browser-safe domain logic must be pinned to Python-generated portability contracts so this does not become an independent web rewrite.

**Tech Stack:** Vite, React, TypeScript, Vitest, jsdom, Canvas 2D.

---

### Task 1: Web Package And Runtime Tests

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/src/runtime/models.ts`
- Create: `web/src/runtime/tcx.ts`
- Create: `web/src/runtime/sampling.ts`
- Create: `web/src/runtime/alignment.ts`
- Create: `web/src/runtime/*.test.ts`

- [x] **Step 1: Write failing runtime tests**

Add Vitest tests that prove TCX parsing reads the checked-in fixture, running cadence is doubled, `sampleAt` interpolates distance/heart rate/speed/altitude, and `alignClip` marks partial overlap.

- [x] **Step 2: Verify tests fail**

Run: `cd web && npm test -- --run`

Expected: tests fail because runtime modules do not exist yet.

- [x] **Step 3: Implement minimal runtime**

Implement TypeScript models plus `readTcx`, `sampleAt`, and `alignClip` with the same behavior as the Python code for the covered cases.

- [x] **Step 4: Verify runtime tests pass**

Run: `cd web && npm test -- --run`

Expected: runtime tests pass.

### Task 2: React Component Preview

**Files:**
- Create: `web/src/components/RaceOverlay.tsx`
- Create: `web/src/components/RaceOverlay.test.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/main.tsx`
- Create: `web/src/styles.css`
- Create: `web/index.html`

- [x] **Step 1: Write failing component test**

Add a jsdom test that renders `<RaceOverlay />` with parsed activity data and verifies the component exposes a canvas preview and selected metric values.

- [x] **Step 2: Verify component test fails**

Run: `cd web && npm test -- --run`

Expected: test fails because the component is not implemented.

- [x] **Step 3: Implement minimal preview**

Implement `<RaceOverlay />` with file inputs, status metrics, and a Canvas 2D overlay preview drawn from the current sample.

- [x] **Step 4: Verify web tests pass**

Run: `cd web && npm test -- --run`

Expected: all web tests pass.

### Task 3: Developer Verification

**Files:**
- Modify only files under `web/` and RAC-6 docs.

- [x] **Step 1: Run Python baseline smoke tests**

Run: `uv run pytest -q tests/test_tcx_reader.py tests/test_sampling.py tests/test_alignment.py`

Expected: pass, proving the web spike did not disturb existing Python logic.

- [x] **Step 2: Start local web dev server**

Run: `cd web && npm run dev -- --host 127.0.0.1`

Expected: Vite prints a local URL for manual inspection.

### Task 4: Local Video Preview

**Files:**
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/src/test/setup.ts`

- [x] **Step 1: Add video upload test**

Add a component test proving a local video file can be selected, status text includes the filename, and video playback time advances the sampled HUD values.

- [x] **Step 2: Implement video-backed preview**

Add a `Video` input, local object URL management, a `<video controls>` preview, and a Canvas HUD overlay synced from `timeupdate`.

- [x] **Step 3: Verify component behavior**

Run: `cd web && npm test -- src/components/RaceOverlay.test.tsx --run`

Expected: component tests pass.

### Task 5: Browser WebM Export MVP

**Files:**
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/src/test/setup.ts`

- [x] **Step 1: Add export test**

Add a component test proving `Export WebM` appears once video/activity inputs are available and starts the browser export flow.

- [x] **Step 2: Implement composed canvas recording**

Use a hidden Canvas to draw video frames plus HUD, record it with `canvas.captureStream()` and `MediaRecorder`, then download a `.webm` file.

- [x] **Step 3: Verify export composition**

Add a regression assertion that video drawing is not cleared before HUD drawing in the export frame.

### Task 6: Sync Calibration And Audio Preservation

**Files:**
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/src/test/setup.ts`

- [x] **Step 1: Add offset calibration test**

Add a component test proving `TCX offset seconds` shifts HUD sampling relative to video playback time.

- [x] **Step 2: Implement offset input**

Add a numeric offset control and apply it to live preview sampling and export-frame sampling.

- [x] **Step 3: Preserve source audio when available**

When the browser exposes `video.captureStream()`, copy source audio tracks into the `MediaRecorder` output stream alongside the composed canvas video track.

- [x] **Step 4: Verify Web tests and build**

Run: `cd web && npm test -- --run` and `cd web && npm run build`

Expected: all web tests and production build pass.

### Task 7: Browser Beta Hardening

**Files:**
- Modify: `web/src/runtime/tcx.ts`
- Modify: `web/src/runtime/tcx.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/test/setup.ts`

- [x] **Step 1: Make TCX heart-rate parsing parent-aware**

Add a regression test for trackpoints that contain non-heart-rate `<Value>` elements before `<HeartRateBpm>`, then read heart rate only from the correct TCX parent wrapper.

- [x] **Step 2: Add export capability detection**

Detect `MediaRecorder` WebM support, prefer `video/webm;codecs=vp9,opus`, and show the current export capability in the controls.

- [x] **Step 3: Add export quality controls**

Expose `Export FPS` and `Export bitrate Mbps`, then pass those settings into `canvas.captureStream()` and `MediaRecorder`.

- [x] **Step 4: Verify Web tests and build**

Run: `cd web && npm test -- --run` and `cd web && npm run build`

Expected: all web tests and production build pass.

### Task 8: Sync UX And Range Safety

**Files:**
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/styles.css`

- [x] **Step 1: Clamp preview sampling to the TCX range**

Add a regression test proving large positive offsets clamp to the final TCX sample instead of extrapolating fake distance, heart-rate, and speed values.

- [x] **Step 2: Show TCX range status**

Display whether the current video time plus TCX offset is inside the activity range, before the start, or after the end.

- [x] **Step 3: Add offset nudge controls**

Add `-0.5s` and `+0.5s` controls for fine manual synchronization.

- [x] **Step 4: Verify Web tests and build**

Run: `cd web && npm test -- --run` and `cd web && npm run build`

Expected: all web tests and production build pass.

### Task 9: Python-Led Portability Contract

**Files:**
- Create: `tests/fixtures/portability_contract.json`
- Create: `tests/test_portability_contract.py`
- Create: `web/src/runtime/portabilityContract.test.ts`
- Modify: `web/src/runtime/sampling.ts`
- Modify: `web/src/runtime/sampling.test.ts`

- [x] **Step 1: Add a Python-generated contract fixture**

Capture the current Python core behavior for the checked-in TCX fixture, representative `sample_at` timestamps, and representative `align_clip` boundaries.

- [x] **Step 2: Guard the contract on the Python side**

Add a Python test proving the JSON contract still matches `read_tcx`, `sample_at`, and `align_clip`.

- [x] **Step 3: Guard the browser runtime against the Python contract**

Add a Vitest contract suite that parses the same TCX fixture and compares browser sampling/alignment output to the Python contract.

- [x] **Step 4: Fix the first portability mismatch**

Match Python `round()` behavior for exactly half-way interpolated integer metrics. JavaScript `Math.round()` rounds `102.5` to `103`, while Python rounds it to the nearest even integer (`102`).

- [x] **Step 5: Verify both sides**

Run: `PYTHONPATH=src uv run pytest -q tests/test_portability_contract.py` and `cd web && npm test -- --run`

Expected: Python and browser contract tests pass.

### Task 10: Lap Parsing Portability Coverage

**Files:**
- Create: `tests/fixtures/portable_laps.tcx`
- Modify: `tests/fixtures/portability_contract.json`
- Modify: `tests/test_portability_contract.py`
- Modify: `web/src/runtime/portabilityContract.test.ts`
- Modify: `web/src/runtime/tcx.ts`
- Modify: `web/src/runtime/tcx.test.ts`

- [x] **Step 1: Add a shared TCX lap fixture**

Add `portable_laps.tcx` to cover lap summary fields, missing-summary fallback derivation, heart-rate wrappers, run cadence normalization, max speed derivation, and signed net elevation delta.

- [x] **Step 2: Extend the Python portability contract**

Add `lapActivity` to the contract generated from Python `read_tcx`.

- [x] **Step 3: Verify browser parsing against Python lap behavior**

Add a Vitest contract assertion that parses the same `portable_laps.tcx` file and compares the full browser model to `lapActivity`.

- [x] **Step 4: Fix descendant-vs-child TCX parsing mismatch**

Make browser lap summary parsing read direct lap children only. This prevents cumulative trackpoint `DistanceMeters` from being mistaken for a lap summary distance; the fallback now derives `1900 - 1000 = 900` just like Python.

- [x] **Step 5: Verify both runtimes**

Run: `cd web && npm test -- --run`, `cd web && npm run build`, and `PYTHONPATH=src uv run pytest -q tests/test_tcx_reader.py tests/test_sampling.py tests/test_alignment.py tests/test_portability_contract.py`

Expected: all tests and build pass.

### Task 11: Browser Video Metadata Boundary

**Files:**
- Create: `web/src/runtime/videoMetadata.ts`
- Create: `web/src/runtime/videoMetadata.test.ts`

- [x] **Step 1: Keep video metadata portable by default**

Do not introduce a Python runtime dependency for the browser workflow. Define a browser-side metadata result that can either return container metadata or explicitly report that an external metadata API is needed.

- [x] **Step 2: Read browser-accessible MP4/MOV metadata**

Parse ISO BMFF/QuickTime boxes in the browser and read `mvhd.creation_time` when it is present in the scanned container metadata.

- [x] **Step 3: Report external API fallback explicitly**

When the browser cannot find readable creation time metadata, return `needsExternalApi: true` with a clear reason instead of silently inventing a timestamp or relying on Python.

- [x] **Step 4: Add browser metadata tests**

Use a synthetic MP4 fixture with an `mvhd` box to prove the browser runtime can parse creation time, and add a negative case for unsupported/unreadable containers.

- [x] **Step 5: Verify frontend and Python contract**

Run: `cd web && npm test -- --run`, `cd web && npm run build`, and `PYTHONPATH=src uv run pytest -q tests/test_portability_contract.py`

Expected: browser metadata tests, web tests, production build, and Python portability contract pass.

### Task 12: Browser Workflow Uses Portable Video Metadata

**Files:**
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`

- [x] **Step 1: Keep preview and metadata local**

Keep local video upload as the browser preview/playback source and read container metadata in the browser when possible.

- [x] **Step 2: Remove backend-specific controls**

Do not expose backend path fields or Python-specific probe controls in the browser workflow.

- [x] **Step 3: Display browser metadata or fallback need**

Show browser-parsed name, `creationTime`, and source when available; otherwise show `Needs external metadata API`.

- [x] **Step 4: Test success and error paths**

Add component tests proving local upload can display browser container metadata, unsupported containers do not call a backend, and an injected external metadata provider is used only as a fallback.

- [x] **Step 5: Verify web package**

Run: `cd web && npm test -- --run` and `cd web && npm run build`

Expected: all web tests and production build pass.

### Task 13: No Python Backend Runtime Boundary

**Files:**
- Create: `web/src/runtime/portabilityBoundary.test.ts`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Guard against backend probe coupling**

Add a browser-side regression test that scans the web package for the removed Python video probe integration terms, including `videoProbeApi`, backend path controls, Vite probe env names, and `/api/video` routes.

- [x] **Step 2: Keep external metadata as an injected API seam**

Keep difficult video container metadata outside the default runtime by using the existing `externalVideoMetadataProvider` prop instead of introducing a local Python API or Vite proxy.

- [x] **Step 3: Verify boundary, web package, and Python contract**

Run: `cd web && npm test -- --run`, `cd web && npm run build`, and `PYTHONPATH=src uv run pytest -q tests/test_portability_contract.py`

Expected: the browser boundary test, all web tests, production build, and Python portability contract pass.

### Task 14: HUD Schema And Preset Portability

**Files:**
- Create: `web/src/runtime/hudConfig.ts`
- Create: `web/src/runtime/hudConfig.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/runtime/portabilityContract.test.ts`
- Modify: `tests/test_portability_contract.py`
- Modify: `tests/fixtures/portability_contract.json`

- [x] **Step 1: Add HUD config tests before implementation**

Add Web tests for the Python `broadcast_runner_preset()` shape and for `<RaceOverlay hudConfig={...}>` drawing configured widgets instead of a fixed overlay.

- [x] **Step 2: Port the HUD config schema and default preset**

Add TypeScript `HudThemeConfig`, `HudWidgetConfig`, `HudConfig`, `broadcastRunnerPreset()`, and `serializeHudConfig()` with Python-compatible snake_case serialization.

- [x] **Step 3: Render from HUD widgets**

Make the browser preview/export HUD path render visible widgets by `zIndex`, including minimal `context_card`, `progress_bar`, `stat_block`, `metric_card`, and `route_map` support.

- [x] **Step 4: Pin HUD preset to the Python contract**

Add `hudPreset` to the Python-generated portability contract and assert that Web serialization matches it.

- [x] **Step 5: Verify contract and component behavior**

Run: `cd web && npm test -- --run src/runtime/portabilityContract.test.ts src/runtime/hudConfig.test.ts src/components/RaceOverlay.test.tsx` and `PYTHONPATH=src uv run pytest -q tests/test_portability_contract.py`

Expected: Web HUD config tests, Web/Python portability contract, and component rendering tests pass.

### Task 15: HUD Renderer Runtime Boundary

**Files:**
- Create: `web/src/runtime/hudRenderer.ts`
- Create: `web/src/runtime/hudRenderer.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add renderer runtime test**

Add a Web runtime test proving `drawHudFrame()` renders visible widgets from `HudConfig` onto a canvas.

- [x] **Step 2: Move HUD drawing out of React**

Extract configured HUD drawing into `web/src/runtime/hudRenderer.ts` so the React component calls a portable runtime function instead of owning renderer internals.

- [x] **Step 3: Keep preview/export behavior wired through runtime**

Use `drawHudFrame()` for both live preview and composed export frames.

- [x] **Step 4: Verify runtime and component behavior**

Run: `cd web && npm test -- --run src/runtime/hudRenderer.test.ts src/components/RaceOverlay.test.tsx`

Expected: renderer runtime and component tests pass.

### Task 16: Lap Waterfall Portability

**Files:**
- Create: `web/src/runtime/lapWaterfall.ts`
- Create: `web/src/runtime/lapWaterfall.test.ts`
- Modify: `web/src/runtime/hudRenderer.ts`
- Modify: `web/src/runtime/hudRenderer.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/runtime/portabilityContract.test.ts`
- Modify: `tests/test_portability_contract.py`
- Modify: `tests/fixtures/portability_contract.json`

- [x] **Step 1: Port Python lap waterfall state semantics**

Implement `lapWaterfallState()` in the browser runtime with Python-compatible completed lap detection, visible row windowing, dimming, fade opacity, and scroll transition state.

- [x] **Step 2: Pin lap waterfall state to the Python contract**

Add representative `lapWaterfallState` examples to the Python-generated portability contract and assert the browser runtime matches them.

- [x] **Step 3: Render lap waterfall widgets from widget-scoped state**

Teach `drawHudFrame()` to accept `lapStates` and render configured `lap_waterfall` widgets with lap number, distance, pace, elevation, and heart-rate columns.

- [x] **Step 4: Wire RaceOverlay preview/export through lap states**

Compute `lapWaterfallStatesForWidgets()` from the current activity laps and sampled timestamp, then pass those states into live preview and export frame rendering.

- [x] **Step 5: Verify runtime, renderer, component, and contract tests**

Run: `cd web && npm test -- --run src/runtime/lapWaterfall.test.ts src/runtime/hudRenderer.test.ts src/components/RaceOverlay.test.tsx src/runtime/portabilityContract.test.ts` and `PYTHONPATH=src uv run pytest -q tests/test_portability_contract.py`

Expected: browser lap waterfall runtime/renderer/component tests and Python/Web portability contract pass.

### Task 17: Route Map Runtime Portability

**Files:**
- Create: `web/src/runtime/routeMap.ts`
- Create: `web/src/runtime/routeMap.test.ts`
- Modify: `web/src/runtime/hudRenderer.ts`
- Modify: `web/src/runtime/hudRenderer.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/test/setup.ts`

- [x] **Step 1: Port route projection primitives**

Add browser runtime support for projecting the current GPS sample onto the nearest route segment, splitting completed/remaining route points, and projecting route coordinates into a widget area while preserving aspect ratio.

- [x] **Step 2: Render route map from real route points**

Update `drawHudFrame()` so `route_map` widgets draw the remaining route, completed route, and current position marker from `routePoints` and `sample` instead of drawing only a placeholder box.

- [x] **Step 3: Wire RaceOverlay route points**

Derive route points from activity samples with latitude/longitude and pass them into preview and export frame rendering.

- [x] **Step 4: Verify runtime, renderer, and component behavior**

Run: `cd web && npm test -- --run src/runtime/routeMap.test.ts src/runtime/hudRenderer.test.ts src/components/RaceOverlay.test.tsx`

Expected: route projection runtime, HUD renderer, and React component tests pass.

### Task 18: Route Projection Contract Coverage

**Files:**
- Modify: `tests/test_portability_contract.py`
- Modify: `tests/fixtures/portability_contract.json`
- Modify: `web/src/runtime/portabilityContract.test.ts`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add Python route projection examples**

Extend the Python-generated portability contract with representative `_resolve_route_projection()` and `_split_route_points()` outputs from the shared TCX fixture.

- [x] **Step 2: Verify Web route projection against Python**

Assert that `resolveRouteProjection()` and `splitRoutePoints()` match the Python-generated contract examples.

- [x] **Step 3: Normalize tuple/list contract output**

Normalize Python tuples to JSON-compatible lists in the contract builder so Python self-checks compare the same structure that Web reads.

- [x] **Step 4: Verify route contract on both sides**

Run: `cd web && npm test -- --run src/runtime/portabilityContract.test.ts src/runtime/routeMap.test.ts` and `PYTHONPATH=src uv run pytest -q tests/test_portability_contract.py`

Expected: route projection runtime tests and Python/Web portability contract pass.

### Task 19: Browser Export Runtime Boundary

**Files:**
- Create: `web/src/runtime/browserExport.ts`
- Create: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/test/setup.ts`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add export runtime tests**

Add browser runtime tests for WebM support detection, canvas stream recording, audio track preservation, and encoder FPS/bitrate options.

- [x] **Step 2: Extract MediaRecorder flow out of React**

Move canvas creation, `captureStream()`, source audio copying, `MediaRecorder` setup, frame loop, and export completion blob handling into `web/src/runtime/browserExport.ts`.

- [x] **Step 3: Keep RaceOverlay as orchestration only**

Make `<RaceOverlay />` call `startBrowserWebmExport()` and provide a frame renderer callback that composes video + HUD using the existing runtime.

- [x] **Step 4: Verify runtime and component behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts src/components/RaceOverlay.test.tsx`

Expected: export runtime tests and existing React export tests pass.

### Task 20: Export Completion React API

**Files:**
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/test/setup.ts`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add callback API test**

Add a React component test proving `<RaceOverlay onExportComplete={...} />` receives the exported WebM `Blob` after browser export finishes.

- [x] **Step 2: Expose export completion to callers**

Add `onExportComplete?: (blob: Blob) => void` to `RaceOverlayProps` and invoke it when the browser export runtime resolves.

- [x] **Step 3: Keep download behavior as demo default**

Continue downloading the WebM in the demo workflow while also notifying the embedding React caller.

- [x] **Step 4: Keep export tests clean**

Stub anchor click navigation in the jsdom setup so export completion tests exercise download setup without noisy navigation errors.

- [x] **Step 5: Verify component behavior**

Run: `cd web && npm test -- --run src/components/RaceOverlay.test.tsx`

Expected: component tests pass, including export completion callback coverage.

### Task 21: React File Prop Inputs

**Files:**
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add caller-owned file input coverage**

Add a React component test proving `<RaceOverlay activityFile={...} videoFile={...} />` loads TCX and video files without requiring the demo file inputs.

- [x] **Step 2: Expose portable file props**

Add `activityFile?: File | null` and `videoFile?: File | null` to `RaceOverlayProps`, and route those props through the same TCX/video loading path as manual input.

- [x] **Step 3: Make TCX file text reading browser-compatible**

Read TCX files with `File.text()` when available and a `FileReader` fallback for browser/test environments that do not expose `Blob.text()`.

- [x] **Step 4: Verify component behavior**

Run: `cd web && npm test -- --run src/components/RaceOverlay.test.tsx`

Expected: component tests pass, including caller-provided TCX and video `File` props.

### Task 22: React HUD And Export Callback API

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add callback API coverage**

Add runtime and component tests for `initialHud`, `onHudChange`, and `onExportProgress`, matching the React call shape in the portability design.

- [x] **Step 2: Add browser export progress reporting**

Report export progress from `startBrowserWebmExport()` with current time, optional duration, and normalized ratio.

- [x] **Step 3: Add portable HUD config props**

Support `initialHud` as the portable uncontrolled HUD input while preserving `hudConfig` compatibility, and notify callers through `onHudChange` when the component edits HUD config.

- [x] **Step 4: Verify runtime and component behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts src/components/RaceOverlay.test.tsx`

Expected: export progress, initial HUD input, HUD change callback, and existing component tests pass.

### Task 23: Public Web API Entry Point

**Files:**
- Create: `web/src/index.ts`
- Create: `web/src/publicApi.test.ts`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add public API coverage**

Add a test proving callers can import the portable React component and browser runtime helpers from `web/src/index.ts`.

- [x] **Step 2: Export component, types, and runtime helpers**

Re-export `RaceOverlay`, `RaceOverlayProps`, HUD config types, TCX parsing, sampling, alignment, browser export, and browser metadata helpers from a single public entry point.

- [x] **Step 3: Verify public API behavior**

Run: `cd web && npm test -- --run src/publicApi.test.ts`

Expected: public API imports resolve and expose the expected component/runtime functions.

### Task 24: Portable Package Build

**Files:**
- Modify: `web/package.json`
- Create: `web/tsconfig.lib.json`
- Create: `web/vite.lib.config.ts`
- Create: `web/src/packageManifest.test.ts`
- Create: `web/src/packageBuildArtifacts.test.ts`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add package manifest coverage**

Add a test proving the web package declares stable `main`, `module`, `types`, `exports`, `files`, and build scripts for library consumption.

- [x] **Step 2: Add library and type builds**

Keep the demo app build, then add declaration generation and a Vite library build that emits ESM and UMD bundles from `src/index.ts` with React externals.

- [x] **Step 3: Preserve all final dist artifacts**

Run the app build before the type and library builds so the app build does not clear the package entrypoints from `dist`.

- [x] **Step 4: Verify package artifacts**

Run: `cd web && npm run build && npm test -- --run src/packageBuildArtifacts.test.ts src/packageManifest.test.ts`

Expected: final `dist` contains demo app assets, library JavaScript bundles, and `dist/types/index.d.ts`.

### Task 25: Export Measurement Report API

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/index.ts`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add export report coverage**

Add runtime and component tests proving browser export produces a structured report with dimensions, FPS, bitrate, MIME type, elapsed time, output bytes, optional duration, audio track count, and optional browser memory observation.

- [x] **Step 2: Keep blob completion compatibility**

Keep `BrowserWebmExportRun.done` resolving the exported `Blob`, and add a separate `report` promise so existing callers do not need to change.

- [x] **Step 3: Expose report and dimensions through React**

Add `exportWidth`, `exportHeight`, and `onExportReport` to `<RaceOverlay />` so embedding apps can run 720p/1080p measurements and collect Go/No-Go evidence.

- [x] **Step 4: Export report types publicly**

Export `BrowserWebmExportReport` from the package entrypoint so host applications can type their measurement storage.

- [x] **Step 5: Verify measurement API behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts src/components/RaceOverlay.test.tsx`

Expected: report promise, React report callback, configured dimensions, and existing export behavior pass.

### Task 26: External Metadata API Provider

**Files:**
- Create: `web/src/runtime/externalVideoMetadataApi.ts`
- Create: `web/src/runtime/externalVideoMetadataApi.test.ts`
- Modify: `web/src/index.ts`
- Modify: `web/src/publicApi.test.ts`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add partial upload fallback coverage**

Add tests proving an external metadata provider uploads only the video head first, returns metadata without a full upload when possible, and uploads the full file only when the API explicitly requests it.

- [x] **Step 2: Implement a generic external provider factory**

Add `createExternalVideoMetadataProvider()` that accepts an arbitrary endpoint and returns the existing `externalVideoMetadataProvider` callback shape used by `<RaceOverlay />`.

- [x] **Step 3: Keep Python/backend coupling out of runtime**

Do not hard-code a local Python API, Vite proxy, or backend path. The provider only knows about the caller-supplied endpoint and uploads `FormData` with `mode=partial` or `mode=full`.

- [x] **Step 4: Export the provider publicly**

Export the factory and response/options types from `web/src/index.ts` so embedding applications can opt into API fallback without writing their own upload plumbing.

- [x] **Step 5: Verify provider and boundary behavior**

Run: `cd web && npm test -- --run src/runtime/externalVideoMetadataApi.test.ts src/publicApi.test.ts src/runtime/portabilityBoundary.test.ts`

Expected: partial-first upload behavior, public API exports, and no-Python-backend boundary tests pass.

### Task 27: Short Clip Export Duration

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add short export runtime coverage**

Add a runtime test proving browser export stops automatically at a configured short export duration and reports that duration in the export measurement report.

- [x] **Step 2: Add export duration option**

Add `exportDurationSeconds` to `startBrowserWebmExport()` and use it as the progress/report duration target when present.

- [x] **Step 3: Expose short export duration in React**

Add `exportDurationSeconds` to `<RaceOverlay />`, default it to 5 seconds for Spike-friendly exports, and expose an `Export duration seconds` control in the demo UI.

- [x] **Step 4: Verify runtime and React behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts src/components/RaceOverlay.test.tsx`

Expected: short duration auto-stop, configured React export duration, and existing export behavior pass.

### Task 28: Portability Readiness Report

**Files:**
- Create: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Create: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add readiness report coverage**

Add a Vitest contract that requires the readiness report to cover TCX-only scope, no Python backend runtime, external metadata API fallback, browser export measurement hooks, 720p/1080p 5-second measurement requirements, and Go/No-Go risks.

- [x] **Step 2: Document the portable migration boundary**

Write the report as a migration artifact: browser `File` inputs, TCX reader, `MediaRecorder` export, package API, `createExternalVideoMetadataProvider`, partial upload fallback, and the remaining risks that prevent claiming full production long-video parity.

- [x] **Step 3: Verify the report contract**

Run: `cd web && npm test -- --run src/portabilityReadinessReport.test.ts`

Expected: readiness report includes the migration boundary, evidence commands, measurement matrix, and explicit Go/No-Go guidance.

### Task 29: Demo Export Measurement Controls

**Files:**
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add demo measurement UI coverage**

Add a component test proving the demo UI exposes export width and height controls, can collect a 1920x1080 5-second report, and renders a visible measurement summary after export.

- [x] **Step 2: Wire export dimensions through UI state**

Initialize export width/height from the existing props, keep prop updates reflected in local UI state, and pass the selected values into `startBrowserWebmExport()`.

- [x] **Step 3: Render the latest measurement report**

Display the latest browser export report in the demo UI with dimensions, duration, MIME type, elapsed time, output size, audio track count, and memory availability.

- [x] **Step 4: Update readiness guidance**

Document that the demo UI can run the 720p/1080p measurement matrix directly through `Export width`, `Export height`, and `Export duration seconds`.

- [x] **Step 5: Verify component behavior**

Run: `cd web && npm test -- --run src/components/RaceOverlay.test.tsx`

Expected: component tests pass, including the demo measurement controls and report summary.

### Task 30: Browser-Generated Demo Measurement Inputs

**Files:**
- Create: `web/src/demo/sampleInputs.ts`
- Create: `web/src/demo/sampleInputs.test.ts`
- Create: `web/src/App.test.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add sample input coverage**

Add tests proving the demo can create a portable TCX `File` and a browser-generated WebM video `File` without using Python or a backend.

- [x] **Step 2: Implement demo-only sample input generation**

Generate the sample TCX in memory and synthesize a short WebM video from a browser canvas plus `MediaRecorder`.

- [x] **Step 3: Wire sample inputs through existing props**

Add a demo button that loads the generated files into `<RaceOverlay activityFile={...} videoFile={...} />`, keeping the core package boundary unchanged.

- [x] **Step 4: Verify App behavior**

Run: `cd web && npm test -- --run src/demo/sampleInputs.test.ts src/App.test.tsx`

Expected: demo sample files are generated and loaded through the same portable file props used by host applications.

### Task 31: Export Play-Rejection Recovery

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add play rejection coverage**

Add a runtime regression test for browsers that reject `video.play()` during export and would otherwise leave the export promise pending.

- [x] **Step 2: Reject export promises on source playback failure**

Stop the recorder, cancel the frame loop, and reject both `done` and `report` with a clear export error when source playback cannot start.

- [x] **Step 3: Surface the export error in React**

Catch `done`/`report` failures in `<RaceOverlay />`, clear the exporting status, and show the playback error instead of hanging.

- [x] **Step 4: Verify runtime and component behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts src/components/RaceOverlay.test.tsx`

Expected: source playback rejection does not hang the export runtime or UI.

### Task 32: Measurement Evidence JSON Artifact

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/index.ts`
- Modify: `web/src/publicApi.test.ts`
- Modify: `web/src/styles.css`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add evidence serialization coverage**

Add a runtime test for stable measurement evidence JSON with `schemaVersion`, `generatedAt`, optional source names, and the browser export report payload.

- [x] **Step 2: Expose serialization in the public API**

Implement `serializeBrowserWebmExportReport(report, context)` and export it with evidence context/result types from the package entrypoint.

- [x] **Step 3: Render and download evidence from the demo UI**

After export, show the JSON evidence block and a `Download measurement JSON` action so 720p/1080p measurements can be saved as reviewable artifacts.

- [x] **Step 4: Document the artifact contract**

Update the readiness report to describe the JSON evidence shape and the matching public runtime helper.

- [x] **Step 5: Verify affected behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts src/components/RaceOverlay.test.tsx src/publicApi.test.ts src/portabilityReadinessReport.test.ts`

Expected: serializer, public API export, demo evidence UI, and readiness contract tests pass.

### Task 33: Export Failure Evidence JSON Artifact

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/index.ts`
- Modify: `web/src/publicApi.test.ts`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add failure evidence serialization coverage**

Add a runtime test for stable failed export evidence JSON with `schemaVersion`, `status: failed`, error text, and attempted export settings.

- [x] **Step 2: Expose failure serialization publicly**

Implement `serializeBrowserWebmExportFailure(error, context)` and export it with failure evidence types from the package entrypoint.

- [x] **Step 3: Render and download failure evidence from the demo UI**

When export fails before a measurement report exists, show the failure evidence JSON and a `Download failure JSON` action instead of leaving users with only a transient UI error.

- [x] **Step 4: Document failure evidence in readiness guidance**

Update the readiness report so browser policy failures, autoplay blocking, and other target-browser export failures can be captured as migration evidence.

- [x] **Step 5: Verify affected behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts src/components/RaceOverlay.test.tsx src/publicApi.test.ts src/portabilityReadinessReport.test.ts`

Expected: failure serializer, public API export, React failure evidence UI, and readiness contract tests pass.

### Task 34: Target Browser Evidence Fixtures

**Files:**
- Create: `docs/superpowers/reports/evidence/2026-06-19-rac-6-iab-720p-success.json`
- Create: `docs/superpowers/reports/evidence/2026-06-19-rac-6-iab-1080p-success.json`
- Create: `web/src/portabilityMeasurementEvidence.test.ts`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Collect target-browser evidence**

Use the demo in the in-app browser with `Load sample measurement inputs`, then attempt 1280x720 and 1920x1080 5-second exports. Capture the measurement evidence JSON emitted by the page.

- [x] **Step 2: Store evidence fixtures**

Commit the two schema-valid success evidence files under `docs/superpowers/reports/evidence/` so the current target-browser result is reviewable instead of anecdotal.

- [x] **Step 3: Add evidence schema coverage**

Add a Vitest test that reads both evidence files and proves they cover 1280x720 and 1920x1080 with the expected sample TCX/video names.

- [x] **Step 4: Update readiness status**

Document that the target-browser evidence matrix now exists and records completed 5-second exports, while noting that the current in-app browser runs used muted playback fallback and do not prove audio retention.

- [x] **Step 5: Verify evidence coverage**

Run: `cd web && npm test -- --run src/portabilityMeasurementEvidence.test.ts src/portabilityReadinessReport.test.ts`

Expected: target-browser evidence files and readiness report references are schema-valid and covered by tests.

### Task 35: Export User-Activation Playback Priming

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add runtime coverage for caller-owned playback**

Add a test proving the browser export runtime can consume a caller-provided `video.play()` promise without calling `play()` a second time.

- [x] **Step 2: Add component coverage for click-handler playback priming**

Add a React test proving the export button starts source playback inside the click handler before constructing `MediaRecorder`.

- [x] **Step 3: Thread the play promise into the runtime**

Expose `playPromise` on `StartBrowserWebmExportOptions` and have the runtime await that promise for playback failure handling.

- [x] **Step 4: Prime playback from the export click handler**

Update `RaceOverlay` so `handleExportWebm()` resets the video, calls `video.play()`, and passes that promise into `startBrowserWebmExport()`.

- [x] **Step 5: Verify affected behavior**

Run: `cd web && npm test -- --run src/components/RaceOverlay.test.tsx` and `cd web && npm test -- --run src/runtime/browserExport.test.ts`

Expected: component and runtime export playback tests pass.

### Task 36: Muted Playback Export Fallback

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/index.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add runtime fallback coverage**

Add tests proving that a browser policy rejection from the first `video.play()` attempt retries with muted playback and reports `playbackMode: "muted-fallback"`.

- [x] **Step 2: Preserve hard failure behavior**

Add coverage proving export promises still reject when the muted playback retry also fails.

- [x] **Step 3: Start recording only after playback is available**

Update `startBrowserWebmExport()` so `MediaRecorder.start()` and frame rendering happen after playback succeeds or muted fallback succeeds.

- [x] **Step 4: Expose playback mode in measurement reports**

Add `BrowserWebmExportPlaybackMode` and `playbackMode` to browser export reports so migration evidence distinguishes normal playback from muted fallback.

- [x] **Step 5: Verify affected behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts` and `cd web && npm test -- --run src/components/RaceOverlay.test.tsx`

Expected: runtime fallback behavior and React measurement evidence tests pass.

### Task 37: Optional Audio Sample Generation Harness

**Files:**
- Modify: `web/src/demo/sampleInputs.ts`
- Modify: `web/src/demo/sampleInputs.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add opt-in sample audio generation**

Add `includeAudio` to `SyntheticMeasurementVideoOptions` so host/demo tests can request a generated Web Audio track when measuring audio retention.

- [x] **Step 2: Keep the default demo sample playable**

Leave the default sample video as video-only because the in-app browser did not play the generated Web Audio WebM sample reliably.

- [x] **Step 3: Cover sample audio stream mixing**

Add tests proving `includeAudio: true` mixes a generated audio track into the `MediaRecorder` stream and requests a VP9/Opus WebM MIME type.

- [x] **Step 4: Re-verify default target-browser export**

Re-run the default in-app browser 1280x720 sample export and confirm it still produces a successful measurement report with `audioTrackCount: 0`.

- [x] **Step 5: Document the audio evidence boundary**

Update readiness guidance so audio-retention parity requires a real playable source video with audio or a target-browser-compatible generated audio fixture.

### Task 38: Browser Export Cancellation And Retry

**Files:**
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add cancellation/retry coverage**

Add a component test proving an in-progress export shows `Cancel export`, canceling suppresses download/report callbacks from that run, and the same UI can retry successfully.

- [x] **Step 2: Track the active export run**

Store the current browser export run in a ref with a monotonic id and canceled flag so stale promise callbacks cannot update the UI.

- [x] **Step 3: Add a cancel action to the UI**

Show `Cancel export` while exporting, call the active run's `stop()`, clear measurement/failure evidence for the canceled run, and leave the export button available for retry.

- [x] **Step 4: Preserve completion callback ordering**

Avoid clearing the active export ref in the report callback before the blob completion callback has a chance to download and notify the host.

- [x] **Step 5: Verify affected behavior**

Run: `cd web && npm test -- --run src/components/RaceOverlay.test.tsx`

Expected: cancellation/retry behavior and existing export completion/report tests pass.

### Task 39: Browser Export Capability Probe

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/index.ts`
- Modify: `web/src/publicApi.test.ts`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add runtime capability coverage**

Add a test proving the export runtime reports WebM support, supported MIME type, canvas capture support, video capture support, source audio track count, and browser memory measurement availability.

- [x] **Step 2: Expose the capability probe as public API**

Export `readBrowserWebmExportCapabilities` and `BrowserWebmExportCapabilities` from the package entrypoint so host applications can record target-browser migration evidence without rendering the demo UI.

- [x] **Step 3: Show capability evidence in the demo UI**

Display a `Browser export capabilities` status line and refresh it after video metadata loads so target-browser runs can distinguish generic WebM support from source-video capture and audio-track retention.

- [x] **Step 4: Document the migration use**

Update readiness guidance so target-browser validation captures both the capability probe and the 5 seconds export measurement reports.

- [x] **Step 5: Verify affected behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts src/publicApi.test.ts src/components/RaceOverlay.test.tsx`

Expected: capability probe runtime, public API, and React UI tests pass.

### Task 40: Browser Export Capability Evidence Artifact

**Files:**
- Modify: `web/src/runtime/browserExport.ts`
- Modify: `web/src/runtime/browserExport.test.ts`
- Modify: `web/src/components/RaceOverlay.tsx`
- Modify: `web/src/components/RaceOverlay.test.tsx`
- Modify: `web/src/index.ts`
- Modify: `web/src/publicApi.test.ts`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add capability evidence serialization coverage**

Add a runtime test proving browser export capabilities serialize to schema-valid JSON with `schemaVersion: 1`, `status: capabilities`, optional context, and the probed capability fields.

- [x] **Step 2: Expose capability evidence serialization**

Export `serializeBrowserWebmExportCapabilities` and its evidence types from the package entrypoint so host applications can archive target-browser capability evidence without the demo UI.

- [x] **Step 3: Add a demo download path**

Show the capability evidence JSON in the demo UI and add `Download capability JSON` so target-browser validation can save the probe alongside 720p and 1080p measurement reports.

- [x] **Step 4: Document the evidence workflow**

Update readiness guidance so cross-browser validation records capability evidence before measurement exports, including Safari, Firefox, Chromium, and production-device comparisons.

- [x] **Step 5: Verify affected behavior**

Run: `cd web && npm test -- --run src/runtime/browserExport.test.ts src/publicApi.test.ts src/components/RaceOverlay.test.tsx`

Expected: runtime serialization, public exports, and React evidence UI tests pass.

### Task 41: Browser Portability Evidence Evaluator

**Files:**
- Create: `web/src/runtime/portabilityEvidence.ts`
- Create: `web/src/runtime/portabilityEvidence.test.ts`
- Modify: `web/src/portabilityMeasurementEvidence.test.ts`
- Modify: `web/src/index.ts`
- Modify: `web/src/publicApi.test.ts`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add evaluator coverage**

Add tests proving capability evidence plus successful 1280x720 and 1920x1080 5-second reports produce a `go` result, while missing or failed required exports produce `no-go` blockers.

- [x] **Step 2: Preserve audio parity as a stricter claim**

Add coverage proving `requireAudioRetention: true` turns `audioTrackCount: 0` and missing source-audio capability into blockers, while the default controlled migration evaluation can still pass video-overlay evidence.

- [x] **Step 3: Implement the pure runtime evaluator**

Implement `evaluateBrowserPortabilityEvidence()` without DOM, Python, file-system, or backend dependencies. Return `ready`, `status`, `blockers`, `warnings`, and `coveredExports`.

- [x] **Step 4: Publicly export the evaluator**

Expose the evaluator and its input/result types from `web/src/index.ts`.

- [x] **Step 5: Document the evidence gate**

Update readiness guidance so host apps and CI can evaluate capability plus measurement artifacts, and so audio-retention parity remains a separate No-Go gate until proven.

- [x] **Step 6: Verify affected behavior**

Run: `cd web && npm test -- --run src/runtime/portabilityEvidence.test.ts src/portabilityMeasurementEvidence.test.ts src/publicApi.test.ts`

Expected: evaluator behavior, current evidence classification, and public exports pass.

### Task 42: Browser Evidence Evaluation CLI

**Files:**
- Create: `web/scripts/evaluate-portability-evidence.mjs`
- Create: `web/src/test/fixtures/iab-capabilities.json`
- Modify: `web/package.json`
- Modify: `web/src/packageManifest.test.ts`
- Modify: `web/src/packageBuildArtifacts.test.ts`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add package manifest coverage**

Require an `evaluate:evidence` npm script, a package `bin` entry, and inclusion of the CLI file in package files.

- [x] **Step 2: Add the build-output CLI wrapper**

Implement `scripts/evaluate-portability-evidence.mjs` so it reads capability and measurement JSON files, imports `evaluateBrowserPortabilityEvidence()` from `dist/lib/race-overlay-web.js`, prints JSON or human-readable output, and exits non-zero for No-Go evidence.

- [x] **Step 3: Add a stable capability fixture for CLI verification**

Add a synthetic in-app browser capability fixture under `web/src/test/fixtures/` for command-level checks against the existing 720p and 1080p evidence artifacts.

- [x] **Step 4: Verify Go and audio-parity No-Go commands**

Run the CLI after `npm run build` and prove the current evidence returns `go` by default but returns `no-go` with `--require-audio-retention`.

- [x] **Step 5: Document the CI gate**

Update readiness guidance with `npm run evaluate:evidence` examples for controlled migration and audio-retention parity gates.

### Task 43: Browser Evidence Matrix Manifest

**Files:**
- Modify: `web/src/runtime/portabilityEvidence.ts`
- Modify: `web/src/runtime/portabilityEvidence.test.ts`
- Modify: `web/src/index.ts`
- Modify: `web/src/publicApi.test.ts`
- Modify: `web/scripts/evaluate-portability-evidence.mjs`
- Modify: `web/src/packageBuildArtifacts.test.ts`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Create: `web/src/test/fixtures/evidence-matrix.json`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add multi-target evaluator coverage**

Add runtime tests proving a matrix with one passing target and one missing target produces an overall No-Go with target-prefixed blockers.

- [x] **Step 2: Implement `evaluateBrowserPortabilityEvidenceMatrix()`**

Aggregate per-target evidence results, preserve each target's individual result, and expose matrix-level `ready`, `status`, `blockers`, and `warnings`.

- [x] **Step 3: Add manifest mode to the CLI**

Support `npm run evaluate:evidence -- --manifest evidence-matrix.json`, resolving target artifact paths relative to the manifest file.

- [x] **Step 4: Add a matrix fixture**

Create a fixture with current in-app browser evidence plus a missing Safari target so command-level verification proves the matrix gate identifies missing target evidence.

- [x] **Step 5: Document the final target-browser matrix workflow**

Update readiness guidance so Safari, Firefox, Chromium, and production-device validation can be evaluated in one manifest-driven CI gate.

### Task 44: Required Target Matrix Gate

**Files:**
- Modify: `web/src/runtime/portabilityEvidence.ts`
- Modify: `web/src/runtime/portabilityEvidence.test.ts`
- Modify: `web/scripts/evaluate-portability-evidence.mjs`
- Modify: `web/src/test/fixtures/evidence-matrix.json`
- Modify: `web/src/packageBuildArtifacts.test.ts`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add missing target coverage**

Add a runtime test proving `requiredTargets` makes omitted target names fail the matrix gate.

- [x] **Step 2: Implement required target blockers**

Teach `evaluateBrowserPortabilityEvidenceMatrix()` to emit `<target>: Missing target evidence entry` for required target names that are absent from the manifest inputs.

- [x] **Step 3: Read required targets from manifest CLI**

Pass manifest `requiredTargets` through `npm run evaluate:evidence -- --manifest ...` so CI catches missing Safari, Firefox, Chromium, or production-device entries.

- [x] **Step 4: Strengthen the example fixture**

Add `requiredTargets` to `web/src/test/fixtures/evidence-matrix.json` so the sample gate demonstrates both omitted target blockers and incomplete target blockers.

- [x] **Step 5: Document the release matrix invariant**

Update readiness guidance so final migration manifests must declare every release target instead of relying on whatever entries happen to be present.

### Task 45: Required Export Matrix Gate

**Files:**
- Modify: `web/src/runtime/portabilityEvidence.test.ts`
- Modify: `web/scripts/evaluate-portability-evidence.mjs`
- Modify: `web/src/test/fixtures/evidence-matrix.json`
- Modify: `web/src/packageBuildArtifacts.test.ts`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add matrix required-export coverage**

Add a runtime test proving matrix-level `requiredExports` apply to every target and missing long-duration evidence becomes a target-prefixed blocker.

- [x] **Step 2: Read required exports from manifest CLI**

Pass manifest `requiredExports` through `npm run evaluate:evidence -- --manifest ...` so release gates can require long-duration, large-file, or additional-resolution evidence without code changes.

- [x] **Step 3: Strengthen the sample matrix fixture**

Add a 1920x1080 60-second required export to `web/src/test/fixtures/evidence-matrix.json` so the sample manifest demonstrates missing long-duration evidence.

- [x] **Step 4: Document long-duration evidence gates**

Update readiness guidance so production long-duration or large-file gates are expressed as manifest `requiredExports`.

### Task 46: Manifest Validation For Evidence CLI

**Files:**
- Create: `web/src/evaluateEvidenceCli.test.ts`
- Create: `web/src/test/fixtures/invalid-evidence-matrix.json`
- Modify: `web/scripts/evaluate-portability-evidence.mjs`
- Modify: `web/src/portabilityReadinessReport.test.ts`
- Modify: `docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md`
- Modify: `docs/superpowers/plans/2026-06-10-webassembly-react-spike.md`

- [x] **Step 1: Add CLI validation coverage**

Add a command-level test proving malformed manifest input exits with code 2 and reports a specific `Manifest ...` validation error before evaluation.

- [x] **Step 2: Validate manifest structure**

Validate manifest object shape, `requiredTargets`, `requiredExports`, target names, capability paths, measurement paths, and per-target audio-retention flags before reading referenced artifacts.

- [x] **Step 3: Separate configuration errors from evidence No-Go**

Keep malformed manifest errors as exit code 2, while well-formed but incomplete evidence remains exit code 1.

- [x] **Step 4: Document validation behavior**

Update readiness guidance so CI operators can distinguish bad gate configuration from failed portability evidence.
