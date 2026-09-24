// Regenerates src/generated/api.ts from the FastAPI OpenAPI schema.
// Requires the API's Python environment (uv) to be installed: `cd apps/api && uv sync`.
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const apiDir = resolve(root, "../../apps/api");
const specPath = resolve(root, "openapi.json");

execFileSync("uv", ["run", "python", "-m", "app.cli", "dump-openapi", specPath], {
  cwd: apiDir,
  stdio: "inherit",
});
execFileSync(
  "pnpm",
  ["exec", "openapi-typescript", specPath, "-o", resolve(root, "src/generated/api.ts"), "--root-types", "--default-non-nullable", "false"],
  { cwd: root, stdio: "inherit" },
);
