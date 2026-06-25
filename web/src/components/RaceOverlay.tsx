import React, { useEffect, useRef, useState } from "react";

import {
  readBrowserWebmExportCapabilities,
  serializeBrowserWebmExportCapabilities,
  serializeBrowserWebmExportFailure,
  serializeBrowserWebmExportReport,
  startBrowserWebmExport,
  supportedWebmMimeType,
  type BrowserWebmExportCapabilities,
  type BrowserWebmExportReport,
  type BrowserWebmExportProgress,
  type BrowserWebmExportRun,
} from "../runtime/browserExport";
import { broadcastRunnerPreset, type HudConfig } from "../runtime/hudConfig";
import { drawHudFrame } from "../runtime/hudRenderer";
import { lapWaterfallStatesForWidgets } from "../runtime/lapWaterfall";
import type { ActivityTrack, HudSample } from "../runtime/models";
import type { RoutePoint } from "../runtime/routeMap";
import { readTcx } from "../runtime/tcx";
import { sampleAt } from "../runtime/sampling";
import { readBrowserVideoMetadata, type VideoMetadata } from "../runtime/videoMetadata";
import { Icon } from "./icons";

export interface RaceOverlayProps {
  activity?: ActivityTrack;
  activityFile?: File | null;
  videoFile?: File | null;
  initialHud?: HudConfig;
  hudConfig?: HudConfig;
  exportWidth?: number;
  exportHeight?: number;
  exportDurationSeconds?: number;
  videoMetadataScanBytes?: number;
  externalVideoMetadataProvider?: (file: File) => Promise<VideoMetadata | null>;
  onHudChange?: (hudConfig: HudConfig) => void;
  onExportProgress?: (progress: BrowserWebmExportProgress) => void;
  onExportReport?: (report: BrowserWebmExportReport) => void;
  onExportComplete?: (blob: Blob) => void;
}

const PREFERRED_WEBM_MIME_TYPE = "video/webm;codecs=vp9,opus";

function formatDistance(sample: HudSample): string {
  if (sample.distanceM == null) {
    return "-- km";
  }
  return `${(sample.distanceM / 1000).toFixed(2)} km`;
}

function formatSpeed(sample: HudSample): string {
  if (sample.speedMps == null) {
    return "-- m/s";
  }
  return `${sample.speedMps.toFixed(1)} m/s`;
}

function formatHeartRate(sample: HudSample): string {
  if (sample.heartRateBpm == null) {
    return "-- bpm";
  }
  return `${sample.heartRateBpm} bpm`;
}

function activityTimeBounds(activity: ActivityTrack | null): { startMs: number; endMs: number } | null {
  if (!activity?.samples.length) {
    return null;
  }
  return {
    startMs: new Date(activity.samples[0].timestamp).getTime(),
    endMs: new Date(activity.samples[activity.samples.length - 1].timestamp).getTime(),
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function roundTenths(value: number): number {
  return Math.round(value * 10) / 10;
}

function formatReportDuration(report: BrowserWebmExportReport): string {
  return report.durationSeconds == null ? "full video" : `${report.durationSeconds}s`;
}

function formatReportMemory(report: BrowserWebmExportReport): string {
  return report.memoryUsedBytes == null ? "memory unavailable" : `${report.memoryUsedBytes} bytes memory`;
}

function formatYesNo(value: boolean): string {
  return value ? "yes" : "no";
}

function formatExportCapabilities(capabilities: BrowserWebmExportCapabilities): string {
  return [
    `WebM ${formatYesNo(capabilities.canExportWebm)}`,
    `MIME ${capabilities.supportedMimeType ?? "none"}`,
    `canvas capture ${formatYesNo(capabilities.supportsCanvasCapture)}`,
    `video capture ${
      capabilities.sourceAudioTrackCount == null ? "pending" : formatYesNo(capabilities.supportsVideoCaptureStream)
    }`,
    `source audio tracks ${capabilities.sourceAudioTrackCount ?? "unknown"}`,
    `memory measurement ${formatYesNo(capabilities.supportsMemoryMeasurement)}`,
  ].join(" · ");
}

function measurementEvidenceFilename(videoName: string): string {
  const baseName = videoName.replace(/\.[^.]+$/, "") || "race-overlay";
  return `${baseName}-measurement.json`;
}

function exportCapabilitiesEvidenceFilename(videoName: string): string {
  const baseName = videoName.replace(/\.[^.]+$/, "") || "race-overlay";
  return `${baseName}-export-capabilities.json`;
}

function activityRangeStatus(
  activity: ActivityTrack | null,
  videoTimeSeconds: number,
  activityOffsetSeconds: number,
): string {
  const bounds = activityTimeBounds(activity);
  if (!bounds) {
    return "";
  }
  const requestedMs = bounds.startMs + (videoTimeSeconds + activityOffsetSeconds) * 1000;
  if (requestedMs < bounds.startMs) {
    return "TCX range start";
  }
  if (requestedMs > bounds.endMs) {
    return "TCX range end";
  }
  return "TCX range inside";
}

function sampleForVideoTime(
  activity: ActivityTrack | null,
  videoTimeSeconds: number,
  activityOffsetSeconds: number,
): HudSample | null {
  if (!activity?.samples.length) {
    return null;
  }
  if (activity.samples.length === 1) {
    const sample = activity.samples[0];
    return {
      ...sample,
      paceSecondsPerKm: sample.speedMps ? 1000 / sample.speedMps : null,
    };
  }
  const bounds = activityTimeBounds(activity);
  if (!bounds) {
    return null;
  }
  const sampleMs = clamp(
    bounds.startMs + (videoTimeSeconds + activityOffsetSeconds) * 1000,
    bounds.startMs,
    bounds.endMs,
  );
  return sampleAt(activity, new Date(sampleMs).toISOString());
}

function routePointsForActivity(activity: ActivityTrack | null): RoutePoint[] {
  if (!activity) {
    return [];
  }
  return activity.samples
    .filter((item) => item.latitude != null && item.longitude != null)
    .map((item) => [item.latitude as number, item.longitude as number]);
}

function drawComposedFrame(
  canvas: HTMLCanvasElement,
  video: HTMLVideoElement,
  sample: HudSample | null,
  activity: ActivityTrack,
  hudConfig: HudConfig,
): void {
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  context.fillStyle = "#050807";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  drawHudFrame(canvas, {
    sample,
    hasVideo: true,
    hudConfig,
    routePoints: routePointsForActivity(activity),
    lapStates: sample ? lapWaterfallStatesForWidgets(hudConfig, activity.laps, sample.timestamp) : undefined,
    clearCanvas: false,
  });
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function readFileText(file: File): Promise<string> {
  if (typeof file.text === "function") {
    return file.text();
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Unable to read activity file"));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsText(file);
  });
}

export function RaceOverlay({
  activity: providedActivity,
  activityFile,
  videoFile,
  initialHud,
  hudConfig: controlledHudConfig,
  exportWidth = 960,
  exportHeight = 540,
  exportDurationSeconds = 5,
  videoMetadataScanBytes,
  externalVideoMetadataProvider,
  onHudChange,
  onExportProgress,
  onExportReport,
  onExportComplete,
}: RaceOverlayProps): React.ReactElement {
  const [activity, setActivity] = useState<ActivityTrack | null>(providedActivity ?? null);
  const [hudConfig, setHudConfig] = useState<HudConfig>(() => controlledHudConfig ?? initialHud ?? broadcastRunnerPreset());
  const [activityName, setActivityName] = useState<string>(providedActivity ? "Provided activity" : "");
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [videoName, setVideoName] = useState<string>("");
  const [videoMetadata, setVideoMetadata] = useState<VideoMetadata | null>(null);
  const [videoMetadataStatus, setVideoMetadataStatus] = useState<string>("");
  const [videoTimeSeconds, setVideoTimeSeconds] = useState(0);
  const [activityOffsetSeconds, setActivityOffsetSeconds] = useState(0);
  const [exportWidthValue, setExportWidthValue] = useState(exportWidth);
  const [exportHeightValue, setExportHeightValue] = useState(exportHeight);
  const [exportFps, setExportFps] = useState(30);
  const [exportBitrateMbps, setExportBitrateMbps] = useState(6);
  const [exportDuration, setExportDuration] = useState(exportDurationSeconds);
  const [exportStatus, setExportStatus] = useState<string>("");
  const [isExporting, setIsExporting] = useState(false);
  const [lastExportReport, setLastExportReport] = useState<BrowserWebmExportReport | null>(null);
  const [lastExportFailureJson, setLastExportFailureJson] = useState("");
  const [exportCapabilities, setExportCapabilities] = useState<BrowserWebmExportCapabilities>(() =>
    readBrowserWebmExportCapabilities(null),
  );
  const [error, setError] = useState<string>("");
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const videoMetadataRequestIdRef = useRef(0);
  const currentExportRef = useRef<{ id: number; run: BrowserWebmExportRun; canceled: boolean } | null>(null);
  const nextExportIdRef = useRef(0);
  const sample = sampleForVideoTime(activity, videoTimeSeconds, activityOffsetSeconds);

  useEffect(() => {
    if (providedActivity) {
      setActivity(providedActivity);
      setActivityName("Provided activity");
    }
  }, [providedActivity]);

  useEffect(() => {
    if (controlledHudConfig) {
      setHudConfig(controlledHudConfig);
    }
  }, [controlledHudConfig]);

  useEffect(() => {
    if (!controlledHudConfig && initialHud) {
      setHudConfig(initialHud);
    }
  }, [controlledHudConfig, initialHud]);

  useEffect(() => {
    setExportDuration(exportDurationSeconds);
  }, [exportDurationSeconds]);

  useEffect(() => {
    setExportWidthValue(exportWidth);
  }, [exportWidth]);

  useEffect(() => {
    setExportHeightValue(exportHeight);
  }, [exportHeight]);

  useEffect(() => {
    if (activityFile) {
      void loadActivityFile(activityFile);
    }
  }, [activityFile]);

  useEffect(() => {
    if (videoFile) {
      loadVideoFile(videoFile);
    }
  }, [videoFile]);

  useEffect(() => {
    if (canvasRef.current) {
      drawHudFrame(canvasRef.current, {
        sample,
        hasVideo: Boolean(videoUrl),
        hudConfig,
        routePoints: routePointsForActivity(activity),
        lapStates: sample && activity ? lapWaterfallStatesForWidgets(hudConfig, activity.laps, sample.timestamp) : undefined,
      });
    }
  }, [activity, hudConfig, sample, videoUrl]);

  useEffect(
    () => () => {
      if (videoUrl) {
        URL.revokeObjectURL(videoUrl);
      }
    },
    [videoUrl],
  );

  async function loadActivityFile(file: File): Promise<void> {
    try {
      setError("");
      setActivity(readTcx(await readFileText(file)));
      setActivityName(file.name);
      setVideoTimeSeconds(0);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to read activity file");
    }
  }

  async function handleActivityFile(event: React.ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    if (file) {
      await loadActivityFile(file);
    }
  }

  function loadVideoFile(file: File): void {
    const metadataRequestId = videoMetadataRequestIdRef.current + 1;
    videoMetadataRequestIdRef.current = metadataRequestId;
    setError("");
    setVideoName(file.name);
    setVideoMetadata(null);
    setExportCapabilities(readBrowserWebmExportCapabilities(null));
    setVideoTimeSeconds(0);
    setVideoUrl((previous) => {
      if (previous) {
        URL.revokeObjectURL(previous);
      }
      return URL.createObjectURL(file);
    });

    void (async () => {
      try {
        setVideoMetadataStatus("Reading browser container metadata...");
        const result = await readBrowserVideoMetadata(file, videoMetadataScanBytes);
        if (videoMetadataRequestIdRef.current !== metadataRequestId) {
          return;
        }
        if (result.metadata) {
          setVideoMetadata(result.metadata);
          setVideoMetadataStatus("Browser metadata ready");
          return;
        }
        if (externalVideoMetadataProvider) {
          setVideoMetadataStatus("Requesting external metadata API...");
          const externalMetadata = await externalVideoMetadataProvider(file);
          if (videoMetadataRequestIdRef.current !== metadataRequestId) {
            return;
          }
          setVideoMetadata(externalMetadata);
          setVideoMetadataStatus(externalMetadata ? "External metadata ready" : "Needs external metadata API");
          if (!externalMetadata && result.reason) {
            setError(result.reason);
          }
          return;
        }
        setVideoMetadata(null);
        setVideoMetadataStatus("Needs external metadata API");
        if (result.reason) {
          setError(result.reason);
        }
      } catch (caught) {
        if (videoMetadataRequestIdRef.current !== metadataRequestId) {
          return;
        }
        setVideoMetadataStatus("Needs external metadata API");
        setVideoMetadata(null);
        setError(caught instanceof Error ? caught.message : "Unable to read browser video metadata");
      }
    })();
  }

  function handleVideoFile(event: React.ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0];
    if (file) {
      loadVideoFile(file);
    }
  }

  function updateHudConfig(updater: (current: HudConfig) => HudConfig): void {
    setHudConfig((current) => {
      const next = updater(current);
      onHudChange?.(next);
      return next;
    });
  }

  function setShowUnits(showUnits: boolean): void {
    updateHudConfig((current) => ({
      ...current,
      theme: {
        ...current.theme,
        showUnits,
      },
    }));
  }

  async function handleExportWebm(): Promise<void> {
    const video = videoRef.current;
    if (!video || !activity?.samples.length) {
      setError("Load a video and TCX before exporting");
      return;
    }
    currentExportRef.current?.run.stop();
    setError("");
    setExportStatus("Exporting WebM...");
    setIsExporting(true);
    setLastExportReport(null);
    setLastExportFailureJson("");
    const exportId = nextExportIdRef.current + 1;
    nextExportIdRef.current = exportId;
    const handleExportError = (caught: unknown) => {
      if (currentExportRef.current?.id !== exportId || currentExportRef.current?.canceled) {
        return;
      }
      setError(caught instanceof Error ? caught.message : "This browser cannot export WebM from canvas");
      setExportStatus("");
      setIsExporting(false);
      currentExportRef.current = null;
      setLastExportFailureJson(
        serializeBrowserWebmExportFailure(caught, {
          activityName: activityName || undefined,
          videoName: videoName || undefined,
          width: exportWidthValue,
          height: exportHeightValue,
          fps: exportFps,
          bitrateMbps: exportBitrateMbps,
          durationSeconds: exportDuration,
        }),
      );
    };
    try {
      video.currentTime = 0;
      const playPromise = video.play();
      const exportRun = startBrowserWebmExport({
        video,
        width: exportWidthValue,
        height: exportHeightValue,
        fps: exportFps,
        bitrateMbps: exportBitrateMbps,
        exportDurationSeconds: exportDuration,
        playPromise,
        renderFrame: (exportCanvas, sourceVideo) => {
          const frameSample = sampleForVideoTime(activity, sourceVideo.currentTime, activityOffsetSeconds);
          drawComposedFrame(exportCanvas, sourceVideo, frameSample, activity, hudConfig);
        },
        onProgress: onExportProgress,
      });
      currentExportRef.current = { id: exportId, run: exportRun, canceled: false };
      void exportRun.done.then((blob) => {
        if (currentExportRef.current?.id !== exportId || currentExportRef.current?.canceled) {
          return;
        }
        onExportComplete?.(blob);
        downloadBlob(blob, `${videoName.replace(/\.[^.]+$/, "") || "race-overlay"}.webm`);
        currentExportRef.current = null;
      }, handleExportError);
      void exportRun.report.then((report) => {
        if (currentExportRef.current?.id !== exportId || currentExportRef.current?.canceled) {
          return;
        }
        setLastExportReport(report);
        setLastExportFailureJson("");
        onExportReport?.(report);
        setExportStatus(`Exported ${report.outputBytes} bytes · ${report.width}x${report.height}`);
        setIsExporting(false);
      }, handleExportError);
    } catch (caught) {
      handleExportError(caught);
    }
  }

  function handleCancelExport(): void {
    const currentExport = currentExportRef.current;
    if (!currentExport) {
      return;
    }
    currentExport.canceled = true;
    currentExport.run.stop();
    currentExportRef.current = null;
    setIsExporting(false);
    setExportStatus("Export canceled");
    setLastExportReport(null);
    setLastExportFailureJson("");
    setError("");
  }

  const sampleCount = activity?.samples.length ?? 0;
  const activityStatus = activityName
    ? `${activityName} · ${sampleCount} ${sampleCount === 1 ? "sample" : "samples"}`
    : "No TCX loaded";
  const webmMimeType = supportedWebmMimeType();
  const exportCapabilityStatus =
    webmMimeType === PREFERRED_WEBM_MIME_TYPE
      ? "WebM VP9/Opus supported"
      : webmMimeType
        ? "WebM export supported"
        : "WebM export unsupported";
  const exportCapabilitiesStatus = formatExportCapabilities(exportCapabilities);
  const measurementEvidenceJson = lastExportReport
    ? serializeBrowserWebmExportReport(lastExportReport, {
        activityName: activityName || undefined,
        videoName: videoName || undefined,
      })
    : "";
  const exportCapabilitiesEvidenceJson = serializeBrowserWebmExportCapabilities(exportCapabilities, {
    videoName: videoName || undefined,
  });

  return (
    <section className="race-overlay">
      <aside className="race-overlay__panel" aria-label="Race overlay controls">
        <label className="race-overlay__file">
          <Icon name="upload" aria-hidden="true" size={18} />
          <span>TCX</span>
          <input
            aria-label="TCX file"
            type="file"
            accept=".tcx,application/xml,text/xml"
            onChange={handleActivityFile}
          />
        </label>
        <label className="race-overlay__file">
          <Icon name="film" aria-hidden="true" size={18} />
          <span>Video</span>
          <input aria-label="Video file" type="file" accept="video/*,.mp4,.mov,.webm" onChange={handleVideoFile} />
        </label>
        <p className="race-overlay__status">
          Local video stays in the browser; container creation_time is parsed client-side when available.
        </p>
        {error ? <p className="race-overlay__error">{error}</p> : null}
        <p className="race-overlay__status">{activityStatus}</p>
        <p className="race-overlay__status">{videoName ? `${videoName} · ${videoTimeSeconds.toFixed(1)}s` : "No video loaded"}</p>
        <p className="race-overlay__status">
          {videoMetadata
            ? `${videoMetadata.name} · created ${videoMetadata.creationTime} · ${videoMetadata.source}`
            : "No browser video creation_time"}
        </p>
        {videoMetadataStatus ? <p className="race-overlay__status">{videoMetadataStatus}</p> : null}
        <p className="race-overlay__status">{activityRangeStatus(activity, videoTimeSeconds, activityOffsetSeconds)}</p>
        <label className="race-overlay__field">
          <span>TCX offset seconds</span>
          <input
            aria-label="TCX offset seconds"
            type="number"
            step="0.1"
            value={activityOffsetSeconds}
            onInput={(event) => setActivityOffsetSeconds(Number.parseFloat(event.currentTarget.value) || 0)}
          />
        </label>
        <div className="race-overlay__button-row" aria-label="TCX offset nudges">
          <button
            className="race-overlay__button"
            type="button"
            aria-label="Nudge TCX offset backward 0.5 seconds"
            onClick={() => setActivityOffsetSeconds((value) => roundTenths(value - 0.5))}
          >
            -0.5s
          </button>
          <button
            className="race-overlay__button"
            type="button"
            aria-label="Nudge TCX offset forward 0.5 seconds"
            onClick={() => setActivityOffsetSeconds((value) => roundTenths(value + 0.5))}
          >
            +0.5s
          </button>
        </div>
        <label className="race-overlay__field">
          <span>Show HUD units</span>
          <input
            aria-label="Show HUD units"
            type="checkbox"
            checked={hudConfig.theme.showUnits}
            onChange={(event) => setShowUnits(event.currentTarget.checked)}
          />
        </label>
        <label className="race-overlay__field">
          <span>Export duration seconds</span>
          <input
            aria-label="Export duration seconds"
            type="number"
            min="1"
            step="1"
            value={exportDuration}
            onInput={(event) => setExportDuration(Math.max(1, Number.parseFloat(event.currentTarget.value) || 5))}
          />
        </label>
        <label className="race-overlay__field">
          <span>Export width</span>
          <input
            aria-label="Export width"
            type="number"
            min="1"
            step="1"
            value={exportWidthValue}
            onInput={(event) => setExportWidthValue(Math.max(1, Number.parseInt(event.currentTarget.value, 10) || 960))}
          />
        </label>
        <label className="race-overlay__field">
          <span>Export height</span>
          <input
            aria-label="Export height"
            type="number"
            min="1"
            step="1"
            value={exportHeightValue}
            onInput={(event) => setExportHeightValue(Math.max(1, Number.parseInt(event.currentTarget.value, 10) || 540))}
          />
        </label>
        <label className="race-overlay__field">
          <span>Export FPS</span>
          <input
            aria-label="Export FPS"
            type="number"
            min="1"
            max="60"
            step="1"
            value={exportFps}
            onInput={(event) => setExportFps(Math.max(1, Number.parseInt(event.currentTarget.value, 10) || 30))}
          />
        </label>
        <label className="race-overlay__field">
          <span>Export bitrate Mbps</span>
          <input
            aria-label="Export bitrate Mbps"
            type="number"
            min="1"
            step="0.5"
            value={exportBitrateMbps}
            onInput={(event) => setExportBitrateMbps(Math.max(1, Number.parseFloat(event.currentTarget.value) || 6))}
          />
        </label>
        <p className="race-overlay__status">{exportCapabilityStatus}</p>
        <p className="race-overlay__status" aria-label="Browser export capabilities">
          {exportCapabilitiesStatus}
        </p>
        <div className="race-overlay__status" aria-label="Browser export capability report">
          <strong>Browser export capability report</strong>
          <button
            aria-label="Download browser export capability evidence JSON"
            className="race-overlay__button"
            type="button"
            onClick={() => {
              downloadBlob(
                new Blob([exportCapabilitiesEvidenceJson], { type: "application/json" }),
                exportCapabilitiesEvidenceFilename(videoName),
              );
            }}
          >
            Download capability JSON
          </button>
          <pre className="race-overlay__evidence-json" aria-label="Browser export capability evidence JSON">
            {exportCapabilitiesEvidenceJson}
          </pre>
        </div>
        <button
          aria-label="Export WebM"
          className="race-overlay__button"
          type="button"
          disabled={!activity || !videoUrl || isExporting}
          onClick={handleExportWebm}
        >
          <Icon name="download" aria-hidden="true" size={18} />
          <span>Export WebM</span>
        </button>
        {isExporting ? (
          <button
            aria-label="Cancel WebM export"
            className="race-overlay__button"
            type="button"
            onClick={handleCancelExport}
          >
            Cancel export
          </button>
        ) : null}
        {exportStatus ? <p className="race-overlay__status">{exportStatus}</p> : null}
        {lastExportReport ? (
          <div className="race-overlay__status" aria-label="Measurement report">
            <strong>Measurement report</strong>
            <p>
              {lastExportReport.width}x{lastExportReport.height} · {formatReportDuration(lastExportReport)} ·{" "}
              {lastExportReport.mimeType}
            </p>
            <p>
              elapsed {Math.round(lastExportReport.elapsedMs)}ms · output {lastExportReport.outputBytes} bytes · audio
              tracks {lastExportReport.audioTrackCount}
            </p>
            <p>{formatReportMemory(lastExportReport)}</p>
            <button
              aria-label="Download measurement evidence JSON"
              className="race-overlay__button"
              type="button"
              onClick={() => {
                downloadBlob(
                  new Blob([measurementEvidenceJson], { type: "application/json" }),
                  measurementEvidenceFilename(videoName),
                );
              }}
            >
              Download measurement JSON
            </button>
            <pre className="race-overlay__evidence-json" aria-label="Measurement evidence JSON">
              {measurementEvidenceJson}
            </pre>
          </div>
        ) : null}
        {lastExportFailureJson ? (
          <div className="race-overlay__status" aria-label="Measurement failure report">
            <strong>Measurement failure report</strong>
            <button
              aria-label="Download measurement failure JSON"
              className="race-overlay__button"
              type="button"
              onClick={() => {
                downloadBlob(
                  new Blob([lastExportFailureJson], { type: "application/json" }),
                  measurementEvidenceFilename(videoName).replace("-measurement.json", "-measurement-failure.json"),
                );
              }}
            >
              Download failure JSON
            </button>
            <pre className="race-overlay__evidence-json" aria-label="Measurement failure evidence JSON">
              {lastExportFailureJson}
            </pre>
          </div>
        ) : null}
        <div className="race-overlay__metric">
          <Icon name="activity" aria-hidden="true" size={18} />
          <span>{sample ? formatDistance(sample) : "-- km"}</span>
        </div>
        <div className="race-overlay__metric">
          <Icon name="heart-pulse" aria-hidden="true" size={18} />
          <span>{sample ? formatHeartRate(sample) : "-- bpm"}</span>
        </div>
        <div className="race-overlay__metric">
          <Icon name="gauge" aria-hidden="true" size={18} />
          <span>{sample ? formatSpeed(sample) : "-- m/s"}</span>
        </div>
      </aside>
      <div className="race-overlay__stage">
        <div className="race-overlay__preview">
          {videoUrl ? (
            <video
              ref={videoRef}
              src={videoUrl}
              controls
              onLoadedMetadata={(event) => {
                setVideoTimeSeconds(event.currentTarget.currentTime);
                setExportCapabilities(readBrowserWebmExportCapabilities(event.currentTarget));
              }}
              onTimeUpdate={(event) => setVideoTimeSeconds(event.currentTarget.currentTime)}
              onSeeked={(event) => setVideoTimeSeconds(event.currentTarget.currentTime)}
            />
          ) : null}
          <canvas ref={canvasRef} width={960} height={540} aria-label="Race overlay preview" />
        </div>
      </div>
    </section>
  );
}
