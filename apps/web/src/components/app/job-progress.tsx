import { ACTIVE_JOB_STATUSES, JOB_STAGE_LABELS, JOB_STATUS_LABELS, type JobOut } from "@leadtracker/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, RotateCcwIcon, SquareIcon } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { api, errorMessage } from "@/lib/api";
import { keys } from "@/lib/queries";

const STATUS_VARIANT = {
  queued: "muted",
  running: "secondary",
  completed: "good",
  partial: "warm",
  failed: "hot",
  cancelled: "muted",
} as const;

function counter(job: JobOut, key: string): number {
  const value = job.counters[key];
  return typeof value === "number" ? value : 0;
}

export function JobStatusBadge({ job }: { job: Pick<JobOut, "status"> }) {
  return <Badge variant={STATUS_VARIANT[job.status]}>{JOB_STATUS_LABELS[job.status]}</Badge>;
}

export function JobProgress({ job, onRetried }: { job: JobOut; onRetried?: (job: JobOut) => void }) {
  const client = useQueryClient();
  const active = ACTIVE_JOB_STATUSES.includes(job.status);
  const cancel = useMutation({
    mutationFn: () => api.cancelJob(job.id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.searchJob(job.id) });
      toast("Cancelling search…");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const retry = useMutation({
    mutationFn: () => api.retryJob(job.id),
    onSuccess: (newJob) => {
      void client.invalidateQueries({ queryKey: keys.searchJobs });
      onRetried?.(newJob);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const total = job.progress_total;
  const processed = job.progress_processed;
  const percent = total > 0 ? (processed / total) * 100 : active ? 5 : 100;
  const stage = JOB_STAGE_LABELS[job.stage ?? ""] ?? job.stage ?? "";
  const stats: [string, number][] = [
    ["found", counter(job, "found") || total],
    ["new", counter(job, "new")],
    ["already known", counter(job, "existing")],
    ["matched filters", counter(job, "matched")],
    ["websites audited", counter(job, "audited")],
    ["audits failed", counter(job, "audit_failed")],
    ["cached requests", counter(job, "cached_requests")],
    ["API requests", counter(job, "api_requests")],
  ];

  return (
    <div className="flex flex-col gap-2 rounded-md border bg-card p-3" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {active && <Loader2Icon className="size-3.5 animate-spin text-muted-foreground" aria-hidden />}
          <JobStatusBadge job={job} />
          <span className="text-[13px] font-medium">{active ? stage : JOB_STATUS_LABELS[job.status]}</span>
          <span className="text-xs text-muted-foreground tabular">
            {processed} / {total} businesses processed
          </span>
        </div>
        <div className="flex gap-2">
          {active && (
            <Button size="xs" variant="outline" onClick={() => cancel.mutate()} disabled={cancel.isPending || job.cancel_requested}>
              <SquareIcon /> {job.cancel_requested ? "Cancelling…" : "Cancel"}
            </Button>
          )}
          {["failed", "partial", "cancelled"].includes(job.status) && (
            <Button size="xs" variant="outline" onClick={() => retry.mutate()} disabled={retry.isPending}>
              <RotateCcwIcon /> Retry
            </Button>
          )}
        </div>
      </div>
      <Progress value={percent} aria-label="Search progress" />
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {stats
          .filter(([, v]) => v > 0)
          .map(([label, value]) => (
            <span key={label}>
              <span className="font-medium text-foreground tabular">{value}</span> {label}
            </span>
          ))}
      </div>
      {job.error_message && (
        <p className="text-xs text-bad" role="alert">
          {job.error_message}
        </p>
      )}
      {job.errors.length > 0 && !job.error_message && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">{job.errors.length} issue(s) during the search</summary>
          <ul className="mt-1 list-disc pl-4">
            {job.errors.slice(0, 10).map((e, i) => (
              <li key={i}>
                {String(e.message ?? e.code)}
                {e.query ? ` — ${String(e.query)}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
