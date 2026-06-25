#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = fileURLToPath(new URL(".", import.meta.url));
const packageRoot = resolve(scriptDir, "..");
const node = process.execPath;

function usage() {
  return [
    "Usage:",
    "  npm run verify:portability",
    "",
    "Runs the current portable package gate:",
    "  1. web unit tests",
    "  2. production build",
    "  3. host integration example typecheck",
    "  4. packed package consumer smoke",
    "  5. npm pack dry-run",
    "  6. release evidence scaffold smoke test",
    "  7. current in-app-browser evidence gate",
    "  8. final release matrix No-Go check",
  ].join("\n");
}

function runStep({ name, command, args, expectedStatus = 0, env = {} }) {
  console.log(`\n[portability] ${name}`);
  const result = spawnSync(command, args, {
    cwd: packageRoot,
    encoding: "utf8",
    env: { ...process.env, ...env },
  });
  if (result.stdout) {
    process.stdout.write(result.stdout);
  }
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }
  if (result.status !== expectedStatus) {
    throw new Error(`${name} exited ${result.status}; expected ${expectedStatus}`);
  }
  return result.stdout;
}

function parseTrailingJson(output, label) {
  const start = output.lastIndexOf("\n{");
  const jsonText = start >= 0 ? output.slice(start + 1) : output.trim();
  try {
    return JSON.parse(jsonText);
  } catch (error) {
    throw new Error(`${label} did not emit parseable JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function assertCurrentEvidencePasses(output) {
  const result = parseTrailingJson(output, "current evidence gate");
  if (result.status !== "go" || result.ready !== true) {
    throw new Error("current in-app-browser evidence gate must be Go");
  }
}

function assertReleaseMatrixStillBlocksMissingEvidence(output) {
  const result = parseTrailingJson(output, "release matrix gate");
  if (result.status !== "no-go" || result.ready !== false) {
    throw new Error("release matrix gate must remain No-Go until all required target evidence is collected");
  }
  const blockers = Array.isArray(result.blockers) ? result.blockers : [];
  for (const requiredBlocker of [
    "chromium: Missing target evidence entry",
    "firefox: Missing target evidence entry",
    "in-app-browser: Missing successful 1920x1080 60s export evidence",
  ]) {
    if (!blockers.includes(requiredBlocker)) {
      throw new Error(`release matrix gate is missing expected blocker: ${requiredBlocker}`);
    }
  }
}

function assertScaffoldedMatrixReportsMissingEvidence(output) {
  const result = parseTrailingJson(output, "scaffolded release matrix gate");
  if (result.status !== "no-go" || result.ready !== false) {
    throw new Error("scaffolded release matrix must be No-Go before artifacts are collected");
  }
  const blockers = Array.isArray(result.blockers) ? result.blockers : [];
  for (const requiredBlocker of [
    "chromium: Missing browser export capability evidence",
    "chromium: Missing successful 1920x1080 60s export evidence",
  ]) {
    if (!blockers.includes(requiredBlocker)) {
      throw new Error(`scaffolded release matrix is missing expected blocker: ${requiredBlocker}`);
    }
  }
}

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(usage());
  process.exit(0);
}

try {
  runStep({ name: "unit tests", command: "npm", args: ["test", "--", "--run"] });
  runStep({ name: "production build", command: "npm", args: ["run", "build"] });
  runStep({ name: "host integration example typecheck", command: "npm", args: ["run", "check:examples"] });
  runStep({ name: "packed package consumer smoke", command: "npm", args: ["run", "verify:consumer"] });
  runStep({
    name: "package dry-run",
    command: "npm",
    args: ["pack", "--dry-run"],
    env: {
      npm_config_cache: process.env.npm_config_cache ?? "/private/tmp/race-overlay-npm-cache",
      NPM_CONFIG_CACHE: process.env.NPM_CONFIG_CACHE ?? "/private/tmp/race-overlay-npm-cache",
    },
  });
  const scaffoldDir = mkdtempSync(resolve(tmpdir(), "race-overlay-release-evidence-"));
  try {
    runStep({
      name: "release evidence scaffold",
      command: node,
      args: ["scripts/scaffold-portability-evidence.mjs", "--out", scaffoldDir],
    });
    const scaffoldMatrix = runStep({
      name: "scaffolded release matrix evidence",
      command: node,
      args: ["scripts/evaluate-portability-evidence.mjs", "--manifest", resolve(scaffoldDir, "evidence-matrix.json"), "--json"],
      expectedStatus: 1,
    });
    assertScaffoldedMatrixReportsMissingEvidence(scaffoldMatrix);
  } finally {
    rmSync(scaffoldDir, { recursive: true, force: true });
  }
  const currentEvidence = runStep({
    name: "current in-app-browser evidence",
    command: node,
    args: [
      "scripts/evaluate-portability-evidence.mjs",
      "--capabilities",
      "src/test/fixtures/iab-capabilities.json",
      "--measurement",
      "../docs/superpowers/reports/evidence/2026-06-19-rac-6-iab-720p-success.json",
      "--measurement",
      "../docs/superpowers/reports/evidence/2026-06-19-rac-6-iab-1080p-success.json",
      "--json",
    ],
  });
  assertCurrentEvidencePasses(currentEvidence);
  const releaseMatrix = runStep({
    name: "release matrix evidence",
    command: node,
    args: ["scripts/evaluate-portability-evidence.mjs", "--manifest", "src/test/fixtures/evidence-matrix.json", "--json"],
    expectedStatus: 1,
  });
  assertReleaseMatrixStillBlocksMissingEvidence(releaseMatrix);
  console.log("\n[portability] current package gate passed; final release matrix still needs target-browser evidence.");
} catch (error) {
  console.error(`\n[portability] ${error instanceof Error ? error.message : String(error)}`);
  console.error("");
  console.error(usage());
  process.exit(1);
}
