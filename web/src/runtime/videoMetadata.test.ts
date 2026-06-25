import { describe, expect, it } from "vitest";

import { readBrowserVideoMetadata } from "./videoMetadata";

const QUICKTIME_EPOCH_OFFSET_SECONDS = 2_082_844_800;

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

describe("readBrowserVideoMetadata", () => {
  it("reads MP4 mvhd creation_time in the browser", async () => {
    const metadata = await readBrowserVideoMetadata(
      new File([asArrayBuffer(mp4WithMvhdCreationTime("2026-04-19T00:06:00.000Z"))], "clip.mp4", {
        type: "video/mp4",
      }),
    );

    expect(metadata).toEqual({
      metadata: {
        name: "clip.mp4",
        creationTime: "2026-04-19T00:06:00.000Z",
        source: "browser-container",
      },
      needsExternalApi: false,
      reason: null,
    });
  });

  it("reports when browser container metadata is not readable", async () => {
    const metadata = await readBrowserVideoMetadata(new File(["not a supported container"], "clip.avi"));

    expect(metadata.metadata).toBeNull();
    expect(metadata.needsExternalApi).toBe(true);
    expect(metadata.reason).toContain("No readable MP4/MOV creation_time");
  });
});
