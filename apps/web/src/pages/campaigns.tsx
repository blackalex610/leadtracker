import { zodResolver } from "@hookform/resolvers/zod";
import {
  OPPORTUNITY_LABELS,
  OPPORTUNITY_TYPES,
  type OpportunityType,
  type Preset,
  type PresetCreate,
} from "@leadtracker/shared";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PencilIcon, PhoneCallIcon, PlusIcon, SearchIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";
import { z } from "zod";

import { JobStatusBadge } from "@/components/app/job-progress";
import { StartCallingDialog } from "@/components/app/start-calling-dialog";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { keys, useCallingSessions, usePresets, useSearchJobs } from "@/lib/queries";

export default function CampaignsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "templates";
  return (
    <div className="flex flex-col">
      <PageHeader
        title="Campaigns"
        description="Niche templates, search history and calling sessions"
        actions={<StartCallingDialog />}
      />
      <Tabs value={tab} onValueChange={(t) => setParams({ tab: t }, { replace: true })} className="px-5 pt-3">
        <TabsList>
          <TabsTrigger value="templates">Niche templates</TabsTrigger>
          <TabsTrigger value="searches">Search history</TabsTrigger>
          <TabsTrigger value="calling">Calling sessions</TabsTrigger>
        </TabsList>
        <TabsContent value="templates">
          <TemplatesTab />
        </TabsContent>
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

const time = z.union([z.literal(""), z.string().regex(/^([01]?\d|2[0-3]):[0-5]\d$/, "Use HH:MM")]);
const presetSchema = z.object({
  key: z.string().regex(/^[a-z0-9_]{2,64}$/, "Lowercase letters, digits and _ only"),
  label: z.string().trim().min(1, "Required").max(120),
  label_bg: z.string().max(120),
  category_query: z.string().trim().min(2, "Required").max(200),
  included_type: z.string().max(100),
  keywords: z.string().max(300),
  match_types: z.string(),
  calling_window_start: time,
  calling_window_end: time,
  booking_oriented: z.boolean(),
  discovery_dependent: z.boolean(),
  strong_opportunities: z.array(z.string()),
});
type PresetForm = z.infer<typeof presetSchema>;

function toPayload(v: PresetForm): PresetCreate {
  return {
    key: v.key,
    label: v.label,
    label_bg: v.label_bg || null,
    category_query: v.category_query,
    included_type: v.included_type || null,
    keywords: v.keywords || null,
    match_types: v.match_types.split(",").map((s) => s.trim()).filter(Boolean),
    calling_window_start: v.calling_window_start || null,
    calling_window_end: v.calling_window_end || null,
    booking_oriented: v.booking_oriented,
    discovery_dependent: v.discovery_dependent,
    strong_opportunities: v.strong_opportunities as OpportunityType[],
    sort_order: 100,
  };
}

function TemplatesTab() {
  const presets = usePresets();
  const client = useQueryClient();
  const [editing, setEditing] = useState<Preset | "new" | null>(null);
  const remove = useMutation({
    mutationFn: (id: number) => api.deletePreset(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.presets });
      toast.success("Template deleted");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (presets.error) return <ErrorState error={presets.error} onRetry={() => void presets.refetch()} />;
  return (
    <div className="flex flex-col gap-3 pb-6">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Templates pre-fill searches and calling sessions. Scoring uses their booking/discovery flags. Nothing is
          hard-coded — edit or delete any of them.
        </p>
        <Button size="sm" onClick={() => setEditing("new")}>
          <PlusIcon /> New template
        </Button>
      </div>
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Template</TableHead>
              <TableHead>Search query</TableHead>
              <TableHead>Calling window</TableHead>
              <TableHead>Strong opportunities</TableHead>
              <TableHead>Flags</TableHead>
              <TableHead className="text-right">Leads</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {presets.isPending &&
              Array.from({ length: 6 }, (_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={7}>
                    <Skeleton className="h-5" />
                  </TableCell>
                </TableRow>
              ))}
            {presets.data?.map((p) => (
              <TableRow key={p.id}>
                <TableCell>
                  <p className="font-medium">{p.label}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">{p.key}</p>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {p.category_query}
                  {p.included_type && <span className="font-mono text-[11px]"> · type:{p.included_type}</span>}
                </TableCell>
                <TableCell className="tabular">
                  {p.calling_window_start ? `${p.calling_window_start}–${p.calling_window_end}` : "default"}
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {p.strong_opportunities.map((o) => (
                      <Badge key={o} variant="outline" className="font-mono text-[10px] font-normal">
                        {o}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {[p.booking_oriented && "booking", p.discovery_dependent && "discovery"].filter(Boolean).join(", ") || "—"}
                </TableCell>
                <TableCell className="text-right tabular">
                  <Link to={`/leads?niche_key=${p.key}`} className="hover:underline">
                    {p.lead_count}
                  </Link>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button size="xs" variant="ghost" asChild>
                      <Link to={`/search`} state={{ preset: p.key }} title="Search with this template">
                        <SearchIcon />
                      </Link>
                    </Button>
                    <StartCallingDialog
                      defaults={{ niche_key: p.key }}
                      trigger={
                        <Button size="xs" variant="ghost" aria-label={`Call ${p.label}`}>
                          <PhoneCallIcon />
                        </Button>
                      }
                    />
                    <Button size="xs" variant="ghost" aria-label={`Edit ${p.label}`} onClick={() => setEditing(p)}>
                      <PencilIcon />
                    </Button>
                    <Button
                      size="xs"
                      variant="ghost"
                      aria-label={`Delete ${p.label}`}
                      onClick={() => {
                        if (window.confirm(`Delete template “${p.label}”? Leads keep their data.`)) remove.mutate(p.id);
                      }}
                    >
                      <Trash2Icon />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      {editing && <PresetDialog preset={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function PresetDialog({ preset, onClose }: { preset: Preset | null; onClose: () => void }) {
  const client = useQueryClient();
  const form = useForm<PresetForm>({
    resolver: zodResolver(presetSchema),
    defaultValues: {
      key: preset?.key ?? "",
      label: preset?.label ?? "",
      label_bg: preset?.label_bg ?? "",
      category_query: preset?.category_query ?? "",
      included_type: preset?.included_type ?? "",
      keywords: preset?.keywords ?? "",
      match_types: (preset?.match_types ?? []).join(", "),
      calling_window_start: preset?.calling_window_start ?? "",
      calling_window_end: preset?.calling_window_end ?? "",
      booking_oriented: preset?.booking_oriented ?? false,
      discovery_dependent: preset?.discovery_dependent ?? true,
      strong_opportunities: preset?.strong_opportunities ?? [],
    },
  });
  const save = useMutation({
    mutationFn: (values: PresetForm) => {
      const payload = toPayload(values);
      if (preset) {
        const { key: _key, ...rest } = payload;
        return api.updatePreset(preset.id, rest);
      }
      return api.createPreset(payload);
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.presets });
      toast.success("Template saved");
      onClose();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const errors = form.formState.errors;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{preset ? `Edit ${preset.label}` : "New niche template"}</DialogTitle>
          <DialogDescription>Used to pre-fill searches and to tell the scoring engine about the category.</DialogDescription>
        </DialogHeader>
        <form className="grid gap-3" onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="p-label">Label</Label>
              <Input id="p-label" aria-invalid={!!errors.label} {...form.register("label")} />
              {errors.label && <p className="text-xs text-bad">{errors.label.message}</p>}
            </div>
            <div className="grid gap-1">
              <Label htmlFor="p-key">Key</Label>
              <Input id="p-key" disabled={!!preset} aria-invalid={!!errors.key} {...form.register("key")} />
              {errors.key && <p className="text-xs text-bad">{errors.key.message}</p>}
            </div>
            <div className="grid gap-1">
              <Label htmlFor="p-query">Search query</Label>
              <Input id="p-query" placeholder="e.g. yoga studios" aria-invalid={!!errors.category_query} {...form.register("category_query")} />
              {errors.category_query && <p className="text-xs text-bad">{errors.category_query.message}</p>}
            </div>
            <div className="grid gap-1">
              <Label htmlFor="p-bg">Bulgarian label (pitch)</Label>
              <Input id="p-bg" placeholder="йога студия" {...form.register("label_bg")} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="p-type">Google place type (optional)</Label>
              <Input id="p-type" placeholder="yoga_studio" {...form.register("included_type")} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="p-match">Matching types (comma separated)</Label>
              <Input id="p-match" placeholder="yoga_studio, gym" {...form.register("match_types")} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="p-start">Calling window</Label>
              <div className="flex items-center gap-1">
                <Input id="p-start" placeholder="19:00" {...form.register("calling_window_start")} />
                <span className="text-muted-foreground">–</span>
                <Input aria-label="Window end" placeholder="21:00" {...form.register("calling_window_end")} />
              </div>
              {(errors.calling_window_start || errors.calling_window_end) && <p className="text-xs text-bad">Use HH:MM</p>}
            </div>
            <div className="grid gap-1">
              <Label htmlFor="p-keywords">Extra keywords</Label>
              <Input id="p-keywords" {...form.register("keywords")} />
            </div>
          </div>
          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-[13px]">
              <Controller control={form.control} name="booking_oriented"
                render={({ field }) => <Checkbox checked={field.value} onCheckedChange={(v) => field.onChange(v === true)} />} />
              Customers typically book
            </label>
            <label className="flex items-center gap-2 text-[13px]">
              <Controller control={form.control} name="discovery_dependent"
                render={({ field }) => <Checkbox checked={field.value} onCheckedChange={(v) => field.onChange(v === true)} />} />
              Relies on online discovery
            </label>
          </div>
          <div className="grid gap-1">
            <Label>Strong opportunities</Label>
            <Controller
              control={form.control}
              name="strong_opportunities"
              render={({ field }) => (
                <div className="flex flex-wrap gap-1">
                  {OPPORTUNITY_TYPES.map((o) => {
                    const on = field.value.includes(o);
                    return (
                      <button key={o} type="button" aria-pressed={on}
                        onClick={() => field.onChange(on ? field.value.filter((v) => v !== o) : [...field.value, o])}
                        className={on ? "rounded border border-foreground bg-foreground px-1.5 py-0.5 text-[11px] text-background" : "rounded border px-1.5 py-0.5 text-[11px] hover:bg-accent"}>
                        {OPPORTUNITY_LABELS[o]}
                      </button>
                    );
                  })}
                </div>
              )}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
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
            <TableHead className="text-right">New</TableHead>
            <TableHead className="text-right">Audited</TableHead>
            <TableHead className="text-right">API requests</TableHead>
            <TableHead>Started</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.data?.items.map((job) => {
            const n = (k: string) => (typeof job.counters[k] === "number" ? (job.counters[k] as number) : 0);
            const hoods = Array.isArray(job.params.neighborhoods) ? job.params.neighborhoods.length : 0;
            return (
              <TableRow key={job.id}>
                <TableCell>
                  <Link to={`/search?job=${job.id}`} className="font-medium hover:underline">
                    {String(job.params.category)} in {String(job.params.location)}
                  </Link>
                  {hoods > 0 && <span className="text-xs text-muted-foreground"> · {hoods} neighborhoods</span>}
                </TableCell>
                <TableCell>
                  <JobStatusBadge job={job} />
                </TableCell>
                <TableCell className="text-right tabular">{job.progress_total}</TableCell>
                <TableCell className="text-right tabular">{n("new")}</TableCell>
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
                  s.filters.niche_key,
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
