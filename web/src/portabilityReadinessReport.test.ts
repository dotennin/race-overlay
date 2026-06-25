import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const reportPath = resolve(
  process.cwd(),
  "../docs/superpowers/reports/2026-06-19-rac-6-portability-readiness.md",
);
const specPath = resolve(
  process.cwd(),
  "../docs/superpowers/specs/2026-06-10-webassembly-react-port-feasibility-design.md",
);

describe("RAC-6 portability readiness report", () => {
  it("documents the migration boundary, evidence, measurements, and risks", () => {
    const report = readFileSync(reportPath, "utf8");

    expect(report).toContain("TCX-only");
    expect(report).toContain("no Python backend runtime");
    expect(report).toContain("createExternalVideoMetadataProvider");
    expect(report).toContain("partial upload");
    expect(report).toContain("MediaRecorder");
    expect(report).toContain("examples/host-integration.tsx");
    expect(report).toContain("npm run check:examples");
    expect(report).toContain("npm run verify:consumer");
    expect(report).toContain("packed tarball consumer smoke");
    expect(report).toContain("readBrowserWebmExportCapabilities");
    expect(report).toContain("serializeBrowserWebmExportCapabilities");
    expect(report).toContain("evaluateBrowserPortabilityEvidence");
    expect(report).toContain("evaluateBrowserPortabilityEvidenceMatrix");
    expect(report).toContain("npm run scaffold:evidence");
    expect(report).toContain("npm run evaluate:evidence");
    expect(report).toContain("npm run verify:portability");
    expect(report).toContain("--manifest");
    expect(report).toContain("requiredTargets");
    expect(report).toContain("requiredExports");
    expect(report).toContain("long-duration");
    expect(report).toContain("Manifest validation");
    expect(report).toContain("Capability and measurement evidence files are also validated");
    expect(report).toContain("exit code 2");
    expect(report).toContain("--require-audio-retention");
    expect(report).toContain("Browser export capabilities");
    expect(report).toContain("Download capability JSON");
    expect(report).toContain("status: capabilities");
    expect(report).toContain("audio-retention parity");
    expect(report).toContain("canvas capture");
    expect(report).toContain("video capture");
    expect(report).toContain("exportWidth");
    expect(report).toContain("exportHeight");
    expect(report).toContain("onExportReport");
    expect(report).toContain("Load sample measurement inputs");
    expect(report).toContain("Download measurement JSON");
    expect(report).toContain("Download failure JSON");
    expect(report).toContain("Cancel export");
    expect(report).toContain("cancellation/retry");
    expect(report).toContain("schemaVersion");
    expect(report).toContain("status: failed");
    expect(report).toContain("activityFile");
    expect(report).toContain("videoFile");
    expect(report).toContain("1280x720");
    expect(report).toContain("1920x1080");
    expect(report).toContain("2026-06-19-rac-6-iab-720p-success.json");
    expect(report).toContain("2026-06-19-rac-6-iab-1080p-success.json");
    expect(report).toContain("user-activation playback priming");
    expect(report).toContain("export button click handler");
    expect(report).toContain("muted playback fallback");
    expect(report).toContain("playbackMode");
    expect(report).toContain("muted-fallback");
    expect(report).toContain("audioTrackCount: 0");
    expect(report).toContain("includeAudio");
    expect(report).toContain("audioTrackCount` greater than `0");
    expect(report).toContain("5 seconds");
    expect(report).toContain("Go");
    expect(report).toContain("No-Go");
    expect(report).toContain("in-app browser package evidence");
    expect(report).toContain("WebCodecs");
    expect(report).toContain("FFmpeg WASM");
    expect(report).toContain("npm test -- --run");
    expect(report).toContain("npm run build");
  });

  it("keeps the feasibility design aligned with the implemented export path", () => {
    const spec = readFileSync(specPath, "utf8");

    expect(spec).toContain("当前 Spike 实现选择 `MediaRecorder`");
    expect(spec).toContain("WebCodecs 和 FFmpeg WASM 保留为后续生产级评估路径");
    expect(spec).not.toContain("Export path 优先使用 WebCodecs");
  });
});
