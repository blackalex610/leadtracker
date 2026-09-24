import { ApiError, api, setJobQueuedListener } from "@/lib/api";

/**
 * Serverless deployments (Vercel) have no always-running worker: queued jobs are
 * processed in time-boxed slices, one `POST /api/worker/run` at a time, while the
 * app is open. The server resumes each job from its checkpoint. `kickWorker()` is
 * idempotent: at most one pump loop runs per tab.
 */
let enabled = false;
let pumping = false;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function enableWorkerPump(on: boolean): void {
  enabled = on;
  setJobQueuedListener(on ? kickWorker : null);
  if (on) kickWorker();
}

export function kickWorker(): void {
  if (!enabled || pumping) return;
  pumping = true;
  void pump().finally(() => {
    pumping = false;
  });
}

async function pump(): Promise<void> {
  let failures = 0;
  for (let round = 0; round < 500 && enabled; round++) {
    try {
      const result = await api.runWorker();
      failures = 0;
      if (!result.on_demand || (result.queued === 0 && result.running === 0)) return;
      // Another tab/user's slice holds the running job: look again shortly.
      if (result.ran === 0) await sleep(4000);
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return;
      failures += 1;
      if (failures >= 5) return;
      await sleep(2000 * failures);
    }
  }
}

/** Test helper. */
export function resetWorkerPump(): void {
  enabled = false;
  pumping = false;
  setJobQueuedListener(null);
}
