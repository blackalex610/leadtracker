import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { api } from "@/lib/api";
import { enableWorkerPump, kickWorker, resetWorkerPump } from "@/lib/worker-pump";
import { server } from "@/test/server";

function workerRunSequence(results: { ran: number; queued: number; running: number }[]) {
  const calls: number[] = [];
  server.use(
    http.post("*/api/worker/run", () => {
      const result = results[Math.min(calls.length, results.length - 1)];
      calls.push(calls.length);
      return HttpResponse.json({ ...result, on_demand: true });
    }),
  );
  return calls;
}

describe("worker pump (serverless job processing)", () => {
  afterEach(() => resetWorkerPump());

  it("runs slices until the queue is empty", async () => {
    const calls = workerRunSequence([
      { ran: 1, queued: 1, running: 0 },
      { ran: 1, queued: 0, running: 0 },
    ]);
    enableWorkerPump(true);
    kickWorker(); // already pumping: no second loop
    await expect.poll(() => calls.length).toBe(2);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls.length).toBe(2);
  });

  it("does nothing while disabled", async () => {
    const calls = workerRunSequence([{ ran: 0, queued: 0, running: 0 }]);
    kickWorker();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls.length).toBe(0);
  });

  it("starts after a request that queues a job", async () => {
    server.use(http.post("*/api/leads/:id/audit", () => HttpResponse.json({ job_id: 9, status: "queued" })));
    const calls = workerRunSequence([{ ran: 0, queued: 0, running: 0 }]);
    enableWorkerPump(true);
    await expect.poll(() => calls.length).toBe(1);
    await api.auditLead(1);
    await expect.poll(() => calls.length).toBe(2);
  });
});
