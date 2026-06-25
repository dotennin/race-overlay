import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("evidence matrix template", () => {
  it("captures the final browser migration gate shape", () => {
    const template = JSON.parse(
      readFileSync(resolve(__dirname, "../examples/evidence-matrix.template.json"), "utf8"),
    ) as {
      requiredTargets: string[];
      requiredExports: Array<{ width: number; height: number; durationSeconds: number }>;
      targets: Array<{ name: string; capabilities: string; measurements: string[] }>;
    };

    expect(template.requiredTargets).toEqual(["chromium", "firefox", "safari", "production-device"]);
    expect(template.requiredExports).toEqual([
      { width: 1280, height: 720, durationSeconds: 5 },
      { width: 1920, height: 1080, durationSeconds: 5 },
      { width: 1920, height: 1080, durationSeconds: 60 },
    ]);
    for (const targetName of template.requiredTargets) {
      const target = template.targets.find((item) => item.name === targetName);
      expect(target?.capabilities).toContain(`${targetName}/capabilities.json`);
      expect(target?.measurements).toHaveLength(3);
    }
  });
});
