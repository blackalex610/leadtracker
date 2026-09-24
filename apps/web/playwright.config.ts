import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the real stack: FastAPI in DEMO_MODE (synthetic data,
 * no API key) + the Vite dev server. Needs PostgreSQL; the database in
 * E2E_DATABASE_URL is migrated automatically.
 *
 *   pnpm --filter @leadtracker/web e2e
 */
const databaseUrl =
  process.env.E2E_DATABASE_URL ?? "postgresql+asyncpg://leadtracker:leadtracker@localhost:5432/leadtracker_e2e";
// E2E_SERVERLESS=1 runs the API like on Vercel: no resident worker, jobs advance only
// through the browser's POST /api/worker/run calls.
const serverless = process.env.E2E_SERVERLESS === "1";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: "uv run alembic upgrade head && uv run uvicorn app.main:app --host 127.0.0.1 --port 8001",
      cwd: "../api",
      url: "http://127.0.0.1:8001/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        DATABASE_URL: databaseUrl,
        DEMO_MODE: "true",
        AUTH_MODE: "none",
        RUN_WORKER: serverless ? "false" : "true",
        SERVERLESS: serverless ? "true" : "false",
        WORKER_RUN_BUDGET_SECONDS: "10",
        CORS_ORIGINS: "http://127.0.0.1:5174",
        LOG_LEVEL: "WARNING",
      },
    },
    {
      command: "pnpm exec vite --host 127.0.0.1 --port 5174 --strictPort",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: !process.env.CI,
      env: { VITE_DEV_API_TARGET: "http://127.0.0.1:8001" },
    },
  ],
});
