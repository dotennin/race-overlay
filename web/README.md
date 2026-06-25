# Race Overlay Web

Portable React/browser package for TCX-based race video overlays.

This package is the web migration boundary for RAC-6. It does not require a Python backend runtime, does not read a backend video path, and does not include FIT support. Host applications provide browser `File` objects for the TCX activity and source video.

## Install Surface

Import the component, styles, and optional helpers from the package entrypoint:

Host applications provide React and ReactDOM as peer dependencies. Build and test tools such as Vite, Vitest, TypeScript, and jsdom are development-only dependencies of this package and are not part of the runtime integration surface. The runtime dependency list is intentionally empty. CSS is declared as a package side effect so host bundlers do not tree-shake away `race-overlay-web/styles.css`.

```tsx
import {
  RaceOverlay,
  createExternalVideoMetadataProvider,
  evaluateBrowserPortabilityEvidence,
  readBrowserWebmExportCapabilities,
  serializeBrowserWebmExportCapabilities,
} from "race-overlay-web";
import "race-overlay-web/styles.css";
```

## Host Integration

Use existing file inputs or drag-and-drop flows. The component accepts the same `File` objects a browser receives from an `<input type="file">`.

See `examples/host-integration.tsx` for a typechecked host wrapper that imports from `race-overlay-web`, wires TCX/video file inputs, injects the caller-owned metadata API, and serializes browser export evidence. `npm run check:examples` typechecks this external-import example after the library declarations are built.

```tsx
import { useMemo, useState } from "react";
import { RaceOverlay, createExternalVideoMetadataProvider } from "race-overlay-web";
import "race-overlay-web/styles.css";

export function OverlayEditor() {
  const [activityFile, setActivityFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const metadataProvider = useMemo(
    () =>
      createExternalVideoMetadataProvider({
        endpoint: "https://metadata.example.com/video",
        initialBytes: 16 * 1024 * 1024,
      }),
    [],
  );

  return (
    <>
      <input
        type="file"
        accept=".tcx,application/xml,text/xml"
        onChange={(event) => setActivityFile(event.currentTarget.files?.[0] ?? null)}
      />
      <input
        type="file"
        accept="video/*"
        onChange={(event) => setVideoFile(event.currentTarget.files?.[0] ?? null)}
      />
      <RaceOverlay
        activityFile={activityFile}
        videoFile={videoFile}
        externalVideoMetadataProvider={metadataProvider}
        exportWidth={1920}
        exportHeight={1080}
        exportDurationSeconds={5}
        onExportReport={(report) => console.log("export evidence", report)}
        onExportComplete={(blob) => console.log("webm export", blob)}
      />
    </>
  );
}
```

## Video Creation Time

`RaceOverlay` first tries `readBrowserVideoMetadata()` against the local browser `File`. This reads a bounded head slice, so common MP4/MOV creation time metadata can be used without uploading the full source video.

If local parsing cannot find metadata, inject `createExternalVideoMetadataProvider()`. The provider uploads a partial file first and only uploads the complete file when the external API explicitly returns `needsFullUpload: true`.

The external API is caller-owned. The package does not provide or call a Python API, a Vite proxy, or a backend video path.

Expected API contract:

- request method: `POST`
- form field `video`: partial or full video file
- form field `mode`: `partial` or `full`
- form field `filename`: original filename
- form field `size`: original file size in bytes
- form field `contentType`: original content type
- JSON response: `{ "metadata": VideoMetadata | null, "needsFullUpload"?: boolean, "reason"?: string | null }`

## Evidence Collection

Before claiming a browser target is portable, collect:

- one capability artifact from `readBrowserWebmExportCapabilities(video)` and `serializeBrowserWebmExportCapabilities()`
- one 1280x720 5 second measurement artifact
- one 1920x1080 5 second measurement artifact
- any extra release-required duration or resolution artifacts

The demo UI can download capability, measurement, and failure JSON artifacts. Host applications can generate the same JSON with:

- `serializeBrowserWebmExportCapabilities()`
- `serializeBrowserWebmExportReport()`
- `serializeBrowserWebmExportFailure()`

Evaluate a single target:

```bash
npm run build
npm run evaluate:evidence -- \
  --capabilities path/to/capabilities.json \
  --measurement path/to/720p-measurement.json \
  --measurement path/to/1080p-measurement.json
```

Create a release evidence workspace:

```bash
npm run scaffold:evidence -- --out release-evidence
```

This creates `release-evidence/evidence-matrix.json` plus one folder per required target. The default scaffold covers Chromium, Firefox, Safari, the production device/browser combination, 720p, 1080p, and a 1080p 60 second export. Use `--target <name>` to override the target list and `--require-audio-retention` when the release claim includes audio-retaining parity.

Evaluate a target matrix after filling the generated artifact paths:

```bash
npm run evaluate:evidence -- --manifest release-evidence/evidence-matrix.json
```

Use `--require-audio-retention` only when the release claim includes audio-retaining export parity. Evidence with `audioTrackCount: 0` is valid controlled video-overlay evidence, but not audio-retention parity.

## Final Migration Gate

Use `npm run scaffold:evidence -- --out release-evidence` or `examples/evidence-matrix.template.json` as the release gate shape. A complete migration should replace every placeholder path with real artifacts for the target browsers and production device/browser combination.

Run the current package gate before handing the package to a host application:

```bash
npm run verify:portability
```

This command runs the web tests, production build, host integration example typecheck, packed tarball consumer smoke, package dry-run, current in-app-browser evidence check, and release matrix check. The release matrix is expected to remain No-Go until Chromium, Firefox, Safari, production-device, and long-duration evidence are collected; the script fails only if the current package gate regresses or the matrix stops reporting those missing requirements.

Run `npm run verify:consumer` when you only need to verify the packed package surface. It creates a real `npm pack` tarball, installs it into a temporary consumer-style `node_modules`, checks ESM import, CJS require, CSS export resolution, packaged examples, and packaged evidence scripts, then removes the temporary artifacts.

The CLI uses distinct exit codes:

- `0`: evidence is complete for the requested gate
- `1`: evidence is well-formed but incomplete or No-Go, including referenced artifacts that have not been collected yet
- `2`: manifest or existing referenced evidence JSON is malformed

## Browser Export Boundary

The current portable export path is canvas composition plus `MediaRecorder` WebM. It is suitable for collecting target-browser evidence and controlled web migration. It is not a claim of parity with native `ffmpeg`/`ffprobe`, and it is not a long-video batch export engine.
