import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("evidence evaluation CLI", () => {
  it("reports manifest validation errors before evaluation", () => {
    const root = resolve(__dirname, "..");
    const result = spawnSync(
      process.execPath,
      ["scripts/evaluate-portability-evidence.mjs", "--manifest", "src/test/fixtures/invalid-evidence-matrix.json", "--json"],
      {
        cwd: root,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(2);
    expect(result.stderr).toContain("Manifest requiredTargets[1] must be a non-empty string");
    expect(result.stderr).toContain("Usage:");
  });

  it("reports invalid capability evidence as an input error", () => {
    const root = resolve(__dirname, "..");
    const result = spawnSync(
      process.execPath,
      [
        "scripts/evaluate-portability-evidence.mjs",
        "--capabilities",
        "src/test/fixtures/invalid-capabilities.json",
        "--measurement",
        "../docs/superpowers/reports/evidence/2026-06-19-rac-6-iab-720p-success.json",
        "--json",
      ],
      {
        cwd: root,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(2);
    expect(result.stderr).toContain(
      "Capability evidence src/test/fixtures/invalid-capabilities.json.capabilities.sourceAudioTrackCount must be a non-negative integer",
    );
  });

  it("reports invalid measurement evidence referenced from a manifest", () => {
    const root = resolve(__dirname, "..");
    const result = spawnSync(
      process.execPath,
      [
        "scripts/evaluate-portability-evidence.mjs",
        "--manifest",
        "src/test/fixtures/invalid-evidence-file-matrix.json",
        "--json",
      ],
      {
        cwd: root,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(2);
    expect(result.stderr).toContain(
      'Measurement evidence invalid-measurement.json.report.playbackMode must be "normal" or "muted-fallback"',
    );
  });

  it("treats missing manifest artifacts as incomplete evidence instead of malformed configuration", () => {
    const root = resolve(__dirname, "..");
    const evidenceDir = mkdtempSync(join(tmpdir(), "race-overlay-missing-evidence-"));
    const manifestPath = join(evidenceDir, "evidence-matrix.json");
    writeFileSync(
      manifestPath,
      JSON.stringify(
        {
          schemaVersion: 1,
          requiredTargets: ["chromium"],
          targets: [
            {
              name: "chromium",
              capabilities: "./chromium/capabilities.json",
              measurements: ["./chromium/1280x720-5s-measurement.json"],
            },
          ],
        },
        null,
        2,
      ),
    );

    const result = spawnSync(
      process.execPath,
      ["scripts/evaluate-portability-evidence.mjs", "--manifest", manifestPath, "--json"],
      {
        cwd: root,
        encoding: "utf8",
      },
    );

    expect(result.status).toBe(1);
    expect(result.stdout).toContain('"status": "no-go"');
    expect(result.stdout).toContain("chromium: Missing browser export capability evidence");
    expect(result.stdout).toContain("chromium: Missing successful 1280x720 5s export evidence");
  });
});
