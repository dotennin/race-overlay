import type {
  BrowserWebmExportCapabilitiesEvidence,
  BrowserWebmExportFailureEvidence,
  BrowserWebmExportReportEvidence,
} from "./browserExport";

export interface RequiredBrowserExportEvidence {
  width: number;
  height: number;
  durationSeconds: number;
}

export interface BrowserPortabilityEvidenceInput {
  capabilities?: BrowserWebmExportCapabilitiesEvidence | null;
  measurements: Array<BrowserWebmExportReportEvidence | BrowserWebmExportFailureEvidence>;
  requiredExports?: RequiredBrowserExportEvidence[];
  requireAudioRetention?: boolean;
}

export interface BrowserPortabilityEvidenceResult {
  ready: boolean;
  status: "go" | "no-go";
  blockers: string[];
  warnings: string[];
  coveredExports: RequiredBrowserExportEvidence[];
}

export interface BrowserPortabilityEvidenceTargetInput extends BrowserPortabilityEvidenceInput {
  name: string;
}

export interface BrowserPortabilityEvidenceTargetResult extends BrowserPortabilityEvidenceResult {
  name: string;
}

export interface BrowserPortabilityEvidenceMatrixInput {
  requiredTargets?: string[];
  targets: BrowserPortabilityEvidenceTargetInput[];
  requiredExports?: RequiredBrowserExportEvidence[];
  requireAudioRetention?: boolean;
}

export interface BrowserPortabilityEvidenceMatrixResult {
  ready: boolean;
  status: "go" | "no-go";
  blockers: string[];
  warnings: string[];
  targets: BrowserPortabilityEvidenceTargetResult[];
}

const DEFAULT_REQUIRED_EXPORTS: RequiredBrowserExportEvidence[] = [
  { width: 1280, height: 720, durationSeconds: 5 },
  { width: 1920, height: 1080, durationSeconds: 5 },
];

function exportLabel(required: RequiredBrowserExportEvidence): string {
  return `${required.width}x${required.height} ${required.durationSeconds}s`;
}

function isFailureEvidence(
  evidence: BrowserWebmExportReportEvidence | BrowserWebmExportFailureEvidence,
): evidence is BrowserWebmExportFailureEvidence {
  return evidence.status === "failed";
}

function matchingReport(
  measurements: Array<BrowserWebmExportReportEvidence | BrowserWebmExportFailureEvidence>,
  required: RequiredBrowserExportEvidence,
): BrowserWebmExportReportEvidence | null {
  return (
    measurements.find(
      (evidence): evidence is BrowserWebmExportReportEvidence =>
        !isFailureEvidence(evidence) &&
        evidence.report.width === required.width &&
        evidence.report.height === required.height &&
        evidence.report.durationSeconds === required.durationSeconds &&
        evidence.report.outputBytes > 0,
    ) ?? null
  );
}

function matchingFailures(
  measurements: Array<BrowserWebmExportReportEvidence | BrowserWebmExportFailureEvidence>,
  required: RequiredBrowserExportEvidence,
): BrowserWebmExportFailureEvidence[] {
  return measurements.filter(
    (evidence): evidence is BrowserWebmExportFailureEvidence =>
      isFailureEvidence(evidence) &&
      evidence.attemptedExport.width === required.width &&
      evidence.attemptedExport.height === required.height &&
      evidence.attemptedExport.durationSeconds === required.durationSeconds,
  );
}

export function evaluateBrowserPortabilityEvidence(
  input: BrowserPortabilityEvidenceInput,
): BrowserPortabilityEvidenceResult {
  const requiredExports = input.requiredExports ?? DEFAULT_REQUIRED_EXPORTS;
  const blockers: string[] = [];
  const warnings: string[] = [];
  const coveredExports: RequiredBrowserExportEvidence[] = [];
  const capabilities = input.capabilities?.capabilities;

  if (!capabilities) {
    blockers.push("Missing browser export capability evidence");
  } else {
    if (!capabilities.canExportWebm) {
      blockers.push("Browser cannot export WebM");
    }
    if (!capabilities.supportsCanvasCapture) {
      blockers.push("Browser does not support canvas capture");
    }
    if (!capabilities.supportedMimeType) {
      blockers.push("Browser has no supported WebM MIME type");
    }
    if (!capabilities.supportsVideoCaptureStream) {
      warnings.push("Browser does not expose source video capture");
    }
    if (input.requireAudioRetention && (capabilities.sourceAudioTrackCount ?? 0) <= 0) {
      blockers.push("Audio retention required but capability evidence has no source audio tracks");
    }
  }

  for (const required of requiredExports) {
    const report = matchingReport(input.measurements, required);
    if (!report) {
      blockers.push(`Missing successful ${exportLabel(required)} export evidence`);
    } else {
      coveredExports.push(required);
      if (input.requireAudioRetention && report.report.audioTrackCount <= 0) {
        blockers.push(`Audio retention required but ${report.report.width}x${report.report.height} evidence has 0 audio tracks`);
      }
      if (report.report.playbackMode === "muted-fallback") {
        warnings.push(`${report.report.width}x${report.report.height} export used muted playback fallback`);
      }
      if (report.report.memoryUsedBytes == null) {
        warnings.push(`${report.report.width}x${report.report.height} evidence has no browser memory measurement`);
      }
    }

    for (const failure of matchingFailures(input.measurements, required)) {
      blockers.push(`Failed ${exportLabel(required)} export evidence: ${failure.error}`);
    }
  }

  return {
    ready: blockers.length === 0,
    status: blockers.length === 0 ? "go" : "no-go",
    blockers,
    warnings,
    coveredExports,
  };
}

export function evaluateBrowserPortabilityEvidenceMatrix(
  input: BrowserPortabilityEvidenceMatrixInput,
): BrowserPortabilityEvidenceMatrixResult {
  const targets = input.targets.map((target) => ({
    name: target.name,
    ...evaluateBrowserPortabilityEvidence({
      capabilities: target.capabilities,
      measurements: target.measurements,
      requiredExports: target.requiredExports ?? input.requiredExports,
      requireAudioRetention: target.requireAudioRetention ?? input.requireAudioRetention,
    }),
  }));
  const targetNames = new Set(targets.map((target) => target.name));
  const missingTargetBlockers = (input.requiredTargets ?? [])
    .filter((targetName) => !targetNames.has(targetName))
    .map((targetName) => `${targetName}: Missing target evidence entry`);
  const blockers = [
    ...missingTargetBlockers,
    ...targets.flatMap((target) => target.blockers.map((blocker) => `${target.name}: ${blocker}`)),
  ];
  const warnings = targets.flatMap((target) => target.warnings.map((warning) => `${target.name}: ${warning}`));

  return {
    ready: blockers.length === 0,
    status: blockers.length === 0 ? "go" : "no-go",
    blockers,
    warnings,
    targets,
  };
}
