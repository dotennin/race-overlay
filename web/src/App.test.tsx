import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { App } from "./App";

async function flushAsyncWork(): Promise<void> {
  for (let index = 0; index < 10; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await Promise.resolve();
  }
}

describe("App", () => {
  it("loads browser-generated sample inputs for export measurement", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    await act(async () => {
      createRoot(host).render(
        <App sampleVideoOptions={{ durationSeconds: 0.01, fps: 5, width: 160, height: 90 }} />,
      );
    });

    const sampleButton = host.querySelector<HTMLButtonElement>('button[aria-label="Load sample measurement inputs"]');
    expect(sampleButton).not.toBeNull();

    await act(async () => {
      sampleButton!.click();
      await flushAsyncWork();
    });
    await act(async () => {
      await flushAsyncWork();
    });

    expect(host.textContent).toContain("Sample measurement inputs ready");
    expect(host.textContent).toContain("sample-measurement.tcx");
    expect(host.textContent).toContain("sample-measurement.webm");
  });
});
