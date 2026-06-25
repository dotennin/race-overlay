export const PREFERRED_WEBM_MIME_TYPE = "video/webm;codecs=vp9,opus";
export const FALLBACK_WEBM_MIME_TYPE = "video/webm";

export interface CapturableVideoElement extends HTMLVideoElement {
  captureStream?: () => MediaStream;
}

export interface StartBrowserWebmExportOptions {
  video: HTMLVideoElement;
  width: number;
  height: number;
  fps: number;
  bitrateMbps: number;
  exportDurationSeconds?: number | null;
  playPromise?: Promise<unknown>;
  renderFrame: (canvas: HTMLCanvasElement, video: HTMLVideoElement) => void;
  onProgress?: (progress: BrowserWebmExportProgress) => void;
}

export interface BrowserWebmExportRun {
  canvas: HTMLCanvasElement;
  done: Promise<Blob>;
  report: Promise<BrowserWebmExportReport>;
  stop: () => void;
}

export interface BrowserWebmExportProgress {
  currentTimeSeconds: number;
  durationSeconds: number | null;
  ratio: number;
}

export interface BrowserWebmExportCapabilities {
  canExportWebm: boolean;
  supportedMimeType: string | null;
  supportsCanvasCapture: boolean;
  supportsVideoCaptureStream: boolean;
  sourceAudioTrackCount: number | null;
  supportsMemoryMeasurement: boolean;
}

export interface BrowserWebmExportCapabilitiesEvidenceContext {
  generatedAt?: string;
  videoName?: string;
  browserName?: string;
}

export interface BrowserWebmExportCapabilitiesEvidence {
  schemaVersion: 1;
  generatedAt: string;
  status: "capabilities";
  videoName?: string;
  browserName?: string;
  capabilities: BrowserWebmExportCapabilities;
}

export type BrowserWebmExportPlaybackMode = "normal" | "muted-fallback";

export interface BrowserWebmExportReport {
  width: number;
  height: number;
  fps: number;
  bitrateMbps: number;
  mimeType: string;
  elapsedMs: number;
  outputBytes: number;
  durationSeconds: number | null;
  audioTrackCount: number;
  memoryUsedBytes: number | null;
  playbackMode: BrowserWebmExportPlaybackMode;
}

export interface BrowserWebmExportReportEvidenceContext {
  generatedAt?: string;
  activityName?: string;
  videoName?: string;
}

export interface BrowserWebmExportReportEvidence {
  schemaVersion: 1;
  generatedAt: string;
  activityName?: string;
  videoName?: string;
  status?: "completed";
  report: BrowserWebmExportReport;
}

export interface BrowserWebmExportFailureEvidenceContext extends BrowserWebmExportReportEvidenceContext {
  width: number;
  height: number;
  fps: number;
  bitrateMbps: number;
  durationSeconds?: number | null;
}

export interface BrowserWebmExportFailureEvidence {
  schemaVersion: 1;
  generatedAt: string;
  activityName?: string;
  videoName?: string;
  status: "failed";
  error: string;
  attemptedExport: {
    width: number;
    height: number;
    fps: number;
    bitrateMbps: number;
    durationSeconds: number | null;
  };
}

export function serializeBrowserWebmExportCapabilities(
  capabilities: BrowserWebmExportCapabilities,
  context: BrowserWebmExportCapabilitiesEvidenceContext = {},
): string {
  const evidence: BrowserWebmExportCapabilitiesEvidence = {
    schemaVersion: 1,
    generatedAt: context.generatedAt ?? new Date().toISOString(),
    status: "capabilities",
    capabilities,
  };
  if (context.videoName) {
    evidence.videoName = context.videoName;
  }
  if (context.browserName) {
    evidence.browserName = context.browserName;
  }
  return JSON.stringify(evidence, null, 2);
}

export function serializeBrowserWebmExportReport(
  report: BrowserWebmExportReport,
  context: BrowserWebmExportReportEvidenceContext = {},
): string {
  const evidence: BrowserWebmExportReportEvidence = {
    schemaVersion: 1,
    generatedAt: context.generatedAt ?? new Date().toISOString(),
    report,
  };
  if (context.activityName) {
    evidence.activityName = context.activityName;
  }
  if (context.videoName) {
    evidence.videoName = context.videoName;
  }
  return JSON.stringify(evidence, null, 2);
}

export function serializeBrowserWebmExportFailure(
  error: unknown,
  context: BrowserWebmExportFailureEvidenceContext,
): string {
  const evidence: BrowserWebmExportFailureEvidence = {
    schemaVersion: 1,
    generatedAt: context.generatedAt ?? new Date().toISOString(),
    status: "failed",
    error: error instanceof Error ? error.message : String(error),
    attemptedExport: {
      width: context.width,
      height: context.height,
      fps: context.fps,
      bitrateMbps: context.bitrateMbps,
      durationSeconds: context.durationSeconds ?? null,
    },
  };
  if (context.activityName) {
    evidence.activityName = context.activityName;
  }
  if (context.videoName) {
    evidence.videoName = context.videoName;
  }
  return JSON.stringify(evidence, null, 2);
}

export function supportedWebmMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") {
    return null;
  }
  if (typeof MediaRecorder.isTypeSupported !== "function") {
    return FALLBACK_WEBM_MIME_TYPE;
  }
  if (MediaRecorder.isTypeSupported(PREFERRED_WEBM_MIME_TYPE)) {
    return PREFERRED_WEBM_MIME_TYPE;
  }
  return MediaRecorder.isTypeSupported(FALLBACK_WEBM_MIME_TYPE) ? FALLBACK_WEBM_MIME_TYPE : null;
}

export function readBrowserWebmExportCapabilities(video?: HTMLVideoElement | null): BrowserWebmExportCapabilities {
  const canvas = typeof document === "undefined" ? null : document.createElement("canvas");
  const supportedMimeType = supportedWebmMimeType();
  const supportsCanvasCapture = typeof canvas?.captureStream === "function";
  const capturableVideo = video as CapturableVideoElement | null | undefined;
  const videoCaptureStream =
    capturableVideo && typeof capturableVideo.captureStream === "function" ? capturableVideo.captureStream() : null;
  return {
    canExportWebm: Boolean(supportedMimeType && supportsCanvasCapture),
    supportedMimeType,
    supportsCanvasCapture,
    supportsVideoCaptureStream: Boolean(videoCaptureStream),
    sourceAudioTrackCount: videoCaptureStream ? videoCaptureStream.getAudioTracks().length : null,
    supportsMemoryMeasurement: browserMemoryUsedBytes() != null,
  };
}

function requestNextFrame(callback: FrameRequestCallback): number {
  if (typeof requestAnimationFrame === "function") {
    return requestAnimationFrame(callback);
  }
  return window.setTimeout(() => callback(performance.now()), 16);
}

function cancelNextFrame(handle: number): void {
  if (typeof cancelAnimationFrame === "function") {
    cancelAnimationFrame(handle);
    return;
  }
  clearTimeout(handle);
}

function exportDurationSecondsForVideo(video: HTMLVideoElement, maxDurationSeconds?: number | null): number | null {
  if (maxDurationSeconds != null && Number.isFinite(maxDurationSeconds) && maxDurationSeconds > 0) {
    return maxDurationSeconds;
  }
  return Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null;
}

function exportProgressForVideo(video: HTMLVideoElement, maxDurationSeconds?: number | null): BrowserWebmExportProgress {
  const durationSeconds = exportDurationSecondsForVideo(video, maxDurationSeconds);
  return {
    currentTimeSeconds: video.currentTime,
    durationSeconds,
    ratio: durationSeconds == null ? 0 : Math.min(Math.max(video.currentTime / durationSeconds, 0), 1),
  };
}

function browserMemoryUsedBytes(): number | null {
  const memory = (performance as Performance & { memory?: { usedJSHeapSize?: number } }).memory;
  return typeof memory?.usedJSHeapSize === "number" ? memory.usedJSHeapSize : null;
}

export function startBrowserWebmExport(options: StartBrowserWebmExportOptions): BrowserWebmExportRun {
  const startedAtMs = performance.now();
  const canvas = document.createElement("canvas");
  canvas.width = options.width;
  canvas.height = options.height;
  const captureStream = canvas.captureStream;
  const mimeType = supportedWebmMimeType();
  if (typeof captureStream !== "function" || !mimeType) {
    throw new Error("This browser cannot export WebM from canvas");
  }

  const stream = captureStream.call(canvas, options.fps);
  const capturableVideo = options.video as CapturableVideoElement;
  const videoCaptureStream =
    typeof capturableVideo.captureStream === "function" ? capturableVideo.captureStream() : null;
  const audioTracks = videoCaptureStream?.getAudioTracks() ?? [];
  audioTracks.forEach((track) => stream.addTrack(track));

  const chunks: Blob[] = [];
  const recorder = new MediaRecorder(stream, {
    mimeType,
    videoBitsPerSecond: Math.max(1, options.bitrateMbps) * 1_000_000,
  });
  let animationFrame = 0;
  let failed = false;
  let stopRequested = false;
  let playbackMode: BrowserWebmExportPlaybackMode = "normal";
  const originalMuted = options.video.muted;

  const restoreMutedState = () => {
    options.video.muted = originalMuted;
  };

  let resolveReport!: (report: BrowserWebmExportReport) => void;
  let rejectReport!: (error: Error) => void;
  const report = new Promise<BrowserWebmExportReport>((resolve, reject) => {
    resolveReport = resolve;
    rejectReport = reject;
  });

  let rejectDone!: (error: Error) => void;
  const done = new Promise<Blob>((resolve, reject) => {
    rejectDone = reject;
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) {
        chunks.push(event.data);
      }
    });
    recorder.addEventListener(
      "stop",
      () => {
        cancelNextFrame(animationFrame);
        if (failed) {
          return;
        }
        const blob = new Blob(chunks, { type: "video/webm" });
        resolveReport({
          width: options.width,
          height: options.height,
          fps: options.fps,
          bitrateMbps: options.bitrateMbps,
          mimeType,
          elapsedMs: performance.now() - startedAtMs,
          outputBytes: blob.size,
          durationSeconds: exportDurationSecondsForVideo(options.video, options.exportDurationSeconds),
          audioTrackCount: audioTracks.length,
          memoryUsedBytes: browserMemoryUsedBytes(),
          playbackMode,
        });
        restoreMutedState();
        resolve(blob);
      },
      { once: true },
    );
  });

  const renderFrame = () => {
    options.renderFrame(canvas, options.video);
    options.onProgress?.(exportProgressForVideo(options.video, options.exportDurationSeconds));
    if (
      options.exportDurationSeconds != null &&
      options.exportDurationSeconds > 0 &&
      options.video.currentTime >= options.exportDurationSeconds
    ) {
      if (recorder.state !== "inactive") {
        recorder.stop();
      }
      return;
    }
    if (!options.video.ended && recorder.state !== "inactive") {
      animationFrame = requestNextFrame(renderFrame);
    }
  };

  options.video.addEventListener(
    "ended",
    () => {
      if (recorder.state !== "inactive") {
        recorder.stop();
      }
    },
    { once: true },
  );

  const failPlayback = (caught: unknown) => {
    failed = true;
    cancelNextFrame(animationFrame);
    restoreMutedState();
    const error =
      caught instanceof Error
        ? new Error(`Unable to play source video for export: ${caught.message}`)
        : new Error("Unable to play source video for export");
    rejectReport(error);
    rejectDone(error);
    if (recorder.state !== "inactive") {
      recorder.stop();
    }
  };

  const ensurePlayback = async () => {
    try {
      await (options.playPromise ?? options.video.play());
    } catch {
      playbackMode = "muted-fallback";
      options.video.muted = true;
      await options.video.play();
    }
  };

  options.video.currentTime = 0;
  void ensurePlayback()
    .then(() => {
      if (failed) {
        return;
      }
      recorder.start();
      renderFrame();
      if (stopRequested && recorder.state !== "inactive") {
        recorder.stop();
      }
    })
    .catch((caught: unknown) => {
      failPlayback(caught);
    });

  const stop = () => {
    if (recorder.state !== "inactive") {
      recorder.stop();
      return;
    }
    stopRequested = true;
  };

  return {
    canvas,
    done,
    report,
    stop,
  };
}
