import { zodResolver } from "@hookform/resolvers/zod";
import {
  ACTIVE_JOB_STATUSES,
  CATEGORY_LABELS,
  OFFER_LABELS,
  SELLABLE_CATEGORIES,
  type LeadCategory,
  type LeadListQuery,
  type LeadSummary,
  type SearchRequest,
  type TargetMeta,
} from "@leadtracker/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CrosshairIcon, SearchIcon, SlidersHorizontalIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import { CategoryBadge, DealValue, DemoBadge, Rating } from "@/components/app/badges";
import { JobProgress } from "@/components/app/job-progress";
import { PhoneLink } from "@/components/app/phone";
import { EmptyState, ErrorState, InlineNotice, PageHeader } from "@/components/app/states";
import { WebsiteCell } from "@/components/app/website-cell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api, errorMessage } from "@/lib/api";
import { formatMoney, jobTitle } from "@/lib/format";
import { keys, useLeads, useMeta, useSearchJob, useSettings } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { searchSchema, toSearchRequest, type SearchFormInput, type SearchFormValues } from "@/features/search/search-schema";

export function FindLeadsPage() {
  const [params, setParams] = useSearchParams();
  const jobId = params.get("job") ? Number(params.get("job")) : null;
  const meta = useMeta();
  const settings = useSettings();
  const provider = meta.data?.provider;
  const blocked = provider ? !provider.configured && !provider.demo_mode : false;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader
        title="Find Leads"
        description="One click: finds local businesses that need a website or more customers, checks them and tells you what to sell"
      />
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
            <SearchForm disabled={blocked} onStarted={(id) => setParams({ job: String(id) })} />
          ) : settings.error ? (
            <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
          ) : (
            <Skeleton className="h-[22rem]" />
          )}
          <WhatItLooksFor targets={meta.data?.targets ?? []} />
        </div>
        <div className="min-w-0">
          {jobId ? <JobResults jobId={jobId} onRetried={(id) => setParams({ job: String(id) })} /> : <Intro />}
        </div>
      </div>
    </div>
  );
}

function Intro() {
  const settings = useSettings();
  const minReviews = settings.data?.runtime.offers.min_reviews ?? 150;
  return (
    <Card className="h-full">
      <EmptyState
        icon={CrosshairIcon}
        title="Pick a city and hit Find leads"
        description={`It searches the business types most likely to need a website or more customers (trades, auto, clinics, salons, venues…), keeps only established businesses with ${minReviews}+ Google reviews, skips chains, closed and badly rated places, checks every website, and sorts what's left by the money each call is worth. Every click searches new ground — queries from the last 30 days are never repeated.`}
      />
    </Card>
  );
}

function WhatItLooksFor({ targets }: { targets: TargetMeta[] }) {
  const settings = useSettings();
  const minReviews = settings.data?.runtime.offers.min_reviews ?? 150;
  const groups = useMemo(() => {
    const map = new Map<string, TargetMeta[]>();
    for (const t of targets) map.set(t.group_label, [...(map.get(t.group_label) ?? []), t]);
    return [...map.entries()];
  }, [targets]);
  if (!groups.length) return null;
  return (
    <Card className="p-3">
      <details>
        <summary className="cursor-pointer text-[13px] font-medium">What it searches for ({targets.length} business types)</summary>
        <div className="mt-2 grid gap-2 text-xs">
          {groups.map(([group, items]) => (
            <div key={group}>
              <p className="font-medium">{group}</p>
              <p className="text-muted-foreground">{items.map((t) => t.label).join(" · ")}</p>
            </div>
          ))}
          <p className="text-muted-foreground">
            Owner-run businesses with at least {minReviews} Google reviews (busy enough to pay), whose customers search
            Google on a phone and where one customer is worth far more than a website costs. High-value types (trades, dentists, venues, driving schools) are offered the premium price.
          </p>
        </div>
      </details>
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

function SearchForm({ disabled, onStarted }: { disabled: boolean; onStarted: (jobId: number) => void }) {
  const client = useQueryClient();
  const meta = useMeta();
  const settings = useSettings();
  const runtime = settings.data?.runtime;
  const callsPerDay = runtime?.offers.calls_per_day ?? 150;

  const form = useForm<SearchFormInput, unknown, SearchFormValues>({
    resolver: zodResolver(searchSchema),
    defaultValues: {
      location: runtime?.general.default_city ?? "Sofia",
      target_leads: runtime?.search.default_max_results ?? callsPerDay,
      max_queries: 60,
      use_neighborhoods: true,
      audit_websites: true,
    },
  });

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
      toast.success("Finding leads…");
      onStarted(job.id);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const errors = form.formState.errors;
  const target = typeof values.target_leads === "number" && Number.isFinite(values.target_leads) ? values.target_leads : 0;
  const days = target > 0 ? target / callsPerDay : 0;

  return (
    <Card>
      <form
        className="grid gap-3 p-3"
        noValidate
        onSubmit={form.handleSubmit((v) => start.mutate(toSearchRequest(v)))}
        aria-label="Find leads"
      >
        <div className="grid grid-cols-[1fr_7rem] gap-3">
          <div className="grid gap-1">
            <Label htmlFor="location">City</Label>
            <Input id="location" list="city-suggestions" aria-invalid={!!errors.location} {...form.register("location")} />
            <datalist id="city-suggestions">
              {Object.keys(meta.data?.cities ?? {}).map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            {errors.location && <p className="text-xs text-bad">{errors.location.message}</p>}
          </div>
          <div className="grid gap-1">
            <Label htmlFor="target_leads">Leads</Label>
            <Input
              id="target_leads"
              type="number"
              min={1}
              max={2000}
              aria-invalid={!!errors.target_leads}
              {...form.register("target_leads", { valueAsNumber: true })}
            />
          </div>
        </div>
        {errors.target_leads ? (
          <p className="-mt-2 text-xs text-bad">{errors.target_leads.message}</p>
        ) : (
          days > 0 && (
            <p className="-mt-2 text-xs text-muted-foreground">
              ≈ {days < 1 ? `${Math.round(days * callsPerDay)} calls` : `${+days.toFixed(1)} day${days === 1 ? "" : "s"} of calls`} at{" "}
              {callsPerDay}/day
            </p>
          )
        )}

        <details className="text-[13px]">
          <summary className="cursor-pointer text-xs text-muted-foreground">Options</summary>
          <div className="mt-2 grid gap-2">
            <label className="flex items-center gap-2">
              <Controller
                control={form.control}
                name="use_neighborhoods"
                render={({ field }) => <Switch checked={field.value} onCheckedChange={field.onChange} />}
              />
              Go neighborhood by neighborhood when the city is used up
            </label>
            <label className="flex items-center gap-2">
              <Controller
                control={form.control}
                name="audit_websites"
                render={({ field }) => <Switch checked={field.value} onCheckedChange={field.onChange} />}
              />
              Check websites (finds broken and outdated sites)
            </label>
            <div className="flex items-center gap-2">
              <Input
                id="max_queries"
                type="number"
                min={1}
                max={200}
                className="w-20"
                aria-label="Max queries"
                {...form.register("max_queries", { valueAsNumber: true })}
              />
              <span className="text-xs text-muted-foreground">max queries (cost cap, each = up to 3 requests)</span>
            </div>
          </div>
        </details>

        <EstimateLine loading={estimate.isFetching} data={estimate.data} />

        <Button type="submit" size="lg" disabled={disabled || start.isPending || estimate.data?.queries === 0}>
          <SearchIcon /> {start.isPending ? "Starting…" : `Find ${target || ""} leads`}
        </Button>
      </form>
    </Card>
  );
}

function EstimateLine({ loading, data }: { loading: boolean; data: Awaited<ReturnType<typeof api.estimateSearch>> | undefined }) {
  if (!data) return <p className="text-xs text-muted-foreground">{loading ? "Estimating cost…" : " "}</p>;
  if (data.queries === 0) {
    return (
      <p className="text-xs text-warm" aria-live="polite">
        Every search for this city ran in the last 30 days. Try another city or turn on neighborhoods.
      </p>
    );
  }
  if (data.demo_mode) return <p className="text-xs text-muted-foreground">Demo mode: synthetic results, no API cost.</p>;
  return (
    <p className="text-xs text-muted-foreground" aria-live="polite">
      Up to {data.queries} new {data.queries === 1 ? "query" : "queries"} / {data.max_requests} request
      {data.max_requests === 1 ? "" : "s"} — stops as soon as it has enough leads
      {data.estimated_max_cost !== null && (
        <>
          {" "}· max ≈ <span className="font-medium text-foreground">{formatMoney(data.estimated_max_cost_display, data.display_currency)}</span>
          {data.free_units_remaining !== null && data.free_units_remaining > 0 && ` (${data.free_units_remaining} free requests left this month)`}
        </>
      )}
      .
    </p>
  );
}

interface CategoryTotal {
  category: LeadCategory;
  count: number;
  value: number;
}

function totalsByCategory(leads: LeadSummary[]): CategoryTotal[] {
  const map = new Map<LeadCategory, CategoryTotal>();
  for (const lead of leads) {
    const category = lead.lead_category ?? "UNCHECKED";
    const row = map.get(category) ?? { category, count: 0, value: 0 };
    row.count += 1;
    row.value += lead.deal_value;
    map.set(category, row);
  }
  const order = [...SELLABLE_CATEGORIES, "UNCHECKED", "NOT_A_FIT"] as LeadCategory[];
  return [...map.values()].sort((a, b) => order.indexOf(a.category) - order.indexOf(b.category));
}

function JobResults({ jobId, onRetried }: { jobId: number; onRetried: (id: number) => void }) {
  const navigate = useNavigate();
  const job = useSearchJob(jobId);
  const [showFiltered, setShowFiltered] = useState(false);
  const [only, setOnly] = useState<LeadCategory | null>(null);
  const active = job.data ? ACTIVE_JOB_STATUSES.includes(job.data.status) : false;
  const query: LeadListQuery = {
    job_id: jobId,
    job_matched_only: !showFiltered,
    sort: "expected_value",
    order: "desc",
    page_size: 200,
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
  const filteredOut = Number(job.data.counters.filtered_out ?? 0) + Number(job.data.counters.dropped_after_audit ?? 0);
  const items = leads.data?.items ?? [];
  const totals = totalsByCategory(items);
  const pipeline = items.reduce((sum, l) => sum + l.deal_value, 0);
  const shown = only ? items.filter((l) => (l.lead_category ?? "UNCHECKED") === only) : items;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[13px] font-semibold">
          {jobTitle(job.data.params)}
          {pipeline > 0 && (
            <span className="font-normal text-muted-foreground">
              {" "}· €{pipeline.toLocaleString()} in offers
            </span>
          )}
        </h2>
        <div className="flex items-center gap-2">
          {filteredOut > 0 && (
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Switch checked={showFiltered} onCheckedChange={setShowFiltered} /> Show {filteredOut} skipped
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
      {totals.length > 0 && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by category">
          {totals.map((t) => (
            <button
              key={t.category}
              type="button"
              aria-pressed={only === t.category}
              onClick={() => setOnly(only === t.category ? null : t.category)}
              className={cn(
                "rounded-md border px-2 py-1 text-left text-xs transition-colors hover:bg-accent",
                only === t.category && "border-foreground bg-accent",
              )}
            >
              <span className="font-medium">{CATEGORY_LABELS[t.category]}</span>{" "}
              <span className="tabular text-muted-foreground">
                {t.count}
                {t.value > 0 && ` · €${t.value.toLocaleString()}`}
              </span>
            </button>
          ))}
        </div>
      )}
      {leads.data && items.length === 0 && !active ? (
        <Card>
          <EmptyState
            title="No new leads this time"
            description="Everything found was a chain, closed, already in your list or already has a good website. Click Find leads again — it moves on to the next business types."
          />
        </Card>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3" aria-busy={active}>
          {shown.map((lead) => (
            <ResultCard key={lead.id} lead={lead} onOpen={() => navigate(`/leads/${lead.id}`)} />
          ))}
          {!leads.data && Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-36" />)}
        </div>
      )}
      {leads.data && leads.data.total > items.length && (
        <p className="text-xs text-muted-foreground">
          Showing {items.length} of {leads.data.total}.{" "}
          <Link to={`/leads?job_id=${jobId}`} className="underline">
            See all in the lead table
          </Link>
        </p>
      )}
    </div>
  );
}

function ResultCard({ lead, onOpen }: { lead: LeadSummary; onOpen: () => void }) {
  const category = lead.lead_category;
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
          <CategoryBadge category={category} />
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
      <dl className="grid grid-cols-[4.5rem_1fr] gap-x-2 gap-y-1 text-xs">
        <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Sell</dt>
        <dd className="flex min-w-0 items-center justify-between gap-2">
          <span className="truncate font-medium">{category ? OFFER_LABELS[category] : "—"}</span>
          <DealValue value={lead.deal_value} odds={lead.close_odds} />
        </dd>
        <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Website</dt>
        <dd className="min-w-0 truncate">
          <WebsiteCell lead={lead} />
          {lead.website_health_score !== null && <span className="ml-1 text-muted-foreground">· health {lead.website_health_score}</span>}
        </dd>
      </dl>
      {lead.top_reason && <p className="line-clamp-1 text-xs text-muted-foreground">Why: {lead.top_reason}</p>}
    </Card>
  );
}
