import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { broadcastRunnerPreset } from "../runtime/hudConfig";
import type { ActivityTrack } from "../runtime/models";
import { RaceOverlay } from "./RaceOverlay";

const QUICKTIME_EPOCH_OFFSET_SECONDS = 2_082_844_800;

function changeFileInput(input: HTMLInputElement, file: File): void {
  Object.defineProperty(input, "files", {
    configurable: true,
    value: [file],
  });
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function changeTextInput(input: HTMLInputElement, value: string): void {
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

async function flushAsyncWork(): Promise<void> {
  for (let index = 0; index < 5; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await Promise.resolve();
  }
}

function ascii(value: string): number[] {
  return [...value].map((character) => character.charCodeAt(0));
}

function uint32(value: number): number[] {
  return [(value >>> 24) & 0xff, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff];
}

function box(type: string, payload: number[]): Uint8Array {
  return Uint8Array.from([...uint32(payload.length + 8), ...ascii(type), ...payload]);
}

function concat(...arrays: Uint8Array[]): Uint8Array {
  const bytes = new Uint8Array(arrays.reduce((sum, array) => sum + array.length, 0));
  let offset = 0;
  for (const array of arrays) {
    bytes.set(array, offset);
    offset += array.length;
  }
  return bytes;
}

function mp4WithMvhdCreationTime(isoTimestamp: string): Uint8Array {
  const unixSeconds = Math.floor(new Date(isoTimestamp).getTime() / 1000);
  const quickTimeSeconds = unixSeconds + QUICKTIME_EPOCH_OFFSET_SECONDS;
  const mvhdPayload = [
    0,
    0,
    0,
    0,
    ...uint32(quickTimeSeconds),
    ...uint32(quickTimeSeconds),
    ...uint32(1000),
    ...uint32(0),
  ];
  return concat(box("ftyp", ascii("isom0000")), box("moov", [...box("mvhd", mvhdPayload)]));
}

function asArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function tcxXml(): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap StartTime="2026-04-19T00:45:00Z">
        <Track>
          <Trackpoint>
            <Time>2026-04-19T00:45:00Z</Time>
            <DistanceMeters>0</DistanceMeters>
            <HeartRateBpm><Value>100</Value></HeartRateBpm>
            <Cadence>85</Cadence>
          </Trackpoint>
          <Trackpoint>
            <Time>2026-04-19T00:45:10Z</Time>
            <DistanceMeters>100</DistanceMeters>
            <HeartRateBpm><Value>120</Value></HeartRateBpm>
            <Cadence>90</Cadence>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>`;
}

function twoSampleActivity(): ActivityTrack {
  return {
    sport: "Running",
    laps: [],
    samples: [
      {
        timestamp: "2026-04-19T00:45:00.000Z",
        latitude: 36,
        longitude: 140,
        altitudeM: 0,
        distanceM: 0,
        speedMps: 2,
        heartRateBpm: 100,
        cadenceSpm: 170,
      },
      {
        timestamp: "2026-04-19T00:45:10.000Z",
        latitude: 36.001,
        longitude: 140.001,
        altitudeM: 5,
        distanceM: 100,
        speedMps: 4,
        heartRateBpm: 120,
        cadenceSpm: 180,
      },
    ],
  };
}

describe("RaceOverlay", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a canvas preview and selected metric values", async () => {
    const activity: ActivityTrack = {
      sport: "Running",
      laps: [],
      samples: [
        {
          timestamp: "2026-04-19T00:45:05.000Z",
          latitude: 36,
          longitude: 140,
          altitudeM: -1.4,
          distanceM: 1200,
          speedMps: 4,
          heartRateBpm: 128,
          cadenceSpm: 180,
        },
      ],
    };
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={activity} />);
    });

    expect(host.querySelector("canvas")).not.toBeNull();
    expect(host.textContent).toContain("1.20 km");
    expect(host.textContent).toContain("128 bpm");
    expect(host.textContent).toContain("4.0 m/s");
  });

  it("draws the configured HUD widgets instead of a hard-coded overlay", async () => {
    const hudConfig = broadcastRunnerPreset();
    hudConfig.widgets = hudConfig.widgets.filter((widget) => widget.id === "heart-rate-stat");
    globalThis.__canvasText = [];
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} hudConfig={hudConfig} />);
    });

    expect(globalThis.__canvasText).toContain("Heart rate");
    expect(globalThis.__canvasText).toContain("100");
    expect(globalThis.__canvasText).toContain("BPM");
    expect(globalThis.__canvasText).not.toContain("0.00 km");
  });

  it("draws initialHud as the portable React HUD config input", async () => {
    const initialHud = broadcastRunnerPreset();
    initialHud.widgets = [
      {
        id: "initial-only-stat",
        type: "stat_block",
        bindings: { value: "heart_rate_bpm" },
        anchor: "top-left",
        x: 20,
        y: 20,
        width: 180,
        height: 80,
        zIndex: 10,
        visible: true,
        style: { label: "Initial Only", unit: "BPM" },
      },
    ];
    globalThis.__canvasText = [];
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} initialHud={initialHud} />);
    });

    expect(globalThis.__canvasText).toContain("Initial Only");
    expect(globalThis.__canvasText).toContain("100");
    expect(globalThis.__canvasText).toContain("BPM");
  });

  it("notifies React callers when HUD config changes", async () => {
    const onHudChange = vi.fn();
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} onHudChange={onHudChange} />);
    });

    const showUnits = host.querySelector<HTMLInputElement>('input[aria-label="Show HUD units"]');
    expect(showUnits).not.toBeNull();
    expect(showUnits!.checked).toBe(true);

    await act(async () => {
      showUnits!.click();
    });

    expect(onHudChange).toHaveBeenCalledTimes(1);
    expect(onHudChange.mock.calls[0][0].theme.showUnits).toBe(false);
    expect(showUnits!.checked).toBe(false);
  });

  it("draws lap waterfall widgets from the current activity laps", async () => {
    const hudConfig = broadcastRunnerPreset();
    hudConfig.widgets = [
      {
        id: "lap-table",
        type: "lap_waterfall",
        bindings: { value: "laps" },
        anchor: "top-left",
        x: 20,
        y: 20,
        width: 360,
        height: 180,
        zIndex: 50,
        visible: true,
        style: { always_show: true, visible_rows: 2 },
      },
    ];
    const activity = twoSampleActivity();
    activity.laps = [
      {
        startTime: "2026-04-19T00:35:00.000Z",
        totalTimeSeconds: 300,
        distanceM: 1000,
        avgHeartRateBpm: 121,
        maxHeartRateBpm: 150,
        maxSpeedMps: 4,
        elevationDeltaM: 5,
        calories: 80,
      },
    ];
    globalThis.__canvasText = [];
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={activity} hudConfig={hudConfig} />);
    });

    expect(globalThis.__canvasText).toContain("Lap");
    expect(globalThis.__canvasText).toContain("1");
    expect(globalThis.__canvasText).toContain("1.00");
    expect(globalThis.__canvasText).toContain("+5");
  });

  it("draws route map from activity GPS samples", async () => {
    const hudConfig = broadcastRunnerPreset();
    hudConfig.widgets = hudConfig.widgets.filter((widget) => widget.id === "route-map");
    globalThis.__canvasLinePoints = [];
    globalThis.__canvasArcCenters = [];
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} hudConfig={hudConfig} />);
    });

    expect(globalThis.__canvasLinePoints.length).toBeGreaterThanOrEqual(2);
    expect(globalThis.__canvasArcCenters.length).toBeGreaterThanOrEqual(1);
  });

  it("loads a video and advances the HUD from video playback time", async () => {
    const activity = twoSampleActivity();
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={activity} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]');
    expect(videoInput).not.toBeNull();

    await act(async () => {
      changeFileInput(videoInput!, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    expect(host.querySelector("video")).not.toBeNull();
    expect(host.textContent).toContain("race.mp4");
    expect(host.textContent).toContain("2 samples");

    const video = host.querySelector("video")!;
    await act(async () => {
      video.currentTime = 5;
      video.dispatchEvent(new Event("timeupdate", { bubbles: true }));
    });

    expect(host.textContent).toContain("0.05 km");
    expect(host.textContent).toContain("110 bpm");
    expect(host.textContent).toContain("3.0 m/s");
  });

  it("loads provided activityFile and videoFile props without manual file input", async () => {
    const activityFile = new File([tcxXml()], "provided.tcx", { type: "application/xml" });
    const videoFile = new File(
      [asArrayBuffer(mp4WithMvhdCreationTime("2026-04-19T00:06:00.000Z"))],
      "provided.mp4",
      { type: "video/mp4" },
    );
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activityFile={activityFile} videoFile={videoFile} />);
    });
    await act(async () => {
      await flushAsyncWork();
    });

    expect(host.querySelector("video")).not.toBeNull();
    expect(host.textContent).toContain("provided.tcx · 2 samples");
    expect(host.textContent).toContain("provided.mp4 · 0.0s");
    expect(host.textContent).toContain("provided.mp4 · created 2026-04-19T00:06:00.000Z · browser-container");
  });

  it("reads browser video container metadata without a backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(
        videoInput,
        new File([asArrayBuffer(mp4WithMvhdCreationTime("2026-04-19T00:06:00.000Z"))], "browser-preview.mp4", {
          type: "video/mp4",
        }),
      );
      await flushAsyncWork();
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(host.textContent).toContain("browser-preview.mp4");
    expect(host.textContent).toContain("browser-preview.mp4 · created 2026-04-19T00:06:00.000Z · browser-container");
    expect(host.textContent).toContain("Browser metadata ready");
  });

  it("reports when video metadata needs an external API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["not an mp4"], "race.avi"));
      await flushAsyncWork();
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(host.textContent).toContain("Needs external metadata API");
    expect(host.textContent).toContain("No readable MP4/MOV creation_time");
  });

  it("uses an injected external metadata provider when browser metadata is not readable", async () => {
    const provider = vi.fn().mockResolvedValue({
      name: "race.avi",
      creationTime: "2026-04-19T00:06:00.000Z",
      source: "external-api",
    });
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(
        <RaceOverlay activity={twoSampleActivity()} externalVideoMetadataProvider={provider} />,
      );
    });

    const file = new File(["not an mp4"], "race.avi");
    await act(async () => {
      changeFileInput(host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!, file);
      await flushAsyncWork();
    });

    expect(provider).toHaveBeenCalledWith(file);
    expect(host.textContent).toContain("race.avi · created 2026-04-19T00:06:00.000Z · external-api");
    expect(host.textContent).toContain("External metadata ready");
  });

  it("does not expose backend video path controls", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    expect(host.textContent).not.toContain("Backend video path");
    expect(host.querySelector<HTMLInputElement>('input[aria-label="Backend video path"]')).toBeNull();
    expect(host.querySelector<HTMLButtonElement>('button[aria-label="Probe backend video metadata"]')).toBeNull();
  });

  it("applies TCX offset seconds while sampling from video time", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const offsetInput = host.querySelector<HTMLInputElement>('input[aria-label="TCX offset seconds"]');
    expect(offsetInput).not.toBeNull();

    await act(async () => {
      changeTextInput(offsetInput!, "5");
    });

    expect(host.textContent).toContain("0.05 km");
    expect(host.textContent).toContain("110 bpm");
  });

  it("clamps offset sampling to the TCX activity range", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const offsetInput = host.querySelector<HTMLInputElement>('input[aria-label="TCX offset seconds"]')!;
    await act(async () => {
      changeTextInput(offsetInput, "20");
    });

    expect(host.textContent).toContain("0.10 km");
    expect(host.textContent).toContain("120 bpm");
    expect(host.textContent).toContain("TCX range end");
  });

  it("nudges TCX offset with sync controls", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const offsetInput = host.querySelector<HTMLInputElement>('input[aria-label="TCX offset seconds"]')!;
    const nudgeForward = host.querySelector<HTMLButtonElement>('button[aria-label="Nudge TCX offset forward 0.5 seconds"]');
    const nudgeBackward = host.querySelector<HTMLButtonElement>('button[aria-label="Nudge TCX offset backward 0.5 seconds"]');
    expect(nudgeForward).not.toBeNull();
    expect(nudgeBackward).not.toBeNull();

    await act(async () => {
      nudgeForward!.click();
    });
    expect(offsetInput.value).toBe("0.5");

    await act(async () => {
      nudgeBackward!.click();
    });
    expect(offsetInput.value).toBe("0");
  });

  it("starts a browser WebM export from the composed preview", async () => {
    const activity = twoSampleActivity();
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={activity} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(
        videoInput,
        new File([asArrayBuffer(mp4WithMvhdCreationTime("2026-04-19T00:06:00.000Z"))], "race.mp4", {
          type: "video/mp4",
        }),
      );
      await flushAsyncWork();
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]');
    expect(exportButton?.textContent).toContain("Export WebM");

    globalThis.__canvasOperations = [];
    await act(async () => {
      exportButton!.click();
    });

    expect(host.textContent).toContain("Exporting WebM");
    const videoDrawIndex = globalThis.__canvasOperations.indexOf("drawImage");
    expect(videoDrawIndex).toBeGreaterThanOrEqual(0);
    expect(globalThis.__canvasOperations.slice(videoDrawIndex + 1, videoDrawIndex + 4)).not.toContain("clearRect");
    expect(globalThis.__lastRecorderTrackKinds).toEqual(["video", "audio"]);
  });

  it("starts source playback in the export click handler before recording", async () => {
    let recorderOptionsDuringPlay: MediaRecorderOptions | undefined;
    const playSpy = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementationOnce(() => {
      recorderOptionsDuringPlay = globalThis.__lastRecorderOptions;
      return Promise.resolve();
    });
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    globalThis.__lastRecorderOptions = undefined;
    await act(async () => {
      exportButton.click();
    });

    expect(playSpy).toHaveBeenCalledTimes(1);
    expect(recorderOptionsDuringPlay).toBeUndefined();
  });

  it("uses configurable export FPS and bitrate when recording WebM", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    expect(host.textContent).toContain("WebM VP9/Opus supported");

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(
        videoInput,
        new File([asArrayBuffer(mp4WithMvhdCreationTime("2026-04-19T00:06:00.000Z"))], "race.mp4", {
          type: "video/mp4",
        }),
      );
      await flushAsyncWork();
    });

    const fpsInput = host.querySelector<HTMLInputElement>('input[aria-label="Export FPS"]')!;
    const bitrateInput = host.querySelector<HTMLInputElement>('input[aria-label="Export bitrate Mbps"]')!;
    await act(async () => {
      changeTextInput(fpsInput, "24");
      changeTextInput(bitrateInput, "8");
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    await act(async () => {
      exportButton.click();
    });

    expect(globalThis.__lastRecorderOptions).toMatchObject({
      mimeType: "video/webm;codecs=vp9,opus",
      videoBitsPerSecond: 8000000,
    });
  });

  it("shows browser export capabilities for target-browser migration evidence", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const capabilities = host.querySelector('[aria-label="Browser export capabilities"]');
    expect(capabilities?.textContent).toContain("WebM yes");
    expect(capabilities?.textContent).toContain("MIME video/webm;codecs=vp9,opus");
    expect(capabilities?.textContent).toContain("canvas capture yes");
    expect(capabilities?.textContent).toContain("video capture pending");
    expect(capabilities?.textContent).toContain("source audio tracks unknown");

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
      await flushAsyncWork();
    });

    const video = host.querySelector("video")!;
    await act(async () => {
      video.dispatchEvent(new Event("loadedmetadata"));
    });

    expect(capabilities?.textContent).toContain("video capture yes");
    expect(capabilities?.textContent).toContain("source audio tracks 1");
    expect(capabilities?.textContent).toContain("memory measurement no");
  });

  it("downloads browser export capability evidence JSON", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
      await flushAsyncWork();
    });
    const video = host.querySelector("video")!;
    await act(async () => {
      video.dispatchEvent(new Event("loadedmetadata"));
    });

    const evidence = host.querySelector('[aria-label="Browser export capability evidence JSON"]');
    expect(evidence?.textContent).toContain('"status": "capabilities"');
    expect(evidence?.textContent).toContain('"videoName": "race.mp4"');
    expect(evidence?.textContent).toContain('"sourceAudioTrackCount": 1');

    const downloadButton = host.querySelector<HTMLButtonElement>(
      'button[aria-label="Download browser export capability evidence JSON"]',
    );
    expect(downloadButton).not.toBeNull();
    await act(async () => {
      downloadButton!.click();
    });

    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
  });

  it("uses configurable short export duration for browser WebM recordings", async () => {
    const onExportReport = vi.fn();
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} onExportReport={onExportReport} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    const durationInput = host.querySelector<HTMLInputElement>('input[aria-label="Export duration seconds"]')!;
    expect(durationInput.value).toBe("5");

    await act(async () => {
      changeTextInput(durationInput, "10");
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    const video = host.querySelector("video")!;
    await act(async () => {
      exportButton.click();
      await flushAsyncWork();
    });
    await act(async () => {
      video.dispatchEvent(new Event("ended"));
      await flushAsyncWork();
    });

    expect(onExportReport).toHaveBeenCalledTimes(1);
    expect(onExportReport.mock.calls[0][0]).toMatchObject({
      durationSeconds: 10,
      outputBytes: 4,
    });
  });

  it("notifies React callers when browser export completes", async () => {
    const onExportComplete = vi.fn();
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} onExportComplete={onExportComplete} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    const video = host.querySelector("video")!;
    await act(async () => {
      exportButton.click();
      await flushAsyncWork();
    });
    await act(async () => {
      video.dispatchEvent(new Event("ended"));
      await flushAsyncWork();
    });

    expect(onExportComplete).toHaveBeenCalledTimes(1);
    expect(onExportComplete.mock.calls[0][0]).toMatchObject({
      size: 4,
      type: "video/webm",
    });
  });

  it("notifies React callers about browser export progress", async () => {
    const onExportProgress = vi.fn();
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} onExportProgress={onExportProgress} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    await act(async () => {
      exportButton.click();
    });

    expect(onExportProgress).toHaveBeenCalledWith({
      currentTimeSeconds: 0,
      durationSeconds: 5,
      ratio: 0,
    });
  });

  it("notifies React callers about measured export reports at configured dimensions", async () => {
    const onExportReport = vi.fn();
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(
        <RaceOverlay
          activity={twoSampleActivity()}
          exportWidth={1280}
          exportHeight={720}
          onExportReport={onExportReport}
        />,
      );
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    const video = host.querySelector("video")!;
    await act(async () => {
      exportButton.click();
      await flushAsyncWork();
    });
    await act(async () => {
      video.dispatchEvent(new Event("ended"));
      await flushAsyncWork();
    });

    expect(onExportReport).toHaveBeenCalledTimes(1);
    expect(onExportReport.mock.calls[0][0]).toMatchObject({
      width: 1280,
      height: 720,
      outputBytes: 4,
      audioTrackCount: 1,
      mimeType: "video/webm;codecs=vp9,opus",
    });
    expect(host.textContent).toContain("Exported 4 bytes · 1280x720");
  });

  it("lets the demo UI collect 720p/1080p export measurement reports", async () => {
    const onExportReport = vi.fn();
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} onExportReport={onExportReport} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    const widthInput = host.querySelector<HTMLInputElement>('input[aria-label="Export width"]')!;
    const heightInput = host.querySelector<HTMLInputElement>('input[aria-label="Export height"]')!;
    expect(widthInput.value).toBe("960");
    expect(heightInput.value).toBe("540");

    await act(async () => {
      changeTextInput(widthInput, "1920");
      changeTextInput(heightInput, "1080");
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    const video = host.querySelector("video")!;
    await act(async () => {
      exportButton.click();
      await flushAsyncWork();
    });
    await act(async () => {
      video.dispatchEvent(new Event("ended"));
      await flushAsyncWork();
    });

    expect(onExportReport).toHaveBeenCalledWith(
      expect.objectContaining({
        width: 1920,
        height: 1080,
        durationSeconds: 5,
        outputBytes: 4,
      }),
    );
    expect(host.textContent).toContain("Measurement report");
    expect(host.textContent).toContain("1920x1080");
    expect(host.textContent).toContain("5s");
    expect(host.textContent).toContain("video/webm;codecs=vp9,opus");
    expect(host.textContent).toContain("audio tracks 1");
  });

  it("renders and downloads export measurement evidence JSON", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    const video = host.querySelector("video")!;
    await act(async () => {
      exportButton.click();
      await flushAsyncWork();
    });
    await act(async () => {
      video.dispatchEvent(new Event("ended"));
      await flushAsyncWork();
    });

    const evidenceJson = host.querySelector<HTMLElement>('[aria-label="Measurement evidence JSON"]');
    expect(evidenceJson).not.toBeNull();
    expect(evidenceJson!.textContent).toContain('"schemaVersion": 1');
    expect(evidenceJson!.textContent).toContain('"activityName": "Provided activity"');
    expect(evidenceJson!.textContent).toContain('"videoName": "race.mp4"');
    expect(evidenceJson!.textContent).toContain('"width": 960');

    const downloadButton = host.querySelector<HTMLButtonElement>('button[aria-label="Download measurement evidence JSON"]');
    expect(downloadButton).not.toBeNull();
    await act(async () => {
      downloadButton!.click();
    });

    const createObjectUrlMock = vi.mocked(URL.createObjectURL);
    const evidenceBlob = createObjectUrlMock.mock.calls.at(-1)?.[0];
    expect(evidenceBlob).toMatchObject({
      type: "application/json",
    });
  });

  it("shows an error instead of hanging when browser export cannot play the source video", async () => {
    vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockRejectedValueOnce(new Error("autoplay blocked"))
      .mockRejectedValueOnce(new Error("muted playback blocked"));
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(
        videoInput,
        new File([asArrayBuffer(mp4WithMvhdCreationTime("2026-04-19T00:06:00.000Z"))], "race.mp4", {
          type: "video/mp4",
        }),
      );
      await flushAsyncWork();
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    await act(async () => {
      exportButton.click();
      await flushAsyncWork();
    });
    await act(async () => {
      await flushAsyncWork();
    });

    expect(host.textContent).toContain("Unable to play source video for export: muted playback blocked");
    expect(host.textContent).not.toContain("Exporting WebM...");
    const failureJson = host.querySelector<HTMLElement>('[aria-label="Measurement failure evidence JSON"]');
    expect(failureJson).not.toBeNull();
    expect(failureJson!.textContent).toContain('"status": "failed"');
    expect(failureJson!.textContent).toContain(
      '"error": "Unable to play source video for export: muted playback blocked"',
    );
    expect(failureJson!.textContent).toContain('"width": 960');

    const downloadButton = host.querySelector<HTMLButtonElement>('button[aria-label="Download measurement failure JSON"]');
    expect(downloadButton).not.toBeNull();
    await act(async () => {
      downloadButton!.click();
    });
    const createObjectUrlMock = vi.mocked(URL.createObjectURL);
    const failureBlob = createObjectUrlMock.mock.calls.at(-1)?.[0];
    expect(failureBlob).toMatchObject({
      type: "application/json",
    });
  });

  it("exports with measurement evidence when muted playback fallback succeeds", async () => {
    const playSpy = vi
      .spyOn(HTMLMediaElement.prototype, "play")
      .mockRejectedValueOnce(new Error("autoplay blocked"))
      .mockResolvedValueOnce(undefined);
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(<RaceOverlay activity={twoSampleActivity()} />);
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    const video = host.querySelector("video")!;
    await act(async () => {
      exportButton.click();
      await flushAsyncWork();
    });
    await act(async () => {
      video.dispatchEvent(new Event("ended"));
      await flushAsyncWork();
    });

    expect(playSpy).toHaveBeenCalledTimes(2);
    expect(host.textContent).toContain("Measurement report");
    const evidenceJson = host.querySelector<HTMLElement>('[aria-label="Measurement evidence JSON"]');
    expect(evidenceJson).not.toBeNull();
    expect(evidenceJson!.textContent).toContain('"playbackMode": "muted-fallback"');
    expect(host.querySelector<HTMLElement>('[aria-label="Measurement failure evidence JSON"]')).toBeNull();
  });

  it("cancels an in-progress export without downloading and allows retry", async () => {
    const onExportComplete = vi.fn();
    const onExportReport = vi.fn();
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(
        <RaceOverlay
          activity={twoSampleActivity()}
          onExportComplete={onExportComplete}
          onExportReport={onExportReport}
        />,
      );
    });

    const videoInput = host.querySelector<HTMLInputElement>('input[aria-label="Video file"]')!;
    await act(async () => {
      changeFileInput(videoInput, new File(["video"], "race.mp4", { type: "video/mp4" }));
    });

    const exportButton = host.querySelector<HTMLButtonElement>('button[aria-label="Export WebM"]')!;
    await act(async () => {
      exportButton.click();
      await flushAsyncWork();
    });

    const cancelButton = host.querySelector<HTMLButtonElement>('button[aria-label="Cancel WebM export"]');
    expect(cancelButton).not.toBeNull();

    await act(async () => {
      cancelButton!.click();
      await flushAsyncWork();
    });

    expect(host.textContent).toContain("Export canceled");
    expect(onExportComplete).not.toHaveBeenCalled();
    expect(onExportReport).not.toHaveBeenCalled();
    expect(host.querySelector<HTMLElement>('[aria-label="Measurement evidence JSON"]')).toBeNull();

    const video = host.querySelector("video")!;
    await act(async () => {
      exportButton.click();
      await flushAsyncWork();
    });
    await act(async () => {
      video.dispatchEvent(new Event("ended"));
      await flushAsyncWork();
    });

    expect(onExportComplete).toHaveBeenCalledTimes(1);
    expect(onExportReport).toHaveBeenCalledTimes(1);
    expect(host.textContent).toContain("Measurement report");
  });
});
