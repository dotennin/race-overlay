import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("package README", () => {
  it("documents the portable host integration and evidence gate", () => {
    const readme = readFileSync(resolve(__dirname, "../README.md"), "utf8");

    expect(readme).toContain("TCX-based");
    expect(readme).toContain('from "race-overlay-web"');
    expect(readme).not.toContain("race-overlay-web-spike");
    expect(readme).toContain("Host applications provide React and ReactDOM");
    expect(readme).toContain("peer dependencies");
    expect(readme).toContain("runtime dependency list is intentionally empty");
    expect(readme).toContain("CSS is declared as a package side effect");
    expect(readme).toContain("does not require a Python backend runtime");
    expect(readme).toContain("does not read a backend video path");
    expect(readme).toContain("does not include FIT support");
    expect(readme).toContain("activityFile={activityFile}");
    expect(readme).toContain("videoFile={videoFile}");
    expect(readme).toContain("examples/host-integration.tsx");
    expect(readme).toContain("npm run check:examples");
    expect(readme).toContain("npm run verify:consumer");
    expect(readme).toContain("packed tarball consumer smoke");
    expect(readme).toContain("createExternalVideoMetadataProvider");
    expect(readme).toContain("partial file first");
    expect(readme).toContain("needsFullUpload: true");
    expect(readme).toContain("readBrowserWebmExportCapabilities");
    expect(readme).toContain("serializeBrowserWebmExportCapabilities");
    expect(readme).toContain("npm run scaffold:evidence");
    expect(readme).toContain("npm run evaluate:evidence");
    expect(readme).toContain("npm run verify:portability");
    expect(readme).toContain("release-evidence/evidence-matrix.json");
    expect(readme).toContain("current package gate");
    expect(readme).toContain("examples/evidence-matrix.template.json");
    expect(readme).toContain("--require-audio-retention");
    expect(readme).toContain("audioTrackCount: 0");
    expect(readme).toContain("MediaRecorder");
  });
});
