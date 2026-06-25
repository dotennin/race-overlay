import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(".");

function* sourceFiles(directory: string): Generator<string> {
  for (const entry of readdirSync(directory)) {
    if (entry === "node_modules" || entry === "dist") {
      continue;
    }
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      yield* sourceFiles(path);
      continue;
    }
    if (/\.(test|spec)\.(ts|tsx)$/.test(entry)) {
      continue;
    }
    if (/\.(ts|tsx|json)$/.test(entry)) {
      yield path;
    }
  }
}

describe("browser portability boundary", () => {
  it("does not depend on the Python video probe backend", () => {
    const bannedRuntimeTerms = [
      "videoProbeApi",
      "Backend video path",
      "VITE_VIDEO_PROBE",
      "/api/video",
      "backendVideo",
      "uploadVideo",
    ];
    const matches: string[] = [];

    for (const file of sourceFiles(WEB_ROOT)) {
      const text = readFileSync(file, "utf8");
      for (const term of bannedRuntimeTerms) {
        if (text.includes(term)) {
          matches.push(`${relative(WEB_ROOT, file)} contains ${term}`);
        }
      }
    }

    expect(matches).toEqual([]);
  });
});
