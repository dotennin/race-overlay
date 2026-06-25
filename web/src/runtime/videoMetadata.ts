export type VideoMetadataSource = "browser-container" | "external-api";

export interface VideoMetadata {
  name: string;
  creationTime: string;
  source: VideoMetadataSource;
}

export interface VideoMetadataResult {
  metadata: VideoMetadata | null;
  needsExternalApi: boolean;
  reason: string | null;
}

const QUICKTIME_EPOCH_OFFSET_SECONDS = 2_082_844_800;
const DEFAULT_SCAN_BYTES = 16 * 1024 * 1024;

interface BoxHeader {
  type: string;
  start: number;
  headerSize: number;
  size: number;
}

function readAscii(view: DataView, offset: number, length: number): string {
  let value = "";
  for (let index = 0; index < length; index += 1) {
    value += String.fromCharCode(view.getUint8(offset + index));
  }
  return value;
}

function readBoxHeader(view: DataView, offset: number, end: number): BoxHeader | null {
  if (offset + 8 > end) {
    return null;
  }
  const smallSize = view.getUint32(offset);
  const type = readAscii(view, offset + 4, 4);
  if (smallSize === 0) {
    return { type, start: offset, headerSize: 8, size: end - offset };
  }
  if (smallSize === 1) {
    if (offset + 16 > end) {
      return null;
    }
    const largeSize = Number(view.getBigUint64(offset + 8));
    return { type, start: offset, headerSize: 16, size: largeSize };
  }
  return { type, start: offset, headerSize: 8, size: smallSize };
}

function* walkBoxes(view: DataView, start: number, end: number): Generator<BoxHeader> {
  let offset = start;
  while (offset + 8 <= end) {
    const box = readBoxHeader(view, offset, end);
    if (!box || box.size < box.headerSize) {
      return;
    }
    const boxEnd = box.start + box.size;
    if (boxEnd > end) {
      return;
    }
    yield box;
    offset = boxEnd;
  }
}

function quickTimeSecondsToIso(seconds: bigint): string | null {
  const unixSeconds = seconds - BigInt(QUICKTIME_EPOCH_OFFSET_SECONDS);
  if (unixSeconds <= 0n) {
    return null;
  }
  return new Date(Number(unixSeconds) * 1000).toISOString();
}

function parseMvhdCreationTime(view: DataView, box: BoxHeader): string | null {
  const payloadStart = box.start + box.headerSize;
  const payloadEnd = box.start + box.size;
  if (payloadStart + 4 > payloadEnd) {
    return null;
  }
  const version = view.getUint8(payloadStart);
  if (version === 1) {
    if (payloadStart + 12 > payloadEnd) {
      return null;
    }
    return quickTimeSecondsToIso(view.getBigUint64(payloadStart + 4));
  }
  if (version === 0) {
    if (payloadStart + 8 > payloadEnd) {
      return null;
    }
    return quickTimeSecondsToIso(BigInt(view.getUint32(payloadStart + 4)));
  }
  return null;
}

function parseIsoBmffCreationTime(buffer: ArrayBuffer): string | null {
  const view = new DataView(buffer);
  for (const topLevelBox of walkBoxes(view, 0, view.byteLength)) {
    if (topLevelBox.type !== "moov") {
      continue;
    }
    const moovStart = topLevelBox.start + topLevelBox.headerSize;
    const moovEnd = topLevelBox.start + topLevelBox.size;
    for (const moovBox of walkBoxes(view, moovStart, moovEnd)) {
      if (moovBox.type === "mvhd") {
        return parseMvhdCreationTime(view, moovBox);
      }
    }
  }
  return null;
}

async function blobToArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === "function") {
    return blob.arrayBuffer();
  }
  return new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(reader.result as ArrayBuffer), { once: true });
    reader.addEventListener("error", () => reject(reader.error ?? new Error("unable to read video metadata")), {
      once: true,
    });
    reader.readAsArrayBuffer(blob);
  });
}

export async function readBrowserVideoMetadata(file: File, scanBytes = DEFAULT_SCAN_BYTES): Promise<VideoMetadataResult> {
  const head = file.slice(0, Math.min(file.size, scanBytes));
  const creationTime = parseIsoBmffCreationTime(await blobToArrayBuffer(head));
  if (!creationTime) {
    return {
      metadata: null,
      needsExternalApi: true,
      reason: "No readable MP4/MOV creation_time was found in the browser-scanned container metadata",
    };
  }
  return {
    metadata: {
      name: file.name,
      creationTime,
      source: "browser-container",
    },
    needsExternalApi: false,
    reason: null,
  };
}
