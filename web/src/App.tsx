import React, { useState } from "react";

import { RaceOverlay } from "./components/RaceOverlay";
import {
  createSampleTcxFile,
  createSyntheticMeasurementVideoFile,
  type SyntheticMeasurementVideoOptions,
} from "./demo/sampleInputs";

export interface AppProps {
  sampleVideoOptions?: SyntheticMeasurementVideoOptions;
}

export function App({ sampleVideoOptions }: AppProps): React.ReactElement {
  const [activityFile, setActivityFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [sampleStatus, setSampleStatus] = useState("");
  const [sampleError, setSampleError] = useState("");

  async function loadSampleInputs(): Promise<void> {
    try {
      setSampleError("");
      setSampleStatus("Generating sample measurement inputs...");
      setActivityFile(createSampleTcxFile());
      setVideoFile(await createSyntheticMeasurementVideoFile(sampleVideoOptions));
      setSampleStatus("Sample measurement inputs ready");
    } catch (caught) {
      setSampleStatus("");
      setSampleError(caught instanceof Error ? caught.message : "Unable to generate sample measurement inputs");
    }
  }

  return (
    <>
      <div className="race-overlay__demo-tools">
        <button
          aria-label="Load sample measurement inputs"
          className="race-overlay__button"
          type="button"
          onClick={() => {
            void loadSampleInputs();
          }}
        >
          Load sample measurement inputs
        </button>
        {sampleStatus ? <p className="race-overlay__status">{sampleStatus}</p> : null}
        {sampleError ? <p className="race-overlay__error">{sampleError}</p> : null}
      </div>
      <RaceOverlay activityFile={activityFile} videoFile={videoFile} />
    </>
  );
}
