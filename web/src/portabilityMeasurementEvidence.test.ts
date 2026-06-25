import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type {
  BrowserWebmExportCapabilitiesEvidence,
  BrowserWebmExportFailureEvidence,
  BrowserWebmExportReportEvidence,
} from "./runtime/browserExport";
import { evaluateBrowserPortabilityEvidence } from "./runtime/portabilityEvidence";

type MeasurementEvidence = BrowserWebmExportReportEvidence | BrowserWebmExportFailureEvidence;

const evidenceRoot = resolve(process.cwd(), "../docs/superpowers/reports/evidence");

function readEvidence(filename: string): MeasurementEvidence {
  return JSON.parse(readFileSync(resolve(evidenceRoot, filename), "utf8")) as MeasurementEvidence;
}

function measuredDimensions(evidence: MeasurementEvidence): { width: number; height: number } {
  if (evidence.status === "failed") {
    expect(evidence.attemptedExport).toBeDefined();
    return {
      width: evidence.attemptedExport!.width,
      height: evidence.attemptedExport!.height,
    };
  }
  expect(evidence.report).toBeDefined();
  return {
    width: evidence.report!.width,
    height: evidence.report!.height,
  };
}

function expectReportEvidence(evidence: MeasurementEvidence): BrowserWebmExportReportEvidence {
  if (evidence.status === "failed") {
    throw new Error(`Expected successful evidence, got failure: ${evidence.error}`);
  }
  return evidence;
}

describe("RAC-6 target browser measurement evidence", () => {
  it("records successful target-browser evidence for 720p and 1080p exports", () => {
    const evidence720 = readEvidence("2026-06-19-rac-6-iab-720p-success.json");
    const evidence1080 = readEvidence("2026-06-19-rac-6-iab-1080p-success.json");

    expect(evidence720.schemaVersion).toBe(1);
    expect(evidence1080.schemaVersion).toBe(1);
    const report720 = expectReportEvidence(evidence720);
    const report1080 = expectReportEvidence(evidence1080);
    expect(measuredDimensions(evidence720)).toEqual({ width: 1280, height: 720 });
    expect(measuredDimensions(evidence1080)).toEqual({ width: 1920, height: 1080 });
    expect(report720.report).toMatchObject({
      durationSeconds: 5,
      audioTrackCount: 0,
      playbackMode: "muted-fallback",
    });
    expect(report1080.report).toMatchObject({
      durationSeconds: 5,
      audioTrackCount: 0,
      playbackMode: "muted-fallback",
    });
    expect(report720.report.outputBytes).toBeGreaterThan(0);
    expect(report1080.report.outputBytes).toBeGreaterThan(0);
    expect(evidence720.generatedAt).toMatch(/^2026-06-19T/);
    expect(evidence1080.generatedAt).toMatch(/^2026-06-19T/);
    expect(evidence720.activityName).toBe("sample-measurement.tcx");
    expect(evidence1080.activityName).toBe("sample-measurement.tcx");
    expect(evidence720.videoName).toBe("sample-measurement.webm");
    expect(evidence1080.videoName).toBe("sample-measurement.webm");
  });

  it("classifies current in-app browser evidence as video-export ready but not audio-retention ready", () => {
    const capabilityEvidence: BrowserWebmExportCapabilitiesEvidence = {
      schemaVersion: 1,
      generatedAt: "2026-06-19T06:41:31.308Z",
      status: "capabilities",
      browserName: "in-app-browser",
      videoName: "sample-measurement.webm",
      capabilities: {
        canExportWebm: true,
        supportedMimeType: "video/webm;codecs=vp9,opus",
        supportsCanvasCapture: true,
        supportsVideoCaptureStream: true,
        sourceAudioTrackCount: 0,
        supportsMemoryMeasurement: true,
      },
    };
    const evidence720 = readEvidence("2026-06-19-rac-6-iab-720p-success.json");
    const evidence1080 = readEvidence("2026-06-19-rac-6-iab-1080p-success.json");

    expect(
      evaluateBrowserPortabilityEvidence({
        capabilities: capabilityEvidence,
        measurements: [evidence720, evidence1080],
      }),
    ).toMatchObject({
      ready: true,
      status: "go",
      warnings: ["1280x720 export used muted playback fallback", "1920x1080 export used muted playback fallback"],
    });

    expect(
      evaluateBrowserPortabilityEvidence({
        capabilities: capabilityEvidence,
        measurements: [evidence720, evidence1080],
        requireAudioRetention: true,
      }),
    ).toMatchObject({
      ready: false,
      status: "no-go",
    });
  });
});
