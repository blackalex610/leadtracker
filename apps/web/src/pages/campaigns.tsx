import { CATEGORY_LABELS, type LeadCategory } from "@leadtracker/shared";
import { PhoneCallIcon } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { JobStatusBadge } from "@/components/app/job-progress";
import { StartCallingDialog } from "@/components/app/start-calling-dialog";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime, jobTitle } from "@/lib/format";
import { useCallingSessions, useMeta, useSearchJobs } from "@/lib/queries";

export default function CampaignsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "searches";
  return (
    <div className="flex flex-col">
      <PageHeader
        title="Campaigns"
        description="Search history and calling sessions"
        actions={<StartCallingDialog />}
      />
      <Tabs value={tab} onValueChange={(t) => setParams({ tab: t }, { replace: true })} className="px-5 pt-3">
        <TabsList>
          <TabsTrigger value="searches">Search history</TabsTrigger>
          <TabsTrigger value="calling">Calling sessions</TabsTrigger>
        </TabsList>
        <TabsContent value="searches">
          <SearchesTab />
        </TabsContent>
        <TabsContent value="calling">
          <CallingTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function SearchesTab() {
  const jobs = useSearchJobs();
  if (jobs.error) return <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} />;
  if (jobs.data && jobs.data.items.length === 0) {
    return <EmptyState title="No searches yet" action={<Button size="sm" asChild><Link to="/search">Find leads</Link></Button>} />;
  }
  return (
    <Card className="mb-6">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Search</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Found</TableHead>
            <TableHead className="text-right">Fresh leads</TableHead>
            <TableHead className="text-right">Audited</TableHead>
            <TableHead className="text-right">API requests</TableHead>
            <TableHead>Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.data?.items.map((job) => {
            const n = (k: string) => (typeof job.counters[k] === "number" ? (job.counters[k] as number) : 0);
            return (
              <TableRow key={job.id}>
                <TableCell>
                  <Link to={`/search?job=${job.id}`} className="font-medium hover:underline">
                    {jobTitle(job.params)}
                  </Link>
                  <span className="text-xs text-muted-foreground"> · {n("queries_ok")} queries</span>
                </TableCell>
                <TableCell>
                  <JobStatusBadge job={job} />
                </TableCell>
                <TableCell className="text-right tabular">{job.progress_total}</TableCell>
                <TableCell className="text-right tabular">{n("matched") - n("dropped_after_audit")}</TableCell>
                <TableCell className="text-right tabular">{n("audited")}</TableCell>
                <TableCell className="text-right tabular">
                  {n("api_requests")}
                  {n("cached_requests") > 0 && <span className="text-muted-foreground"> (+{n("cached_requests")} cached)</span>}
                </TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(job.created_at)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}

function CallingTab() {
  const sessions = useCallingSessions();
  const meta = useMeta();
  if (sessions.error) return <ErrorState error={sessions.error} onRetry={() => void sessions.refetch()} />;
  if (sessions.data && sessions.data.length === 0) {
    return <EmptyState icon={PhoneCallIcon} title="No calling sessions yet" action={<StartCallingDialog />} />;
  }
  return (
    <Card className="mb-6">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Session</TableHead>
            <TableHead>Filters</TableHead>
            <TableHead className="text-right">Progress</TableHead>
            <TableHead className="text-right">Calls</TableHead>
            <TableHead className="text-right">Interested</TableHead>
            <TableHead className="text-right">Callbacks</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {sessions.data?.map((s) => (
            <TableRow key={s.id}>
              <TableCell>
                <p className="font-medium">#{s.id}</p>
                <p className="text-xs text-muted-foreground">{formatDateTime(s.started_at)}</p>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {[
                  Array.isArray(s.filters.categories) && s.filters.categories.length
                    ? (s.filters.categories as LeadCategory[]).map((c) => CATEGORY_LABELS[c] ?? c).join(", ")
                    : null,
                  typeof s.filters.target_key === "string"
                    ? (meta.data?.targets.find((t) => t.key === s.filters.target_key)?.label ?? s.filters.target_key)
                    : null,
                  s.filters.city,
                  Array.isArray(s.filters.priorities) ? s.filters.priorities.join("+") : null,
                  s.filters.window_start ? `${String(s.filters.window_start)}–${String(s.filters.window_end)}` : null,
                ]
                  .filter(Boolean)
                  .map(String)
                  .join(" · ")}
              </TableCell>
              <TableCell className="text-right tabular">
                {s.position}/{s.total}
              </TableCell>
              <TableCell className="text-right tabular">{s.stats.total_calls ?? 0}</TableCell>
              <TableCell className="text-right tabular">{s.stats.INTERESTED ?? 0}</TableCell>
              <TableCell className="text-right tabular">{s.stats.CALLBACK ?? 0}</TableCell>
              <TableCell className="text-right">
                {!s.ended_at && s.position < s.total ? (
                  <Button size="xs" asChild>
                    <Link to={`/calling/${s.id}`}>Resume</Link>
                  </Button>
                ) : (
                  <Badge variant="muted">{s.ended_at ? "Ended" : "Done"}</Badge>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
