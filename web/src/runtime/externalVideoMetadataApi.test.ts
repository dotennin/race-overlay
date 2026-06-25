import { describe, expect, it, vi } from "vitest";

import { createExternalVideoMetadataProvider } from "./externalVideoMetadataApi";

function responseJson(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function uploadedVideo(call: unknown[]): File {
  const init = call[1] as RequestInit;
  const body = init.body as FormData;
  return body.get("video") as File;
}

function uploadMode(call: unknown[]): string {
  const init = call[1] as RequestInit;
  const body = init.body as FormData;
  return String(body.get("mode"));
}

describe("createExternalVideoMetadataProvider", () => {
  it("uploads only the video head when the external API can read partial metadata", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      responseJson({
        metadata: {
          name: "race.mov",
          creationTime: "2026-04-19T00:06:00.000Z",
          source: "external-api",
        },
      }),
    );
    const provider = createExternalVideoMetadataProvider({
      endpoint: "https://metadata.example/probe",
      initialBytes: 4,
      fetchImpl,
    });

    const metadata = await provider(new File(["abcdefghij"], "race.mov", { type: "video/quicktime" }));

    expect(metadata).toEqual({
      name: "race.mov",
      creationTime: "2026-04-19T00:06:00.000Z",
      source: "external-api",
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl.mock.calls[0][0]).toBe("https://metadata.example/probe");
    expect(uploadedVideo(fetchImpl.mock.calls[0]).size).toBe(4);
    expect(uploadMode(fetchImpl.mock.calls[0])).toBe("partial");
  });

  it("falls back to a full upload only when the external API requests it", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(responseJson({ metadata: null, needsFullUpload: true }))
      .mockResolvedValueOnce(
        responseJson({
          metadata: {
            name: "race.avi",
            creationTime: "2026-04-19T00:06:00.000Z",
            source: "external-api",
          },
        }),
      );
    const provider = createExternalVideoMetadataProvider({
      endpoint: "https://metadata.example/probe",
      initialBytes: 4,
      fetchImpl,
    });

    const metadata = await provider(new File(["abcdefghij"], "race.avi", { type: "video/x-msvideo" }));

    expect(metadata?.creationTime).toBe("2026-04-19T00:06:00.000Z");
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(uploadedVideo(fetchImpl.mock.calls[0]).size).toBe(4);
    expect(uploadMode(fetchImpl.mock.calls[0])).toBe("partial");
    expect(uploadedVideo(fetchImpl.mock.calls[1]).size).toBe(10);
    expect(uploadMode(fetchImpl.mock.calls[1])).toBe("full");
  });

  it("returns null without full upload when partial metadata is unavailable but not requested", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(responseJson({ metadata: null }));
    const provider = createExternalVideoMetadataProvider({
      endpoint: "https://metadata.example/probe",
      initialBytes: 4,
      fetchImpl,
    });

    const metadata = await provider(new File(["abcdefghij"], "race.mkv"));

    expect(metadata).toBeNull();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
