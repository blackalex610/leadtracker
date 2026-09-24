import { zodResolver } from "@hookform/resolvers/zod";
import {
  ACTIVE_JOB_STATUSES,
  type LeadListQuery,
  type LeadSummary,
  type Priority,
  type SearchRequest,
} from "@leadtracker/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPinIcon, SearchIcon, SlidersHorizontalIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import { DemoBadge, OpportunityTags, PriorityBadge, Rating } from "@/components/app/badges";
import { JobProgress } from "@/components/app/job-progress";
import { PhoneLink } from "@/components/app/phone";
import { EmptyState, ErrorState, InlineNotice, PageHeader } from "@/components/app/states";
import { WebsiteCell } from "@/components/app/website-cell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api, errorMessage } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { keys, useLeads, useMeta, usePresets, useSearchJob, useSettings } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { searchSchema, toSearchRequest, type SearchFormInput, type SearchFormValues } from "@/features/search/search-schema";

const QUALITY_TO_PRIORITY: Record<string, Priority[] | undefined> = {
  any: undefined,
  high: ["HOT"],
  medium: ["WARM"],
  low: ["COLD"],
};

export function FindLeadsPage() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const initialPreset = (location.state as { preset?: string } | null)?.preset ?? "gyms";
  const jobId = params.get("job") ? Number(params.get("job")) : null;
  const meta = useMeta();
  const settings = useSettings();
  const provider = meta.data?.provider;
  const blocked = provider ? !provider.configured && !provider.demo_mode : false;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader title="Find Leads" description="Search local businesses, audit their websites and score the opportunity" />
      <div className="grid flex-1 gap-4 p-5 xl:grid-cols-[22rem_1fr]">
        <div className="flex flex-col gap-3">
          {blocked && (
            <InlineNotice tone="error" title="Provider not configured">
              The backend has no <code>PROVIDER_API_KEY</code>. Add a Google Places API (New) key to the API
              environment and restart it — or set <code>DEMO_MODE=true</code> for synthetic test data.{" "}
              <Link to="/settings?tab=provider" className="underline">
                Setup guide
              </Link>
            </InlineNotice>
          )}
          {settings.data ? (
            <SearchForm initialPreset={initialPreset} disabled={blocked} onStarted={(id) => setParams({ job: String(id) })} />
          ) : settings.error ? (
            <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
          ) : (
            <Skeleton className="h-[34rem]" />
          )}
        </div>
        <div className="min-w-0">
          {jobId ? <JobResults jobId={jobId} onRetried={(id) => setParams({ job: String(id) })} /> : <RecentHint />}
        </div>
      </div>
    </div>
  );
}

function RecentHint() {
  return (
    <Card className="h-full">
      <EmptyState
        icon={MapPinIcon}
        title="Choose a niche and a location"
        description="Results appear here as they are found. Re-running a search never creates duplicates — known businesses are updated, and provider responses are cached."
      />
    </Card>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

function SearchForm({ initialPreset, disabled, onStarted }: { initialPreset: string; disabled: boolean; onStarted: (jobId: number) => void }) {
  const client = useQueryClient();
  const meta = useMeta();
  const presets = usePresets();
  const settings = useSettings();
  const [showNeighborhoods, setShowNeighborhoods] = useState(false);
  const runtime = settings.data?.runtime;

  const form = useForm<SearchFormInput, unknown, SearchFormValues>({
    resolver: zodResolver(searchSchema),
    defaultValues: {
      preset_key: initialPreset,
      location: runtime?.general.default_city ?? "Sofia",
      neighborhoods: [],
      category: "gyms",
      keywords: "",
      min_rating: 4.0,
      min_reviews: Number.NaN,
      max_reviews: Number.NaN,
      has_website: "any",
      open_in_window: false,
      window_start: runtime?.calling.window_start ?? "19:00",
      window_end: runtime?.calling.window_end ?? "21:00",
      lead_quality: "any",
      max_results: runtime?.search.default_max_results ?? 60,
      audit_websites: true,
    },
  });

  const presetKey = useWatch({ control: form.control, name: "preset_key" });
  const appliedPreset = useRef<string | null>(null);
  useEffect(() => {
    const preset = presets.data?.find((p) => p.key === presetKey);
    // Apply a template only when the selection changes, never on a data refetch.
    if (!preset || appliedPreset.current === presetKey) return;
    appliedPreset.current = presetKey;
    form.setValue("category", preset.category_query, { shouldValidate: true });
    if (preset.keywords) form.setValue("keywords", preset.keywords);
    if (preset.calling_window_start && preset.calling_window_end) {
      form.setValue("window_start", preset.calling_window_start);
      form.setValue("window_end", preset.calling_window_end);
    }
  }, [presetKey, presets.data, form]);

  const location = useWatch({ control: form.control, name: "location" });
  const neighborhoods = useMemo(() => {
    const cities = meta.data?.cities ?? {};
    const key = Object.keys(cities).find((c) => c.toLowerCase() === location.trim().toLowerCase());
    return key ? cities[key] ?? [] : [];
  }, [meta.data, location]);

  const values = useWatch({ control: form.control });
  const parsed = searchSchema.safeParse(values);
  const request = useDebounced(parsed.success ? toSearchRequest(parsed.data) : null, 400);
  const estimate = useQuery({
    queryKey: ["search-estimate", request],
    queryFn: () => api.estimateSearch(request as SearchRequest),
    enabled: request !== null,
    staleTime: 30_000,
  });

  const start = useMutation({
    mutationFn: api.createSearch,
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: keys.searchJobs });
      toast.success("Search started");
      onStarted(job.id);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const errors = form.formState.errors;
  const selected = useWatch({ control: form.control, name: "neighborhoods" }) ?? [];

  return (
    <Card>
      <form
        className="grid gap-3 p-3"
        noValidate
        onSubmit={form.handleSubmit((v) => start.mutate(toSearchRequest(v)))}
        aria-label="Search businesses"
      >
        <div className="grid gap-1">
          <Label htmlFor="preset">Niche template</Label>
          <Controller
            control={form.control}
            name="preset_key"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="preset">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {presets.data?.map((p) => (
                    <SelectItem key={p.key} value={p.key}>
                      {p.label}
                    </SelectItem>
                  ))}
                  <SelectItem value="custom">Custom category…</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1">
            <Label htmlFor="category">Business category</Label>
            <Input id="category" list="category-suggestions" aria-invalid={!!errors.category} {...form.register("category")} />
            <datalist id="category-suggestions">
              {meta.data?.category_suggestions.map((c) => <option key={c} value={c} />)}
            </datalist>
            {errors.category && <p className="text-xs text-bad">{errors.category.message}</p>}
          </div>
          <div className="grid gap-1">
            <Label htmlFor="location">Location</Label>
            <Input id="location" list="city-suggestions" aria-invalid={!!errors.location} {...form.register("location")} />
            <datalist id="city-suggestions">
              {Object.keys(meta.data?.cities ?? {}).map((c) => <option key={c} value={c} />)}
            </datalist>
            {errors.location && <p className="text-xs text-bad">{errors.location.message}</p>}
          </div>
        </div>

        {neighborhoods.length > 0 && (
          <div className="grid gap-1">
            <div className="flex items-center justify-between">
              <Label>Neighborhoods {selected.length > 0 && <Badge variant="muted">{selected.length}</Badge>}</Label>
              <Button type="button" variant="link" size="xs" onClick={() => setShowNeighborhoods((v) => !v)}>
                {showNeighborhoods ? "Hide" : "Split search by neighborhood"}
              </Button>
            </div>
            {showNeighborhoods && (
              <Controller
                control={form.control}
                name="neighborhoods"
                render={({ field }) => (
                  <div className="flex flex-col gap-1.5">
                    <div className="flex flex-wrap gap-1">
                      {neighborhoods.map((n) => {
                        const on = field.value.includes(n);
                        return (
                          <button
                            key={n}
                            type="button"
                            aria-pressed={on}
                            onClick={() => field.onChange(on ? field.value.filter((x) => x !== n) : [...field.value, n])}
                            className={cn(
                              "rounded border px-1.5 py-0.5 text-xs transition-colors",
                              on ? "border-foreground bg-foreground text-background" : "hover:bg-accent",
                            )}
                          >
                            {n}
                          </button>
                        );
                      })}
                    </div>
                    <div className="flex gap-2 text-xs">
                      <button type="button" className="underline" onClick={() => field.onChange(neighborhoods)}>
                        Select all
                      </button>
                      <button type="button" className="underline" onClick={() => field.onChange([])}>
                        Clear
                      </button>
                      <span className="text-muted-foreground">Each neighborhood is a separate query (up to 60 results each).</span>
                    </div>
                  </div>
                )}
              />
            )}
          </div>
        )}

        <div className="grid gap-1">
          <Label htmlFor="keywords">Keywords (optional)</Label>
          <Input id="keywords" placeholder="e.g. crossfit, 24/7" {...form.register("keywords")} />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="grid gap-1">
            <Label htmlFor="min_rating">Min rating</Label>
            <Input id="min_rating" type="number" step="0.1" min={0} max={5} {...form.register("min_rating", { valueAsNumber: true })} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="min_reviews">Min reviews</Label>
            <Input id="min_reviews" type="number" min={0} placeholder="—" {...form.register("min_reviews", { valueAsNumber: true })} />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="max_reviews">Max reviews</Label>
            <Input id="max_reviews" type="number" min={0} placeholder="—" aria-invalid={!!errors.max_reviews} {...form.register("max_reviews", { valueAsNumber: true })} />
          </div>
        </div>
        {errors.max_reviews && <p className="-mt-2 text-xs text-bad">{errors.max_reviews.message}</p>}

        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1">
            <Label htmlFor="has_website">Has website</Label>
            <Controller
              control={form.control}
              name="has_website"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="has_website">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any</SelectItem>
                    <SelectItem value="yes">Yes</SelectItem>
                    <SelectItem value="no">No</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="lead_quality">Lead quality</Label>
            <Controller
              control={form.control}
              name="lead_quality"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="lead_quality">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any</SelectItem>
                    <SelectItem value="high">High (HOT)</SelectItem>
                    <SelectItem value="medium">Medium (WARM)</SelectItem>
                    <SelectItem value="low">Low (COLD)</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </div>
        </div>

        <div className="grid gap-1.5">
          <label className="flex items-center gap-2 text-[13px]">
            <Controller
              control={form.control}
              name="open_in_window"
              render={({ field }) => <Switch checked={field.value} onCheckedChange={field.onChange} />}
            />
            Open during calling hours
          </label>
          {values.open_in_window && (
            <div className="flex items-center gap-2">
              <Input aria-label="Window start" className="w-20" {...form.register("window_start")} />
              <span className="text-muted-foreground">–</span>
              <Input aria-label="Window end" className="w-20" {...form.register("window_end")} />
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 items-end gap-3">
          <div className="grid gap-1">
            <Label htmlFor="max_results">Max results</Label>
            <Input id="max_results" type="number" min={1} max={2000} {...form.register("max_results", { valueAsNumber: true })} />
          </div>
          <label className="flex h-8 items-center gap-2 text-[13px]">
            <Controller
              control={form.control}
              name="audit_websites"
              render={({ field }) => <Switch checked={field.value} onCheckedChange={field.onChange} />}
            />
            Audit websites
          </label>
        </div>

        <EstimateLine loading={estimate.isFetching} data={estimate.data} />

        <Button type="submit" disabled={disabled || start.isPending}>
          <SearchIcon /> {start.isPending ? "Starting…" : "Search"}
        </Button>
      </form>
    </Card>
  );
}

function EstimateLine({ loading, data }: { loading: boolean; data: Awaited<ReturnType<typeof api.estimateSearch>> | undefined }) {
  if (!data) return <p className="text-xs text-muted-foreground">{loading ? "Estimating cost…" : " "}</p>;
  if (data.demo_mode) return <p className="text-xs text-muted-foreground">Demo mode: synthetic results, no API cost.</p>;
  return (
    <p className="text-xs text-muted-foreground" aria-live="polite">
      {data.queries} {data.queries === 1 ? "query" : "queries"} · up to {data.max_requests} billable request
      {data.max_requests === 1 ? "" : "s"}
      {data.estimated_max_cost !== null && (
        <>
          {" "}· max ≈ <span className="font-medium text-foreground">{formatMoney(data.estimated_max_cost_display, data.display_currency)}</span>
          {data.free_units_remaining !== null && data.free_units_remaining > 0 && ` (${data.free_units_remaining} free requests left this month)`}
        </>
      )}
      {" "}· cached results cost nothing.
    </p>
  );
}

function JobResults({ jobId, onRetried }: { jobId: number; onRetried: (id: number) => void }) {
  const navigate = useNavigate();
  const job = useSearchJob(jobId);
  const [showFiltered, setShowFiltered] = useState(false);
  const active = job.data ? ACTIVE_JOB_STATUSES.includes(job.data.status) : false;
  const quality = typeof job.data?.params.lead_quality === "string" ? job.data.params.lead_quality : "any";
  const query: LeadListQuery = {
    job_id: jobId,
    job_matched_only: !showFiltered,
    priority: QUALITY_TO_PRIORITY[quality],
    sort: "priority",
    order: "desc",
    page_size: 100,
  };
  const leads = useLeads(query, { enabled: !!job.data });
  // Refresh results whenever the job reports progress (and once more when it finishes).
  const progressKey = `${job.data?.status}:${job.data?.progress_processed}:${job.data?.progress_total}`;
  const refetchLeads = leads.refetch;
  useEffect(() => {
    if (job.data) void refetchLeads();
  }, [progressKey, refetchLeads, job.data]);

  if (job.error) return <ErrorState error={job.error} onRetry={() => void job.refetch()} />;
  if (!job.data) return <Skeleton className="h-24" />;
  const filteredOut = Number(job.data.counters.filtered_out ?? 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[13px] font-semibold">
          {String(job.data.params.category)} in {String(job.data.params.location)}
          {Array.isArray(job.data.params.neighborhoods) && job.data.params.neighborhoods.length > 0 && (
            <span className="font-normal text-muted-foreground"> · {job.data.params.neighborhoods.length} neighborhoods</span>
          )}
        </h2>
        <div className="flex items-center gap-2">
          {filteredOut > 0 && (
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Switch checked={showFiltered} onCheckedChange={setShowFiltered} /> Show {filteredOut} filtered out
            </label>
          )}
          <Button size="xs" variant="outline" asChild>
            <Link to={`/leads?job_id=${jobId}`}>
              <SlidersHorizontalIcon /> Open in lead table
            </Link>
          </Button>
        </div>
      </div>
      <JobProgress job={job.data} onRetried={(j) => onRetried(j.id)} />
      {leads.data && leads.data.items.length === 0 && !active ? (
        <Card>
          <EmptyState title="No businesses matched" description="Try a broader category, lower the minimum rating or remove filters." />
        </Card>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3" aria-busy={active}>
          {leads.data?.items.map((lead) => (
            <ResultCard key={lead.id} lead={lead} onOpen={() => navigate(`/leads/${lead.id}`)} />
          ))}
          {!leads.data && Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-36" />)}
        </div>
      )}
      {leads.data && leads.data.total > leads.data.items.length && (
        <p className="text-xs text-muted-foreground">
          Showing {leads.data.items.length} of {leads.data.total}.{" "}
          <Link to={`/leads?job_id=${jobId}`} className="underline">
            See all in the lead table
          </Link>
        </p>
      )}
    </div>
  );
}

function ResultCard({ lead, onOpen }: { lead: LeadSummary; onOpen: () => void }) {
  return (
    <Card
      role="link"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter") onOpen();
      }}
      className="flex cursor-pointer flex-col gap-2 p-3 outline-none transition-colors hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring/40"
      aria-label={lead.name}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold">{lead.name}</p>
          <p className="truncate text-xs text-muted-foreground">{lead.category ?? "—"}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {lead.is_demo && <DemoBadge />}
          <PriorityBadge priority={lead.priority} />
        </div>
      </div>
      <div className="flex items-center justify-between text-xs">
        <Rating rating={lead.rating} reviews={lead.review_count} />
        <PhoneLink
          phone={lead.normalized_phone}
          display={lead.international_phone}
          isDemo={lead.is_demo}
          invalid={lead.phone_invalid}
          suppressed={lead.suppressed}
        />
      </div>
      <dl className="grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-1 text-xs">
        <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Website</dt>
        <dd className="min-w-0 truncate">
          <WebsiteCell lead={lead} />
          {lead.website_health_score !== null && (
            <span className="ml-1 text-muted-foreground">· health {lead.website_health_score}</span>
          )}
        </dd>
        <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Opportunity</dt>
        <dd>
          <OpportunityTags types={lead.opportunity_types} max={3} />
        </dd>
      </dl>
      {lead.top_reason && <p className="line-clamp-1 text-xs text-muted-foreground">Why: {lead.top_reason}</p>}
    </Card>
  );
}
