#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = fileURLToPath(new URL(".", import.meta.url));
const packageRoot = resolve(scriptDir, "..");
const libraryPath = resolve(packageRoot, "dist/lib/race-overlay-web.js");

function usage() {
  return [
    "Usage:",
    "  npm run evaluate:evidence -- --capabilities capabilities.json --measurement 720p.json --measurement 1080p.json",
    "  npm run evaluate:evidence -- --manifest evidence-matrix.json",
    "",
    "Options:",
    "  --manifest <file>               Multi-target evidence manifest JSON",
    "  --capabilities <file>           Browser export capability evidence JSON",
    "  --measurement <file>            Browser export measurement JSON; repeat for each run",
    "  --require-audio-retention       Treat audioTrackCount: 0 as No-Go",
    "  --json                          Print JSON only",
  ].join("\n");
}

function parseArgs(argv) {
  const parsed = {
    manifestPath: "",
    capabilityPath: "",
    measurementPaths: [],
    requireAudioRetention: false,
    jsonOnly: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--manifest") {
      parsed.manifestPath = argv[index + 1] ?? "";
      index += 1;
    } else if (argument === "--capabilities") {
      parsed.capabilityPath = argv[index + 1] ?? "";
      index += 1;
    } else if (argument === "--measurement") {
      const value = argv[index + 1] ?? "";
      if (value) {
        parsed.measurementPaths.push(value);
      }
      index += 1;
    } else if (argument === "--require-audio-retention") {
      parsed.requireAudioRetention = true;
    } else if (argument === "--json") {
      parsed.jsonOnly = true;
    } else if (argument === "--help" || argument === "-h") {
      console.log(usage());
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${argument}`);
    }
  }

  if (parsed.manifestPath) {
    return parsed;
  }

  if (!parsed.capabilityPath) {
    throw new Error("Missing --capabilities");
  }
  if (parsed.measurementPaths.length === 0) {
    throw new Error("Provide at least one --measurement");
  }

  return parsed;
}

function readJson(path) {
  return JSON.parse(readFileSync(resolve(process.cwd(), path), "utf8"));
}

function readJsonFrom(baseDir, path) {
  return JSON.parse(readFileSync(resolve(baseDir, path), "utf8"));
}

function readCapabilityEvidence(path) {
  return validateCapabilityEvidence(readJson(path), path);
}

function readMeasurementEvidence(path) {
  return validateMeasurementEvidence(readJson(path), path);
}

function readCapabilityEvidenceFrom(baseDir, path) {
  return validateCapabilityEvidence(readJsonFrom(baseDir, path), path);
}

function readMeasurementEvidenceFrom(baseDir, path) {
  return validateMeasurementEvidence(readJsonFrom(baseDir, path), path);
}

function readOptionalCapabilityEvidenceFrom(baseDir, path) {
  try {
    return readCapabilityEvidenceFrom(baseDir, path);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

function readOptionalMeasurementEvidenceFrom(baseDir, path) {
  try {
    return readMeasurementEvidenceFrom(baseDir, path);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

function assertNonEmptyString(value, label) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Manifest ${label} must be a non-empty string`);
  }
}

function assertOptionalString(value, label) {
  if (value != null && typeof value !== "string") {
    throw new Error(`${label} must be a string`);
  }
}

function assertBoolean(value, label) {
  if (typeof value !== "boolean") {
    throw new Error(`${label} must be a boolean`);
  }
}

function assertNonNegativeInteger(value, label) {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
}

function assertPositiveNumber(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new Error(`${label} must be a positive number`);
  }
}

function assertNonNegativeNumber(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`${label} must be a non-negative number`);
  }
}

function assertNullablePositiveNumber(value, label) {
  if (value !== null) {
    assertPositiveNumber(value, label);
  }
}

function assertNullableNonNegativeNumber(value, label) {
  if (value !== null) {
    assertNonNegativeNumber(value, label);
  }
}

function assertEvidenceBase(value, label) {
  if (typeof value !== "object" || value == null || Array.isArray(value)) {
    throw new Error(`${label} must be a JSON object`);
  }
  if (value.schemaVersion !== 1) {
    throw new Error(`${label}.schemaVersion must be 1`);
  }
  if (typeof value.generatedAt !== "string" || value.generatedAt.trim() === "") {
    throw new Error(`${label}.generatedAt must be a non-empty string`);
  }
  assertOptionalString(value.activityName, `${label}.activityName`);
  assertOptionalString(value.videoName, `${label}.videoName`);
}

function validateCapabilityEvidence(value, path) {
  const label = `Capability evidence ${path}`;
  assertEvidenceBase(value, label);
  if (value.status !== "capabilities") {
    throw new Error(`${label}.status must be "capabilities"`);
  }
  assertOptionalString(value.browserName, `${label}.browserName`);
  const capabilities = value.capabilities;
  if (typeof capabilities !== "object" || capabilities == null || Array.isArray(capabilities)) {
    throw new Error(`${label}.capabilities must be an object`);
  }
  assertBoolean(capabilities.canExportWebm, `${label}.capabilities.canExportWebm`);
  if (capabilities.supportedMimeType !== null && typeof capabilities.supportedMimeType !== "string") {
    throw new Error(`${label}.capabilities.supportedMimeType must be a string or null`);
  }
  assertBoolean(capabilities.supportsCanvasCapture, `${label}.capabilities.supportsCanvasCapture`);
  assertBoolean(capabilities.supportsVideoCaptureStream, `${label}.capabilities.supportsVideoCaptureStream`);
  if (capabilities.sourceAudioTrackCount !== null) {
    assertNonNegativeInteger(capabilities.sourceAudioTrackCount, `${label}.capabilities.sourceAudioTrackCount`);
  }
  assertBoolean(capabilities.supportsMemoryMeasurement, `${label}.capabilities.supportsMemoryMeasurement`);
  return value;
}

function validateMeasurementEvidence(value, path) {
  const label = `Measurement evidence ${path}`;
  assertEvidenceBase(value, label);
  if (value.status === "failed") {
    if (typeof value.error !== "string" || value.error.trim() === "") {
      throw new Error(`${label}.error must be a non-empty string`);
    }
    const attemptedExport = value.attemptedExport;
    if (typeof attemptedExport !== "object" || attemptedExport == null || Array.isArray(attemptedExport)) {
      throw new Error(`${label}.attemptedExport must be an object`);
    }
    assertPositiveNumber(attemptedExport.width, `${label}.attemptedExport.width`);
    assertPositiveNumber(attemptedExport.height, `${label}.attemptedExport.height`);
    assertPositiveNumber(attemptedExport.fps, `${label}.attemptedExport.fps`);
    assertPositiveNumber(attemptedExport.bitrateMbps, `${label}.attemptedExport.bitrateMbps`);
    assertNullablePositiveNumber(attemptedExport.durationSeconds, `${label}.attemptedExport.durationSeconds`);
    return value;
  }
  if (value.status != null && value.status !== "completed") {
    throw new Error(`${label}.status must be "completed", "failed", or omitted`);
  }
  const report = value.report;
  if (typeof report !== "object" || report == null || Array.isArray(report)) {
    throw new Error(`${label}.report must be an object`);
  }
  assertPositiveNumber(report.width, `${label}.report.width`);
  assertPositiveNumber(report.height, `${label}.report.height`);
  assertPositiveNumber(report.fps, `${label}.report.fps`);
  assertPositiveNumber(report.bitrateMbps, `${label}.report.bitrateMbps`);
  if (typeof report.mimeType !== "string" || report.mimeType.trim() === "") {
    throw new Error(`${label}.report.mimeType must be a non-empty string`);
  }
  assertNonNegativeNumber(report.elapsedMs, `${label}.report.elapsedMs`);
  assertNonNegativeNumber(report.outputBytes, `${label}.report.outputBytes`);
  assertNullablePositiveNumber(report.durationSeconds, `${label}.report.durationSeconds`);
  assertNonNegativeInteger(report.audioTrackCount, `${label}.report.audioTrackCount`);
  assertNullableNonNegativeNumber(report.memoryUsedBytes, `${label}.report.memoryUsedBytes`);
  if (report.playbackMode !== "normal" && report.playbackMode !== "muted-fallback") {
    throw new Error(`${label}.report.playbackMode must be "normal" or "muted-fallback"`);
  }
  return value;
}

function assertStringArray(value, label, { required = false } = {}) {
  if (value == null && !required) {
    return undefined;
  }
  if (!Array.isArray(value)) {
    throw new Error(`Manifest ${label} must be an array`);
  }
  value.forEach((item, index) => assertNonEmptyString(item, `${label}[${index}]`));
  return value;
}

function assertRequiredExports(value) {
  if (value == null) {
    return undefined;
  }
  if (!Array.isArray(value)) {
    throw new Error("Manifest requiredExports must be an array");
  }
  return value.map((item, index) => {
    const label = `requiredExports[${index}]`;
    if (typeof item !== "object" || item == null || Array.isArray(item)) {
      throw new Error(`Manifest ${label} must be an object`);
    }
    for (const field of ["width", "height", "durationSeconds"]) {
      if (typeof item[field] !== "number" || !Number.isFinite(item[field]) || item[field] <= 0) {
        throw new Error(`Manifest ${label}.${field} must be a positive number`);
      }
    }
    return item;
  });
}

function validateManifest(manifest) {
  if (typeof manifest !== "object" || manifest == null || Array.isArray(manifest)) {
    throw new Error("Manifest must be a JSON object");
  }
  const requiredTargets = assertStringArray(manifest.requiredTargets, "requiredTargets");
  const requiredExports = assertRequiredExports(manifest.requiredExports);
  if (!Array.isArray(manifest.targets)) {
    throw new Error("Manifest targets must be an array");
  }
  const targets = manifest.targets.map((target, index) => {
    const label = `targets[${index}]`;
    if (typeof target !== "object" || target == null || Array.isArray(target)) {
      throw new Error(`Manifest ${label} must be an object`);
    }
    assertNonEmptyString(target.name, `${label}.name`);
    if (target.capabilities != null) {
      assertNonEmptyString(target.capabilities, `${label}.capabilities`);
    }
    const measurements = assertStringArray(target.measurements, `${label}.measurements`, { required: true });
    if (target.requireAudioRetention != null && typeof target.requireAudioRetention !== "boolean") {
      throw new Error(`Manifest ${label}.requireAudioRetention must be a boolean`);
    }
    return {
      name: target.name,
      capabilities: target.capabilities,
      measurements,
      requireAudioRetention: target.requireAudioRetention,
    };
  });
  return {
    requiredTargets,
    requiredExports,
    requireAudioRetention: Boolean(manifest.requireAudioRetention),
    targets,
  };
}

function readManifestTargets(manifestPath) {
  const absoluteManifestPath = resolve(process.cwd(), manifestPath);
  const manifestDir = dirname(absoluteManifestPath);
  const manifest = validateManifest(JSON.parse(readFileSync(absoluteManifestPath, "utf8")));
  return {
    requiredTargets: manifest.requiredTargets,
    requiredExports: manifest.requiredExports,
    requireAudioRetention: manifest.requireAudioRetention,
    targets: manifest.targets.map((target) => ({
      name: target.name,
      capabilities: target.capabilities ? readOptionalCapabilityEvidenceFrom(manifestDir, target.capabilities) : null,
      measurements: Array.isArray(target.measurements)
        ? target.measurements
            .map((measurementPath) => readOptionalMeasurementEvidenceFrom(manifestDir, measurementPath))
            .filter((measurement) => measurement !== null)
        : [],
      requireAudioRetention:
        typeof target.requireAudioRetention === "boolean" ? target.requireAudioRetention : undefined,
    })),
  };
}

try {
  const options = parseArgs(process.argv.slice(2));
  const { evaluateBrowserPortabilityEvidence, evaluateBrowserPortabilityEvidenceMatrix } = await import(libraryPath);
  const result = options.manifestPath
    ? (() => {
        const manifestInput = readManifestTargets(options.manifestPath);
        return evaluateBrowserPortabilityEvidenceMatrix({
          ...manifestInput,
          requireAudioRetention: options.requireAudioRetention || manifestInput.requireAudioRetention,
        });
      })()
    : evaluateBrowserPortabilityEvidence({
        capabilities: readCapabilityEvidence(options.capabilityPath),
        measurements: options.measurementPaths.map((path) => readMeasurementEvidence(path)),
        requireAudioRetention: options.requireAudioRetention,
      });

  if (options.jsonOnly) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.log(`${result.status.toUpperCase()}: browser portability evidence ${result.ready ? "passes" : "does not pass"}`);
    if (result.blockers.length > 0) {
      console.log("Blockers:");
      for (const blocker of result.blockers) {
        console.log(`- ${blocker}`);
      }
    }
    if (result.warnings.length > 0) {
      console.log("Warnings:");
      for (const warning of result.warnings) {
        console.log(`- ${warning}`);
      }
    }
    console.log(JSON.stringify(result, null, 2));
  }

  process.exit(result.ready ? 0 : 1);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  console.error("");
  console.error(usage());
  process.exit(2);
}
