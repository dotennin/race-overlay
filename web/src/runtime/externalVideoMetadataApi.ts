import type { VideoMetadata } from "./videoMetadata";

export interface ExternalVideoMetadataApiResponse {
  metadata: VideoMetadata | null;
  needsFullUpload?: boolean;
  reason?: string | null;
}

export interface ExternalVideoMetadataProviderOptions {
  endpoint: string;
  initialBytes?: number;
  fetchImpl?: typeof fetch;
}

const DEFAULT_INITIAL_BYTES = 16 * 1024 * 1024;

function videoUploadFile(file: File, mode: "partial" | "full", initialBytes: number): File {
  if (mode === "full") {
    return file;
  }
  return new File([file.slice(0, Math.min(file.size, initialBytes))], file.name, { type: file.type });
}

async function requestMetadata(
  options: Required<ExternalVideoMetadataProviderOptions>,
  file: File,
  mode: "partial" | "full",
): Promise<ExternalVideoMetadataApiResponse> {
  const body = new FormData();
  body.set("video", videoUploadFile(file, mode, options.initialBytes), file.name);
  body.set("mode", mode);
  body.set("filename", file.name);
  body.set("size", String(file.size));
  body.set("contentType", file.type);

  const response = await options.fetchImpl(options.endpoint, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    throw new Error(`external video metadata API failed with HTTP ${response.status}`);
  }
  return (await response.json()) as ExternalVideoMetadataApiResponse;
}

function normalizeExternalMetadata(metadata: VideoMetadata | null | undefined): VideoMetadata | null {
  if (!metadata) {
    return null;
  }
  return {
    ...metadata,
    source: "external-api",
  };
}

export function createExternalVideoMetadataProvider({
  endpoint,
  initialBytes = DEFAULT_INITIAL_BYTES,
  fetchImpl = fetch,
}: ExternalVideoMetadataProviderOptions): (file: File) => Promise<VideoMetadata | null> {
  const options: Required<ExternalVideoMetadataProviderOptions> = { endpoint, initialBytes, fetchImpl };
  return async (file: File) => {
    const partial = await requestMetadata(options, file, "partial");
    const partialMetadata = normalizeExternalMetadata(partial.metadata);
    if (partialMetadata) {
      return partialMetadata;
    }
    if (!partial.needsFullUpload) {
      return null;
    }
    const full = await requestMetadata(options, file, "full");
    return normalizeExternalMetadata(full.metadata);
  };
}
