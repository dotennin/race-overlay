export interface SyntheticMeasurementVideoOptions {
  durationSeconds?: number;
  fps?: number;
  includeAudio?: boolean;
  width?: number;
  height?: number;
}

export function createSampleTcxFile(): File {
  return new File([sampleTcxXml()], "sample-measurement.tcx", { type: "application/xml" });
}

export function createSyntheticMeasurementVideoFile({
  durationSeconds = 6,
  fps = 30,
  includeAudio = false,
  width = 640,
  height = 360,
}: SyntheticMeasurementVideoOptions = {}): Promise<File> {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  const captureStream = canvas.captureStream;
  if (!context || typeof captureStream !== "function" || typeof MediaRecorder === "undefined") {
    return Promise.reject(new Error("This browser cannot generate a sample measurement video"));
  }

  const stream = captureStream.call(canvas, fps);
  const sampleAudio = includeAudio ? createSampleAudioTrack(durationSeconds) : null;
  if (sampleAudio?.track) {
    stream.addTrack(sampleAudio.track);
  }
  const chunks: Blob[] = [];
  const recorder = new MediaRecorder(stream, { mimeType: supportedSampleVideoMimeType() });
  const startedAt = performance.now();
  const frameIntervalMs = 1000 / fps;
  let frameTimer = 0;

  return new Promise((resolve) => {
    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) {
        chunks.push(event.data);
      }
    });
    recorder.addEventListener(
      "stop",
      () => {
        window.clearInterval(frameTimer);
        sampleAudio?.cleanup();
        const blob = new Blob(chunks, { type: "video/webm" });
        resolve(new File([blob], "sample-measurement.webm", { type: "video/webm" }));
      },
      { once: true },
    );

    const drawFrame = () => {
      const elapsedSeconds = (performance.now() - startedAt) / 1000;
      const progress = Math.min(elapsedSeconds / durationSeconds, 1);
      context.fillStyle = "#101820";
      context.fillRect(0, 0, width, height);
      context.fillStyle = "#2dd4bf";
      context.fillRect(0, height * 0.68, width * progress, height * 0.08);
      context.fillStyle = "#f8fafc";
      context.font = `${Math.max(18, Math.round(width / 26))}px sans-serif`;
      context.fillText(`Race Overlay Sample ${elapsedSeconds.toFixed(1)}s`, width * 0.08, height * 0.22);
      context.fillStyle = "#f97316";
      context.fillRect(width * (0.08 + 0.72 * progress), height * 0.42, width * 0.08, height * 0.14);
    };

    recorder.start();
    drawFrame();
    frameTimer = window.setInterval(drawFrame, frameIntervalMs);
    window.setTimeout(() => {
      if (recorder.state !== "inactive") {
        recorder.stop();
      }
    }, Math.max(1, durationSeconds * 1000));
  });
}

interface SampleAudioTrack {
  track: MediaStreamTrack | null;
  cleanup: () => void;
}

function createSampleAudioTrack(durationSeconds: number): SampleAudioTrack {
  const AudioContextConstructor =
    window.AudioContext ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextConstructor) {
    return { track: null, cleanup: () => undefined };
  }

  const audioContext = new AudioContextConstructor();
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  const destination = audioContext.createMediaStreamDestination();

  oscillator.frequency.value = 440;
  gain.gain.value = 0.025;
  oscillator.connect(gain);
  gain.connect(destination);
  oscillator.start();
  oscillator.stop(audioContext.currentTime + Math.max(0.1, durationSeconds));
  void audioContext.resume?.();

  return {
    track: destination.stream.getAudioTracks()[0] ?? null,
    cleanup: () => {
      oscillator.disconnect();
      gain.disconnect();
      void audioContext.close();
    },
  };
}

function supportedSampleVideoMimeType(): string {
  const preferredMimeType = "video/webm;codecs=vp9,opus";
  if (typeof MediaRecorder.isTypeSupported === "function" && MediaRecorder.isTypeSupported(preferredMimeType)) {
    return preferredMimeType;
  }
  return "video/webm";
}

function sampleTcxXml(): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap StartTime="2026-04-19T00:45:00Z">
        <TotalTimeSeconds>10</TotalTimeSeconds>
        <DistanceMeters>100</DistanceMeters>
        <Track>
          <Trackpoint>
            <Time>2026-04-19T00:45:00Z</Time>
            <Position><LatitudeDegrees>36</LatitudeDegrees><LongitudeDegrees>140</LongitudeDegrees></Position>
            <AltitudeMeters>0</AltitudeMeters>
            <DistanceMeters>0</DistanceMeters>
            <HeartRateBpm><Value>100</Value></HeartRateBpm>
            <Cadence>85</Cadence>
          </Trackpoint>
          <Trackpoint>
            <Time>2026-04-19T00:45:10Z</Time>
            <Position><LatitudeDegrees>36.001</LatitudeDegrees><LongitudeDegrees>140.001</LongitudeDegrees></Position>
            <AltitudeMeters>5</AltitudeMeters>
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
