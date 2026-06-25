import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

interface PackageJson {
  bin?: Record<string, string>;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  exports?: Record<string, unknown>;
  files?: string[];
  main?: string;
  module?: string;
  name?: string;
  peerDependencies?: Record<string, string>;
  private?: boolean;
  sideEffects?: string[];
  scripts?: Record<string, string>;
  types?: string;
}

const packageJson = JSON.parse(
  readFileSync(resolve(__dirname, "../package.json"), "utf8"),
) as PackageJson;

describe("web package portability manifest", () => {
  it("declares a portable library entrypoint alongside the demo app", () => {
    expect(packageJson.name).toBe("race-overlay-web");
    expect(packageJson.private).not.toBe(true);
    expect(packageJson.sideEffects).toEqual(["*.css"]);
    expect(packageJson.main).toBe("./dist/lib/race-overlay-web.umd.cjs");
    expect(packageJson.module).toBe("./dist/lib/race-overlay-web.js");
    expect(packageJson.types).toBe("./dist/types/index.d.ts");
    expect(packageJson.bin).toEqual({
      "race-overlay-evaluate-evidence": "./scripts/evaluate-portability-evidence.mjs",
      "race-overlay-scaffold-evidence": "./scripts/scaffold-portability-evidence.mjs",
      "race-overlay-verify-portability": "./scripts/verify-portability.mjs",
    });
    expect(packageJson.exports).toMatchObject({
      ".": {
        types: "./dist/types/index.d.ts",
        import: "./dist/lib/race-overlay-web.js",
        require: "./dist/lib/race-overlay-web.umd.cjs",
      },
      "./styles.css": "./src/styles.css",
    });
    expect(packageJson.files).toEqual([
      "README.md",
      "dist",
      "examples",
      "scripts/evaluate-portability-evidence.mjs",
      "scripts/scaffold-portability-evidence.mjs",
      "scripts/verify-package-consumer.mjs",
      "scripts/verify-portability.mjs",
      "src/styles.css",
    ]);
    expect(packageJson.scripts).toMatchObject({
      "build:app": "vite build",
      "build:lib": "vite build --config vite.lib.config.ts",
      "build:types": "tsc -p tsconfig.lib.json",
      "check:examples": "tsc -p tsconfig.examples.json --noEmit",
      "evaluate:evidence": "node scripts/evaluate-portability-evidence.mjs",
      "scaffold:evidence": "node scripts/scaffold-portability-evidence.mjs",
      "verify:consumer": "node scripts/verify-package-consumer.mjs",
      "verify:portability": "node scripts/verify-portability.mjs",
    });
    expect(packageJson.dependencies).toEqual({});
    expect(packageJson.peerDependencies).toEqual({
      react: "^19.1.0",
      "react-dom": "^19.1.0",
    });
    expect(packageJson.devDependencies).toMatchObject({
      "@vitejs/plugin-react": "^5.0.0",
      jsdom: "^26.1.0",
      react: "^19.1.0",
      "react-dom": "^19.1.0",
      typescript: "^5.8.0",
      vite: "^7.0.0",
      vitest: "^3.2.0",
    });
  });
});
