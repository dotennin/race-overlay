import { describe, expect, it } from "vitest";

import {
  RaceOverlay,
  broadcastRunnerPreset,
  createExternalVideoMetadataProvider,
  evaluateBrowserPortabilityEvidence,
  evaluateBrowserPortabilityEvidenceMatrix,
  readBrowserWebmExportCapabilities,
  serializeBrowserWebmExportCapabilities,
  readTcx,
  sampleAt,
  serializeBrowserWebmExportFailure,
  serializeBrowserWebmExportReport,
  startBrowserWebmExport,
  supportedWebmMimeType,
} from "./index";

describe("public React/runtime API", () => {
  it("exports the portable React component and browser runtime helpers", () => {
    expect(RaceOverlay).toBeTypeOf("function");
    expect(broadcastRunnerPreset().preset).toBe("broadcast-runner");
    expect(readTcx).toBeTypeOf("function");
    expect(sampleAt).toBeTypeOf("function");
    expect(startBrowserWebmExport).toBeTypeOf("function");
    expect(readBrowserWebmExportCapabilities).toBeTypeOf("function");
    expect(serializeBrowserWebmExportCapabilities).toBeTypeOf("function");
    expect(serializeBrowserWebmExportReport).toBeTypeOf("function");
    expect(serializeBrowserWebmExportFailure).toBeTypeOf("function");
    expect(supportedWebmMimeType()).toBe("video/webm;codecs=vp9,opus");
    expect(createExternalVideoMetadataProvider).toBeTypeOf("function");
    expect(evaluateBrowserPortabilityEvidence).toBeTypeOf("function");
    expect(evaluateBrowserPortabilityEvidenceMatrix).toBeTypeOf("function");
  });
});
