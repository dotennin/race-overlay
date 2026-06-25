import { vi } from "vitest";

declare global {
  // React uses this flag to suppress act() environment warnings in custom test setups.
  var IS_REACT_ACT_ENVIRONMENT: boolean;
  var __canvasOperations: string[];
  var __canvasText: string[];
  var __canvasLinePoints: Array<[number, number]>;
  var __canvasArcCenters: Array<[number, number]>;
  var __lastRecorderTrackKinds: string[];
  var __lastRecorderOptions: MediaRecorderOptions | undefined;
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.__canvasOperations = [];
globalThis.__canvasText = [];
globalThis.__canvasLinePoints = [];
globalThis.__canvasArcCenters = [];
globalThis.__lastRecorderTrackKinds = [];
globalThis.__lastRecorderOptions = undefined;

class TestMediaStreamTrack {
  constructor(public kind: string) {}
}

class TestMediaStream {
  private readonly tracks: TestMediaStreamTrack[];

  constructor(tracks: TestMediaStreamTrack[] = []) {
    this.tracks = [...tracks];
  }

  addTrack(track: TestMediaStreamTrack): void {
    this.tracks.push(track);
  }

  getAudioTracks(): TestMediaStreamTrack[] {
    return this.tracks.filter((track) => track.kind === "audio");
  }

  getTracks(): TestMediaStreamTrack[] {
    return [...this.tracks];
  }
}

Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  value: vi.fn(() => ({
    clearRect: vi.fn(() => globalThis.__canvasOperations.push("clearRect")),
    fillRect: vi.fn(() => globalThis.__canvasOperations.push("fillRect")),
    drawImage: vi.fn(() => globalThis.__canvasOperations.push("drawImage")),
    strokeRect: vi.fn(() => globalThis.__canvasOperations.push("strokeRect")),
    fillText: vi.fn((text: string) => {
      globalThis.__canvasOperations.push("fillText");
      globalThis.__canvasText.push(String(text));
    }),
    beginPath: vi.fn(),
    moveTo: vi.fn((x: number, y: number) => globalThis.__canvasLinePoints.push([x, y])),
    lineTo: vi.fn((x: number, y: number) => globalThis.__canvasLinePoints.push([x, y])),
    stroke: vi.fn(() => globalThis.__canvasOperations.push("stroke")),
    fill: vi.fn(() => globalThis.__canvasOperations.push("fill")),
    arc: vi.fn((x: number, y: number) => globalThis.__canvasArcCenters.push([x, y])),
    save: vi.fn(),
    restore: vi.fn(),
    set fillStyle(_value: string) {},
    set strokeStyle(_value: string) {},
    set lineWidth(_value: number) {},
    set font(_value: string) {},
  })),
});

Object.defineProperty(HTMLCanvasElement.prototype, "captureStream", {
  configurable: true,
  value: vi.fn(() => new TestMediaStream([new TestMediaStreamTrack("video")]) as unknown as MediaStream),
});

Object.defineProperty(HTMLMediaElement.prototype, "play", {
  configurable: true,
  value: vi.fn(() => Promise.resolve()),
});

Object.defineProperty(HTMLMediaElement.prototype, "captureStream", {
  configurable: true,
  value: vi.fn(() => new TestMediaStream([new TestMediaStreamTrack("audio")]) as unknown as MediaStream),
});

Object.defineProperty(URL, "createObjectURL", {
  configurable: true,
  value: vi.fn((file: File) => `blob:test/${file.name}`),
});

Object.defineProperty(URL, "revokeObjectURL", {
  configurable: true,
  value: vi.fn(),
});

Object.defineProperty(HTMLAnchorElement.prototype, "click", {
  configurable: true,
  value: vi.fn(),
});

class TestMediaRecorder extends EventTarget {
  state: RecordingState = "inactive";

  constructor(
    public stream: MediaStream,
    public options?: MediaRecorderOptions,
  ) {
    super();
    globalThis.__lastRecorderTrackKinds =
      "getTracks" in stream ? stream.getTracks().map((track) => track.kind) : [];
    globalThis.__lastRecorderOptions = options;
  }

  start(): void {
    this.state = "recording";
  }

  stop(): void {
    this.state = "inactive";
    const dataEvent = new Event("dataavailable") as Event & { data: Blob };
    dataEvent.data = new Blob(["webm"], { type: "video/webm" });
    this.dispatchEvent(dataEvent);
    this.dispatchEvent(new Event("stop"));
  }
}

Object.defineProperty(globalThis, "MediaRecorder", {
  configurable: true,
  value: Object.assign(TestMediaRecorder, {
    isTypeSupported: vi.fn((mimeType: string) => mimeType === "video/webm;codecs=vp9,opus"),
  }),
});
