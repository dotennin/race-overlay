import { describe, expect, it } from "vitest";

import type { BrowserWebmExportCapabilitiesEvidence, BrowserWebmExportReportEvidence } from "./browserExport";
import { evaluateBrowserPortabilityEvidence, evaluateBrowserPortabilityEvidenceMatrix } from "./portabilityEvidence";

const capableEvidence: BrowserWebmExportCapabilitiesEvidence = {
  schemaVersion: 1,
  generatedAt: "2026-06-19T00:00:00.000Z",
  status: "capabilities",
  browserName: "chromium",
  videoName: "source.mp4",
  capabilities: {
    canExportWebm: true,
    supportedMimeType: "video/webm;codecs=vp9,opus",
    supportsCanvasCapture: true,
    supportsVideoCaptureStream: true,
    sourceAudioTrackCount: 1,
    supportsMemoryMeasurement: true,
  },
};

function measurement(width: number, height: number, audioTrackCount = 1): BrowserWebmExportReportEvidence {
  return {
    schemaVersion: 1,
    generatedAt: "2026-06-19T00:00:00.000Z",
    activityName: "sample.tcx",
    videoName: "source.mp4",
    report: {
      width,
      height,
      fps: 30,
      bitrateMbps: 6,
      mimeType: "video/webm;codecs=vp9,opus",
      elapsedMs: 5000,
      outputBytes: 123456,
      durationSeconds: 5,
      audioTrackCount,
      memoryUsedBytes: 1000000,
      playbackMode: "normal",
    },
  };
}

describe("browser portability evidence evaluator", () => {
  it("accepts capability evidence plus successful 720p and 1080p measurement evidence", () => {
    const result = evaluateBrowserPortabilityEvidence({
      capabilities: capableEvidence,
      measurements: [measurement(1280, 720), measurement(1920, 1080)],
    });

    expect(result.ready).toBe(true);
    expect(result.status).toBe("go");
    expect(result.coveredExports).toEqual([
      { width: 1280, height: 720, durationSeconds: 5 },
      { width: 1920, height: 1080, durationSeconds: 5 },
    ]);
    expect(result.blockers).toEqual([]);
  });

  it("blocks migration when required dimensions are missing or failed", () => {
    const result = evaluateBrowserPortabilityEvidence({
      capabilities: capableEvidence,
      measurements: [
        measurement(1280, 720),
        {
          schemaVersion: 1,
          generatedAt: "2026-06-19T00:00:00.000Z",
          status: "failed",
          error: "recording failed",
          attemptedExport: {
            width: 1920,
            height: 1080,
            fps: 30,
            bitrateMbps: 6,
            durationSeconds: 5,
          },
        },
      ],
    });

    expect(result.ready).toBe(false);
    expect(result.status).toBe("no-go");
    expect(result.blockers).toContain("Missing successful 1920x1080 5s export evidence");
    expect(result.blockers).toContain("Failed 1920x1080 5s export evidence: recording failed");
  });

  it("can require audio-retaining evidence for parity claims", () => {
    const result = evaluateBrowserPortabilityEvidence({
      capabilities: capableEvidence,
      measurements: [measurement(1280, 720, 0), measurement(1920, 1080, 0)],
      requireAudioRetention: true,
    });

    expect(result.ready).toBe(false);
    expect(result.status).toBe("no-go");
    expect(result.blockers).toContain("Audio retention required but 1280x720 evidence has 0 audio tracks");
    expect(result.blockers).toContain("Audio retention required but 1920x1080 evidence has 0 audio tracks");
  });

  it("warns when playback needed muted fallback but does not block controlled migration", () => {
    const muted720 = measurement(1280, 720);
    muted720.report.playbackMode = "muted-fallback";
    const result = evaluateBrowserPortabilityEvidence({
      capabilities: capableEvidence,
      measurements: [muted720, measurement(1920, 1080)],
    });

    expect(result.ready).toBe(true);
    expect(result.status).toBe("go");
    expect(result.warnings).toContain("1280x720 export used muted playback fallback");
  });

  it("evaluates a multi-target browser evidence matrix", () => {
    const result = evaluateBrowserPortabilityEvidenceMatrix({
      targets: [
        {
          name: "chromium",
          capabilities: capableEvidence,
          measurements: [measurement(1280, 720), measurement(1920, 1080)],
        },
        {
          name: "safari",
          capabilities: null,
          measurements: [],
        },
      ],
    });

    expect(result.ready).toBe(false);
    expect(result.status).toBe("no-go");
    expect(result.targets).toHaveLength(2);
    expect(result.targets[0]).toMatchObject({ name: "chromium", ready: true, status: "go" });
    expect(result.targets[1]).toMatchObject({ name: "safari", ready: false, status: "no-go" });
    expect(result.blockers).toContain("safari: Missing browser export capability evidence");
    expect(result.blockers).toContain("safari: Missing successful 1280x720 5s export evidence");
    expect(result.blockers).toContain("safari: Missing successful 1920x1080 5s export evidence");
  });

  it("blocks a matrix that omits required target names", () => {
    const result = evaluateBrowserPortabilityEvidenceMatrix({
      requiredTargets: ["chromium", "firefox", "safari"],
      targets: [
        {
          name: "chromium",
          capabilities: capableEvidence,
          measurements: [measurement(1280, 720), measurement(1920, 1080)],
        },
      ],
    });

    expect(result.ready).toBe(false);
    expect(result.status).toBe("no-go");
    expect(result.blockers).toContain("firefox: Missing target evidence entry");
    expect(result.blockers).toContain("safari: Missing target evidence entry");
  });

  it("applies matrix-level required export specifications to every target", () => {
    const result = evaluateBrowserPortabilityEvidenceMatrix({
      requiredExports: [
        { width: 1280, height: 720, durationSeconds: 5 },
        { width: 1920, height: 1080, durationSeconds: 60 },
      ],
      targets: [
        {
          name: "chromium",
          capabilities: capableEvidence,
          measurements: [measurement(1280, 720), measurement(1920, 1080)],
        },
      ],
    });

    expect(result.ready).toBe(false);
    expect(result.status).toBe("no-go");
    expect(result.blockers).toContain("chromium: Missing successful 1920x1080 60s export evidence");
  });
});
