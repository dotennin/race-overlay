export { RaceOverlay } from "./components/RaceOverlay";
export type { RaceOverlayProps } from "./components/RaceOverlay";
export {
  broadcastRunnerPreset,
  serializeHudConfig,
  type HudConfig,
  type HudStyleValue,
  type HudThemeConfig,
  type HudWidgetConfig,
  type SerializedHudConfig,
  type SerializedHudThemeConfig,
  type SerializedHudWidgetConfig,
} from "./runtime/hudConfig";
export type { ActivityLap, ActivitySample, ActivityTrack, HudSample } from "./runtime/models";
export { readTcx } from "./runtime/tcx";
export { sampleAt } from "./runtime/sampling";
export { alignClip } from "./runtime/alignment";
export {
  readBrowserWebmExportCapabilities,
  serializeBrowserWebmExportCapabilities,
  serializeBrowserWebmExportFailure,
  serializeBrowserWebmExportReport,
  startBrowserWebmExport,
  supportedWebmMimeType,
  type BrowserWebmExportCapabilities,
  type BrowserWebmExportCapabilitiesEvidence,
  type BrowserWebmExportCapabilitiesEvidenceContext,
  type BrowserWebmExportFailureEvidence,
  type BrowserWebmExportFailureEvidenceContext,
  type BrowserWebmExportPlaybackMode,
  type BrowserWebmExportReportEvidence,
  type BrowserWebmExportReportEvidenceContext,
  type BrowserWebmExportReport,
  type BrowserWebmExportProgress,
  type BrowserWebmExportRun,
  type CapturableVideoElement,
  type StartBrowserWebmExportOptions,
} from "./runtime/browserExport";
export { readBrowserVideoMetadata } from "./runtime/videoMetadata";
export type { VideoMetadata, VideoMetadataResult, VideoMetadataSource } from "./runtime/videoMetadata";
export { createExternalVideoMetadataProvider } from "./runtime/externalVideoMetadataApi";
export type { ExternalVideoMetadataApiResponse, ExternalVideoMetadataProviderOptions } from "./runtime/externalVideoMetadataApi";
export { evaluateBrowserPortabilityEvidence, evaluateBrowserPortabilityEvidenceMatrix } from "./runtime/portabilityEvidence";
export type {
  BrowserPortabilityEvidenceMatrixInput,
  BrowserPortabilityEvidenceMatrixResult,
  BrowserPortabilityEvidenceInput,
  BrowserPortabilityEvidenceResult,
  BrowserPortabilityEvidenceTargetInput,
  BrowserPortabilityEvidenceTargetResult,
  RequiredBrowserExportEvidence,
} from "./runtime/portabilityEvidence";
