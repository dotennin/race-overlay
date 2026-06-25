import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("web package build artifacts", () => {
  it("emits the library JavaScript and type declaration entrypoints", () => {
    const root = resolve(__dirname, "..");
    const esmEntry = resolve(root, "dist/lib/race-overlay-web.js");
    const umdEntry = resolve(root, "dist/lib/race-overlay-web.umd.cjs");
    const typesEntry = resolve(root, "dist/types/index.d.ts");
    const cliEntry = resolve(root, "scripts/evaluate-portability-evidence.mjs");
    const hostExample = resolve(root, "examples/host-integration.tsx");
    const scaffoldEntry = resolve(root, "scripts/scaffold-portability-evidence.mjs");
    const consumerVerifyEntry = resolve(root, "scripts/verify-package-consumer.mjs");
    const verifyEntry = resolve(root, "scripts/verify-portability.mjs");

    expect(existsSync(esmEntry)).toBe(true);
    expect(existsSync(umdEntry)).toBe(true);
    expect(existsSync(typesEntry)).toBe(true);
    expect(existsSync(cliEntry)).toBe(true);
    expect(existsSync(hostExample)).toBe(true);
    expect(existsSync(scaffoldEntry)).toBe(true);
    expect(existsSync(consumerVerifyEntry)).toBe(true);
    expect(existsSync(verifyEntry)).toBe(true);
    expect(readFileSync(typesEntry, "utf8")).toContain("RaceOverlay");
    expect(readFileSync(cliEntry, "utf8")).toContain("evaluateBrowserPortabilityEvidence");
    expect(readFileSync(cliEntry, "utf8")).toContain("evaluateBrowserPortabilityEvidenceMatrix");
    expect(readFileSync(cliEntry, "utf8")).toContain("--manifest");
    expect(readFileSync(cliEntry, "utf8")).toContain("requiredTargets");
    expect(readFileSync(cliEntry, "utf8")).toContain("requiredExports");
    expect(readFileSync(cliEntry, "utf8")).toContain("dist/lib/race-overlay-web.js");
    expect(readFileSync(hostExample, "utf8")).toContain('from "race-overlay-web"');
    expect(readFileSync(hostExample, "utf8")).toContain('import "race-overlay-web/styles.css"');
    expect(readFileSync(hostExample, "utf8")).toContain("serializeBrowserWebmExportReport");
    expect(readFileSync(scaffoldEntry, "utf8")).toContain("Release Evidence");
    expect(readFileSync(scaffoldEntry, "utf8")).toContain("durationSeconds: 60");
    expect(readFileSync(consumerVerifyEntry, "utf8")).toContain("consumer smoke ok");
    expect(readFileSync(consumerVerifyEntry, "utf8")).toContain("race-overlay-web/styles.css");
    expect(readFileSync(consumerVerifyEntry, "utf8")).toContain("examples/host-integration.tsx");
    expect(readFileSync(verifyEntry, "utf8")).toContain("final release matrix No-Go check");
    expect(readFileSync(verifyEntry, "utf8")).toContain("host integration example typecheck");
    expect(readFileSync(verifyEntry, "utf8")).toContain("packed package consumer smoke");
    expect(readFileSync(verifyEntry, "utf8")).toContain("release evidence scaffold");
    expect(readFileSync(verifyEntry, "utf8")).toContain("npm_config_cache");
  });
});
