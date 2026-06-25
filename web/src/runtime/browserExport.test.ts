import { describe, expect, it, vi } from "vitest";

import {
  readBrowserWebmExportCapabilities,
  serializeBrowserWebmExportCapabilities,
  serializeBrowserWebmExportFailure,
  serializeBrowserWebmExportReport,
  startBrowserWebmExport,
  supportedWebmMimeType,
} from "./browserExport";

describe("browser WebM export runtime", () => {
  it("serializes export reports as portable measurement evidence", () => {
    const json = serializeBrowserWebmExportReport(
      {
        width: 1280,
        height: 720,
        fps: 30,
        bitrateMbps: 6,
        mimeType: "video/webm;codecs=vp9,opus",
        elapsedMs: 1234.5,
        outputBytes: 987654,
        durationSeconds: 5,
        audioTrackCount: 1,
        memoryUsedBytes: 456789,
        playbackMode: "normal",
      },
      {
        generatedAt: "2026-06-19T00:00:00.000Z",
        activityName: "sample-measurement.tcx",
        videoName: "sample-measurement.webm",
      },
    );

    expect(JSON.parse(json)).toEqual({
      schemaVersion: 1,
      generatedAt: "2026-06-19T00:00:00.000Z",
      activityName: "sample-measurement.tcx",
      videoName: "sample-measurement.webm",
      report: {
        width: 1280,
        height: 720,
        fps: 30,
        bitrateMbps: 6,
        mimeType: "video/webm;codecs=vp9,opus",
        elapsedMs: 1234.5,
        outputBytes: 987654,
        durationSeconds: 5,
        audioTrackCount: 1,
        memoryUsedBytes: 456789,
        playbackMode: "normal",
      },
    });
  });

  it("serializes export failures as portable measurement evidence", () => {
    const json = serializeBrowserWebmExportFailure(new Error("autoplay blocked"), {
      generatedAt: "2026-06-19T00:00:00.000Z",
      activityName: "sample-measurement.tcx",
      videoName: "sample-measurement.webm",
      width: 1280,
      height: 720,
      fps: 30,
      bitrateMbps: 6,
      durationSeconds: 5,
    });

    expect(JSON.parse(json)).toEqual({
      schemaVersion: 1,
      generatedAt: "2026-06-19T00:00:00.000Z",
      activityName: "sample-measurement.tcx",
      videoName: "sample-measurement.webm",
      status: "failed",
      error: "autoplay blocked",
      attemptedExport: {
        width: 1280,
        height: 720,
        fps: 30,
        bitrateMbps: 6,
        durationSeconds: 5,
      },
    });
  });

  it("detects preferred WebM recording support", () => {
    expect(supportedWebmMimeType()).toBe("video/webm;codecs=vp9,opus");
  });

  it("reports browser export capabilities for migration evidence", () => {
    const video = document.createElement("video");

    expect(readBrowserWebmExportCapabilities(video)).toEqual({
      canExportWebm: true,
      supportedMimeType: "video/webm;codecs=vp9,opus",
      supportsCanvasCapture: true,
      supportsVideoCaptureStream: true,
      sourceAudioTrackCount: 1,
      supportsMemoryMeasurement: false,
    });
  });

  it("serializes browser export capabilities as portable evidence", () => {
    const json = serializeBrowserWebmExportCapabilities(
      {
        canExportWebm: true,
        supportedMimeType: "video/webm;codecs=vp9,opus",
        supportsCanvasCapture: true,
        supportsVideoCaptureStream: true,
        sourceAudioTrackCount: 1,
        supportsMemoryMeasurement: false,
      },
      {
        generatedAt: "2026-06-19T00:00:00.000Z",
        videoName: "race.mp4",
        browserName: "chromium",
      },
    );

    expect(JSON.parse(json)).toEqual({
      schemaVersion: 1,
      generatedAt: "2026-06-19T00:00:00.000Z",
      status: "capabilities",
      videoName: "race.mp4",
      browserName: "chromium",
      capabilities: {
        canExportWebm: true,
        supportedMimeType: "video/webm;codecs=vp9,opus",
        supportsCanvasCapture: true,
        supportsVideoCaptureStream: true,
        sourceAudioTrackCount: 1,
        supportsMemoryMeasurement: false,
      },
    });
  });

  it("records a composed canvas stream with source audio and encoder options", async () => {
    const video = document.createElement("video");
    const renderFrame = vi.fn();
    const onProgress = vi.fn();

    const exportRun = startBrowserWebmExport({
      video,
      width: 960,
      height: 540,
      fps: 24,
      bitrateMbps: 8,
      renderFrame,
      onProgress,
    });

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(renderFrame).toHaveBeenCalledTimes(1);
    expect(onProgress).toHaveBeenCalledWith({
      currentTimeSeconds: 0,
      durationSeconds: null,
      ratio: 0,
    });
    expect(globalThis.__lastRecorderTrackKinds).toEqual(["video", "audio"]);
    expect(globalThis.__lastRecorderOptions).toMatchObject({
      mimeType: "video/webm;codecs=vp9,opus",
      videoBitsPerSecond: 8_000_000,
    });

    exportRun.stop();
    await expect(exportRun.done).resolves.toMatchObject({
      size: 4,
      type: "video/webm",
    });
    await expect(exportRun.report).resolves.toMatchObject({
      width: 960,
      height: 540,
      fps: 24,
      bitrateMbps: 8,
      mimeType: "video/webm;codecs=vp9,opus",
      outputBytes: 4,
      audioTrackCount: 1,
      durationSeconds: null,
      playbackMode: "normal",
    });
  });

  it("stops automatically at the configured short export duration", async () => {
    const video = document.createElement("video");
    const renderFrame = vi.fn((_canvas: HTMLCanvasElement, sourceVideo: HTMLVideoElement) => {
      sourceVideo.currentTime = 5;
    });
    const onProgress = vi.fn();

    const exportRun = startBrowserWebmExport({
      video,
      width: 1280,
      height: 720,
      fps: 30,
      bitrateMbps: 6,
      exportDurationSeconds: 5,
      renderFrame,
      onProgress,
    });

    await expect(exportRun.done).resolves.toMatchObject({ size: 4 });
    await expect(exportRun.report).resolves.toMatchObject({
      width: 1280,
      height: 720,
      durationSeconds: 5,
      outputBytes: 4,
    });
    expect(onProgress).toHaveBeenCalledWith({
      currentTimeSeconds: 5,
      durationSeconds: 5,
      ratio: 1,
    });
  });

  it("falls back to muted playback when browser policy blocks the first play request", async () => {
    const playSpy = vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockRejectedValueOnce(new Error("autoplay blocked"))
      .mockResolvedValueOnce(undefined);
    const video = document.createElement("video");
    const renderFrame = vi.fn((_canvas: HTMLCanvasElement, sourceVideo: HTMLVideoElement) => {
      sourceVideo.currentTime = 5;
    });

    const exportRun = startBrowserWebmExport({
      video,
      width: 1280,
      height: 720,
      fps: 30,
      bitrateMbps: 6,
      exportDurationSeconds: 5,
      renderFrame,
    });

    await expect(exportRun.done).resolves.toMatchObject({ size: 4 });
    await expect(exportRun.report).resolves.toMatchObject({
      width: 1280,
      height: 720,
      playbackMode: "muted-fallback",
    });
    expect(playSpy).toHaveBeenCalledTimes(2);
    expect(video.muted).toBe(false);
  });

  it("rejects export promises when muted playback fallback also fails", async () => {
    vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockRejectedValueOnce(new Error("autoplay blocked"))
      .mockRejectedValueOnce(new Error("muted playback blocked"));
    const video = document.createElement("video");

    const exportRun = startBrowserWebmExport({
      video,
      width: 1280,
      height: 720,
      fps: 30,
      bitrateMbps: 6,
      exportDurationSeconds: 5,
      renderFrame: vi.fn(),
    });

    await expect(exportRun.done).rejects.toThrow("Unable to play source video for export");
    await expect(exportRun.report).rejects.toThrow("Unable to play source video for export");
  });

  it("uses a caller-provided play promise without calling play again", async () => {
    const playSpy = vi.spyOn(HTMLMediaElement.prototype, "play");
    const video = document.createElement("video");
    const exportRun = startBrowserWebmExport({
      video,
      width: 1280,
      height: 720,
      fps: 30,
      bitrateMbps: 6,
      exportDurationSeconds: 5,
      playPromise: Promise.resolve(),
      renderFrame: vi.fn((_canvas: HTMLCanvasElement, sourceVideo: HTMLVideoElement) => {
        sourceVideo.currentTime = 5;
      }),
    });

    await expect(exportRun.done).resolves.toMatchObject({ size: 4 });
    expect(playSpy).not.toHaveBeenCalled();
  });
});
