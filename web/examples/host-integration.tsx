/// <reference types="vite/client" />

import { useMemo, useState } from "react";
import {
  RaceOverlay,
  createExternalVideoMetadataProvider,
  serializeBrowserWebmExportReport,
  type BrowserWebmExportReport,
} from "race-overlay-web";
import "race-overlay-web/styles.css";

export interface HostOverlayEditorProps {
  metadataEndpoint: string;
  onEvidenceJson?: (json: string) => void;
  onExportBlob?: (blob: Blob) => void;
}

export function HostOverlayEditor({
  metadataEndpoint,
  onEvidenceJson,
  onExportBlob,
}: HostOverlayEditorProps): React.ReactElement {
  const [activityFile, setActivityFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const metadataProvider = useMemo(
    () =>
      createExternalVideoMetadataProvider({
        endpoint: metadataEndpoint,
        initialBytes: 16 * 1024 * 1024,
      }),
    [metadataEndpoint],
  );

  function handleExportReport(report: BrowserWebmExportReport) {
    onEvidenceJson?.(
      serializeBrowserWebmExportReport(report, {
        activityName: activityFile?.name,
        videoName: videoFile?.name,
      }),
    );
  }

  return (
    <section aria-label="Race overlay host integration">
      <label>
        TCX activity
        <input
          type="file"
          accept=".tcx,application/xml,text/xml"
          onChange={(event) => setActivityFile(event.currentTarget.files?.[0] ?? null)}
        />
      </label>
      <label>
        Source video
        <input
          type="file"
          accept="video/*"
          onChange={(event) => setVideoFile(event.currentTarget.files?.[0] ?? null)}
        />
      </label>
      <RaceOverlay
        activityFile={activityFile}
        videoFile={videoFile}
        externalVideoMetadataProvider={metadataProvider}
        exportWidth={1920}
        exportHeight={1080}
        exportDurationSeconds={5}
        onExportReport={handleExportReport}
        onExportComplete={onExportBlob}
      />
    </section>
  );
}
