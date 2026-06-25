import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

const scriptPath = resolve(__dirname, "../scripts/scaffold-portability-evidence.mjs");

function runScaffold(args: string[], cwd: string) {
  return execFileSync(process.execPath, [scriptPath, ...args], {
    cwd,
    encoding: "utf8",
  });
}

function tempDir() {
  return mkdtempSync(join(tmpdir(), "race-overlay-evidence-"));
}

describe("portability evidence scaffold", () => {
  it("creates a release evidence matrix with required browser targets and long export coverage", () => {
    const cwd = tempDir();

    const output = runScaffold(["--out", "release-evidence"], cwd);
    const manifest = JSON.parse(readFileSync(join(cwd, "release-evidence/evidence-matrix.json"), "utf8"));
    const readme = readFileSync(join(cwd, "release-evidence/README.md"), "utf8");

    expect(output).toContain("Created portability evidence scaffold");
    expect(manifest.requiredTargets).toEqual(["chromium", "firefox", "safari", "production-device"]);
    expect(manifest.requiredExports).toEqual([
      { width: 1280, height: 720, durationSeconds: 5 },
      { width: 1920, height: 1080, durationSeconds: 5 },
      { width: 1920, height: 1080, durationSeconds: 60 },
    ]);
    expect(manifest.targets[0]).toEqual({
      name: "chromium",
      capabilities: "./chromium/capabilities.json",
      measurements: [
        "./chromium/1280x720-5s-measurement.json",
        "./chromium/1920x1080-5s-measurement.json",
        "./chromium/1920x1080-60s-measurement.json",
      ],
    });
    expect(readme).toContain("Upload a TCX file and a source video file");
    expect(readme).toContain("npm run evaluate:evidence -- --manifest release-evidence/evidence-matrix.json");
  });

  it("supports custom target lists and an audio-retention parity gate", () => {
    const cwd = tempDir();

    runScaffold(
      ["--out", "release-evidence", "--target", "edge", "--target", "ios-safari", "--require-audio-retention"],
      cwd,
    );
    const manifest = JSON.parse(readFileSync(join(cwd, "release-evidence/evidence-matrix.json"), "utf8"));
    const readme = readFileSync(join(cwd, "release-evidence/README.md"), "utf8");

    expect(manifest.requiredTargets).toEqual(["edge", "ios-safari"]);
    expect(manifest.requireAudioRetention).toBe(true);
    expect(manifest.targets).toHaveLength(2);
    expect(readme).toContain("--require-audio-retention");
  });

  it("does not overwrite existing scaffold files unless forced", () => {
    const cwd = tempDir();
    runScaffold(["--out", "release-evidence"], cwd);
    writeFileSync(join(cwd, "release-evidence/README.md"), "keep me");

    const duplicate = spawnSync(process.execPath, [scriptPath, "--out", "release-evidence"], {
      cwd,
      encoding: "utf8",
    });

    expect(duplicate.status).toBe(2);
    expect(duplicate.stderr).toContain("already exists");

    runScaffold(["--out", "release-evidence", "--force"], cwd);
    expect(readFileSync(join(cwd, "release-evidence/README.md"), "utf8")).toContain(
      "Race Overlay Web Release Evidence",
    );
  });
});
