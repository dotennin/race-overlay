import { afterEach, describe, expect, it, vi } from "vitest";

import { createSampleTcxFile, createSyntheticMeasurementVideoFile } from "./sampleInputs";

const originalAudioContext = window.AudioContext;

function readFileText(file: File): Promise<string> {
  if (typeof file.text === "function") {
    return file.text();
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Unable to read file"));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsText(file);
  });
}

describe("demo measurement sample inputs", () => {
  afterEach(() => {
    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      value: originalAudioContext,
    });
  });

  it("creates a portable TCX sample file", async () => {
    const file = createSampleTcxFile();

    expect(file.name).toBe("sample-measurement.tcx");
    expect(file.type).toBe("application/xml");
    await expect(readFileText(file)).resolves.toContain("<TrainingCenterDatabase");
  });

  it("creates a browser-generated WebM sample video file", async () => {
    const file = await createSyntheticMeasurementVideoFile({
      durationSeconds: 0.01,
      fps: 5,
      width: 160,
      height: 90,
    });

    expect(file.name).toBe("sample-measurement.webm");
    expect(file.type).toBe("video/webm");
    expect(file.size).toBeGreaterThan(0);
  });

  it("mixes a generated audio track into the sample video when requested and Web Audio is available", async () => {
    const close = vi.fn(() => Promise.resolve());
    const disconnect = vi.fn();
    const audioTrack = { kind: "audio" } as MediaStreamTrack;
    class TestAudioContext {
      currentTime = 0;
      close = close;
      resume = vi.fn(() => Promise.resolve());

      createOscillator(): OscillatorNode {
        return {
          frequency: { value: 0 },
          connect: vi.fn(),
          disconnect,
          start: vi.fn(),
          stop: vi.fn(),
        } as unknown as OscillatorNode;
      }

      createGain(): GainNode {
        return {
          gain: { value: 0 },
          connect: vi.fn(),
          disconnect,
        } as unknown as GainNode;
      }

      createMediaStreamDestination(): MediaStreamAudioDestinationNode {
        return {
          stream: {
            getAudioTracks: () => [audioTrack],
          },
        } as unknown as MediaStreamAudioDestinationNode;
      }
    }

    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      value: TestAudioContext,
    });

    await createSyntheticMeasurementVideoFile({
      durationSeconds: 0.01,
      fps: 5,
      includeAudio: true,
      width: 160,
      height: 90,
    });

    expect(globalThis.__lastRecorderTrackKinds).toEqual(["video", "audio"]);
    expect(globalThis.__lastRecorderOptions).toMatchObject({
      mimeType: "video/webm;codecs=vp9,opus",
    });
    expect(close).toHaveBeenCalledTimes(1);
  });
});
