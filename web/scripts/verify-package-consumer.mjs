#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = fileURLToPath(new URL(".", import.meta.url));
const packageRoot = resolve(scriptDir, "..");
const node = process.execPath;

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? packageRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      npm_config_cache: process.env.npm_config_cache ?? "/private/tmp/race-overlay-npm-cache",
      NPM_CONFIG_CACHE: process.env.NPM_CONFIG_CACHE ?? "/private/tmp/race-overlay-npm-cache",
      ...(options.env ?? {}),
    },
  });
  if (result.stdout) {
    process.stdout.write(result.stdout);
  }
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }
  const expectedStatus = options.expectedStatus ?? 0;
  if (result.status !== expectedStatus) {
    throw new Error(`${command} ${args.join(" ")} exited ${result.status}; expected ${expectedStatus}`);
  }
  return result.stdout;
}

function writeJson(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
}

function writeText(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, value);
}

function createReactPeerStubs(nodeModulesDir) {
  const reactDir = resolve(nodeModulesDir, "react");
  writeJson(resolve(reactDir, "package.json"), {
    name: "react",
    version: "19.1.0",
    exports: {
      ".": {
        import: "./index.mjs",
        require: "./index.cjs",
      },
      "./jsx-runtime": {
        import: "./jsx-runtime.mjs",
        require: "./jsx-runtime.cjs",
      },
    },
    main: "./index.cjs",
  });
  writeText(
    resolve(reactDir, "index.mjs"),
    [
      "export default {};",
      "export const Fragment = Symbol.for('react.fragment');",
      "export function createElement(type, props, ...children) { return { type, props: { ...(props ?? {}), children } }; }",
      "export function useEffect() {}",
      "export function useMemo(factory) { return factory(); }",
      "export function useRef(value) { return { current: value }; }",
      "export function useState(initialValue) { return [typeof initialValue === 'function' ? initialValue() : initialValue, () => {}]; }",
    ].join("\n"),
  );
  writeText(
    resolve(reactDir, "index.cjs"),
    [
      "const Fragment = Symbol.for('react.fragment');",
      "function createElement(type, props, ...children) { return { type, props: { ...(props || {}), children } }; }",
      "function useEffect() {}",
      "function useMemo(factory) { return factory(); }",
      "function useRef(value) { return { current: value }; }",
      "function useState(initialValue) { return [typeof initialValue === 'function' ? initialValue() : initialValue, () => {}]; }",
      "module.exports = { Fragment, createElement, useEffect, useMemo, useRef, useState, default: {} };",
    ].join("\n"),
  );
  writeText(
    resolve(reactDir, "jsx-runtime.mjs"),
    [
      "export const Fragment = Symbol.for('react.fragment');",
      "export function jsx(type, props) { return { type, props }; }",
      "export const jsxs = jsx;",
    ].join("\n"),
  );
  writeText(
    resolve(reactDir, "jsx-runtime.cjs"),
    [
      "const Fragment = Symbol.for('react.fragment');",
      "function jsx(type, props) { return { type, props }; }",
      "module.exports = { Fragment, jsx, jsxs: jsx };",
    ].join("\n"),
  );
}

function createConsumerSmoke(consumerDir) {
  writeText(
    resolve(consumerDir, "consumer-smoke.mjs"),
    [
      "import { existsSync, readFileSync } from 'node:fs';",
      "import { createRequire } from 'node:module';",
      "import { resolve } from 'node:path';",
      "import * as esm from 'race-overlay-web';",
      "const require = createRequire(import.meta.url);",
      "const cjs = require('race-overlay-web');",
      "function assert(condition, message) { if (!condition) throw new Error(message); }",
      "for (const api of ['RaceOverlay', 'readTcx', 'sampleAt', 'alignClip', 'createExternalVideoMetadataProvider', 'evaluateBrowserPortabilityEvidenceMatrix']) {",
      "  assert(typeof esm[api] === 'function', `Missing ESM export ${api}`);",
      "  assert(typeof cjs[api] === 'function', `Missing CJS export ${api}`);",
      "}",
      "const stylePath = require.resolve('race-overlay-web/styles.css');",
      "assert(existsSync(stylePath), 'CSS export path does not resolve to a file');",
      "const packageRoot = resolve(stylePath, '../..');",
      "const packageJson = JSON.parse(readFileSync(resolve(packageRoot, 'package.json'), 'utf8'));",
      "assert(packageJson.name === 'race-overlay-web', 'Unexpected package name');",
      "assert(packageJson.dependencies && Object.keys(packageJson.dependencies).length === 0, 'Runtime dependencies must stay empty');",
      "assert(existsSync(resolve(packageRoot, 'examples/host-integration.tsx')), 'Host integration example missing from tarball');",
      "assert(existsSync(resolve(packageRoot, 'scripts/evaluate-portability-evidence.mjs')), 'Evidence CLI missing from tarball');",
      "assert(existsSync(resolve(packageRoot, 'scripts/scaffold-portability-evidence.mjs')), 'Scaffold CLI missing from tarball');",
      "console.log('consumer smoke ok');",
    ].join("\n"),
  );
}

let tarballPath = "";
let tempDir = "";

try {
  const packOutput = run("npm", ["pack", "--json"]);
  const packResult = JSON.parse(packOutput);
  const packed = Array.isArray(packResult) ? packResult[0] : null;
  if (!packed?.filename) {
    throw new Error("npm pack --json did not return a tarball filename");
  }
  tarballPath = resolve(packageRoot, packed.filename);
  if (!existsSync(tarballPath)) {
    throw new Error(`Packed tarball does not exist: ${tarballPath}`);
  }

  tempDir = mkdtempSync(resolve(tmpdir(), "race-overlay-consumer-"));
  const consumerDir = resolve(tempDir, "consumer");
  const nodeModulesDir = resolve(consumerDir, "node_modules");
  const packageDir = resolve(nodeModulesDir, "race-overlay-web");
  mkdirSync(packageDir, { recursive: true });
  createReactPeerStubs(nodeModulesDir);

  run("tar", ["-xzf", tarballPath, "-C", packageDir, "--strip-components=1"], { cwd: packageRoot });
  createConsumerSmoke(consumerDir);
  run(node, ["consumer-smoke.mjs"], { cwd: consumerDir });
  run(node, [resolve(packageDir, "scripts/scaffold-portability-evidence.mjs"), "--out", "release-evidence"], {
    cwd: consumerDir,
  });
  run(
    node,
    [
      resolve(packageDir, "scripts/evaluate-portability-evidence.mjs"),
      "--manifest",
      "release-evidence/evidence-matrix.json",
      "--json",
    ],
    {
      cwd: consumerDir,
      expectedStatus: 1,
    },
  );
  console.log("package consumer smoke passed");
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
} finally {
  if (tarballPath) {
    rmSync(tarballPath, { force: true });
  }
  if (tempDir) {
    rmSync(tempDir, { recursive: true, force: true });
  }
}
