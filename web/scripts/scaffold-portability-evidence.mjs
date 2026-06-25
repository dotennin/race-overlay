#!/usr/bin/env node

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";

const DEFAULT_TARGETS = ["chromium", "firefox", "safari", "production-device"];
const DEFAULT_EXPORTS = [
  { width: 1280, height: 720, durationSeconds: 5 },
  { width: 1920, height: 1080, durationSeconds: 5 },
  { width: 1920, height: 1080, durationSeconds: 60 },
];

function usage() {
  return [
    "Usage:",
    "  npm run scaffold:evidence -- --out path/to/release-evidence",
    "",
    "Options:",
    "  --out <dir>                    Evidence workspace directory to create",
    "  --target <name>                Required target; repeat to override defaults",
    "  --require-audio-retention      Add requireAudioRetention: true to the manifest",
    "  --force                        Overwrite existing manifest and README",
    "",
    "The scaffold creates a manifest plus per-target folders for capability,",
    "measurement, and failure artifacts downloaded from the demo UI or host app.",
  ].join("\n");
}

function parseArgs(argv) {
  const options = {
    outDir: "",
    targets: [],
    requireAudioRetention: false,
    force: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--out") {
      options.outDir = argv[index + 1] ?? "";
      index += 1;
    } else if (argument === "--target") {
      const target = argv[index + 1] ?? "";
      if (target.trim()) {
        options.targets.push(target.trim());
      }
      index += 1;
    } else if (argument === "--require-audio-retention") {
      options.requireAudioRetention = true;
    } else if (argument === "--force") {
      options.force = true;
    } else if (argument === "--help" || argument === "-h") {
      console.log(usage());
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${argument}`);
    }
  }

  if (!options.outDir) {
    throw new Error("Missing --out");
  }
  return {
    ...options,
    targets: options.targets.length > 0 ? options.targets : DEFAULT_TARGETS,
  };
}

function measurementFileName(required) {
  return `${required.width}x${required.height}-${required.durationSeconds}s-measurement.json`;
}

function writeFile(path, content, force) {
  if (existsSync(path) && !force) {
    throw new Error(`${path} already exists; pass --force to overwrite generated files`);
  }
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
}

function createManifest(targets, requireAudioRetention) {
  const manifest = {
    schemaVersion: 1,
    requiredTargets: targets,
    requiredExports: DEFAULT_EXPORTS,
    targets: targets.map((target) => ({
      name: target,
      capabilities: `./${target}/capabilities.json`,
      measurements: DEFAULT_EXPORTS.map((required) => `./${target}/${measurementFileName(required)}`),
    })),
  };

  if (requireAudioRetention) {
    manifest.requireAudioRetention = true;
  }

  return `${JSON.stringify(manifest, null, 2)}\n`;
}

function createReadme(targets, requireAudioRetention, manifestPathFromPackageRoot) {
  const targetList = targets.map((target) => `- ${target}`).join("\n");
  const audioFlag = requireAudioRetention ? " --require-audio-retention" : "";
  return `# Race Overlay Web Release Evidence

This directory is the handoff workspace for proving a browser migration target.

Required targets:

${targetList}

For each target:

1. Open the host app or demo in that browser/device.
2. Upload a TCX file and a source video file.
3. Download capability JSON as \`capabilities.json\`.
4. Export and download measurement JSON for every required export in \`evidence-matrix.json\`.
5. Save failed runs beside the measurements as failure evidence instead of replacing successful files.

Evaluate the release gate from the package root:

\`\`\`bash
npm run build
npm run evaluate:evidence -- --manifest ${manifestPathFromPackageRoot}${audioFlag}
\`\`\`

The package is portable for this matrix only when the evaluator exits 0. Exit 1 means the evidence is well-formed but still No-Go; exit 2 means the manifest or an existing referenced JSON file is malformed.
`;
}

try {
  const options = parseArgs(process.argv.slice(2));
  const outDir = resolve(process.cwd(), options.outDir);
  mkdirSync(outDir, { recursive: true });

  for (const target of options.targets) {
    mkdirSync(resolve(outDir, target), { recursive: true });
  }

  const manifestPath = resolve(outDir, "evidence-matrix.json");
  writeFile(manifestPath, createManifest(options.targets, options.requireAudioRetention), options.force);
  writeFile(
    resolve(outDir, "README.md"),
    createReadme(options.targets, options.requireAudioRetention, relative(process.cwd(), manifestPath)),
    options.force,
  );

  console.log(`Created portability evidence scaffold at ${outDir}`);
  console.log(`Evaluate with: npm run evaluate:evidence -- --manifest ${relative(process.cwd(), resolve(outDir, "evidence-matrix.json"))}`);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  console.error("");
  console.error(usage());
  process.exit(2);
}
