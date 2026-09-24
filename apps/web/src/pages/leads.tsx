import {
  LEAD_STATUSES,
  OPPORTUNITY_LABELS,
  OPPORTUNITY_TYPES,
  SORT_LABELS,
  STATUS_LABELS,
  type LeadListQuery,
  type LeadStatus,
  type OpportunityType,
  type SortField,
} from "@leadtracker/shared";
import { useMutation } from "@tanstack/react-query";
import {
  ArrowDownIcon,
  ArrowUpDownIcon,
  ArrowUpIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  FilterIcon,
  RefreshCwIcon,
  SearchIcon,
  UploadIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import {
  DemoBadge,
  HealthScore,
  OpportunityScore,
  OpportunityTags,
  PriorityBadge,
  StatusBadge,
} from "@/components/app/badges";
import { PhoneLink } from "@/components/app/phone";
import { StartCallingDialog } from "@/components/app/start-calling-dialog";
import { EmptyState, ErrorState, PageHeader } from "@/components/app/states";
import { WebsiteCell } from "@/components/app/website-cell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatNumber } from "@/lib/format";
import { activeFilterCount, parseLeadQuery, QUICK_FILTERS, serializeLeadQuery, withoutPaging } from "@/lib/lead-query";
import { useFacets, useInvalidateLeads, useLeads } from "@/lib/queries";
import { cn } from "@/lib/utils";

const DEFAULT_PAGE_SIZE = 50;

export function LeadsPage() {
  const [params, setParams] = useSearchParams();
  const query = useMemo(() => parseLeadQuery(params), [params]);
  const effective: LeadListQuery = { sort: "priority", order: "desc", page_size: DEFAULT_PAGE_SIZE, ...query };
  const leads = useLeads(effective);
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const update = (next: LeadListQuery) => {
    setSelected(new Set());
    setParams(serializeLeadQuery(next), { replace: true });
  };
  const exportHref = api.exportUrl(withoutPaging(effective));
  const page = effective.page ?? 1;
  const pageSize = effective.page_size ?? DEFAULT_PAGE_SIZE;
  const total = leads.data?.total ?? 0;
  const items = leads.data?.items ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader
        title={
          <span>
            Leads{" "}
            <span className="font-normal text-muted-foreground tabular">{leads.data ? formatNumber(total) : ""}</span>
          </span>
        }
        actions={
          <>
            <Button size="sm" variant="outline" asChild>
              <Link to="/leads/import">
                <UploadIcon /> Import CSV
              </Link>
            </Button>
            <Button size="sm" variant="outline" asChild>
              <a href={exportHref} download>
                <DownloadIcon /> Export CSV
              </a>
            </Button>
            <StartCallingDialog />
          </>
        }
      />
      <FilterBar query={query} onChange={update} />
      {selected.size > 0 && (
        <BulkBar ids={[...selected]} onDone={() => setSelected(new Set())} />
      )}
      <div className={cn("min-h-0 flex-1 overflow-auto", leads.isPlaceholderData && "opacity-70")}>
        {leads.error ? (
          <ErrorState error={leads.error} onRetry={() => void leads.refetch()} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-8">
                  <Checkbox
                    aria-label="Select all on page"
                    checked={items.length > 0 && items.every((i) => selected.has(i.id))}
                    onCheckedChange={(checked) =>
                      setSelected(checked ? new Set(items.map((i) => i.id)) : new Set())
                    }
                  />
                </TableHead>
                <SortHead field="priority" query={effective} onChange={update}>Priority</SortHead>
                <SortHead field="name" query={effective} onChange={update}>Business</SortHead>
                <TableHead>Category</TableHead>
                <TableHead>Phone</TableHead>
                <SortHead field="rating" query={effective} onChange={update}>Rating</SortHead>
                <SortHead field="review_count" query={effective} onChange={update}>Reviews</SortHead>
                <TableHead>Website</TableHead>
                <SortHead field="website_score" query={effective} onChange={update}>Health</SortHead>
                <SortHead field="opportunity_score" query={effective} onChange={update}>Opportunity</SortHead>
                <TableHead className="hidden 2xl:table-cell">Location</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {leads.isPending &&
                Array.from({ length: 12 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={12}>
                      <Skeleton className="h-5" />
                    </TableCell>
                  </TableRow>
                ))}
              {items.map((lead) => (
                <TableRow
                  key={lead.id}
                  data-state={selected.has(lead.id) ? "selected" : undefined}
                  className="cursor-pointer"
                  onClick={() => navigate(`/leads/${lead.id}`)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      aria-label={`Select ${lead.name}`}
                      checked={selected.has(lead.id)}
                      onCheckedChange={(checked) => {
                        const next = new Set(selected);
                        if (checked) next.add(lead.id);
                        else next.delete(lead.id);
                        setSelected(next);
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <PriorityBadge priority={lead.priority} />
                  </TableCell>
                  <TableCell className="max-w-52">
                    <Link
                      to={`/leads/${lead.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="block truncate font-medium hover:underline"
                    >
                      {lead.name}
                    </Link>
                    <span className="flex items-center gap-1">
                      {lead.is_demo && <DemoBadge />}
                      <span className="truncate text-xs text-muted-foreground" title={lead.top_reason ?? undefined}>
                        {lead.top_reason ?? lead.address}
                      </span>
                    </span>
                  </TableCell>
                  <TableCell className="max-w-24 truncate text-muted-foreground" title={lead.category ?? undefined}>
                    {lead.category ?? "—"}
                  </TableCell>
                  <TableCell>
                    <PhoneLink
                      phone={lead.normalized_phone}
                      display={lead.international_phone}
                      isDemo={lead.is_demo}
                      invalid={lead.phone_invalid}
                      suppressed={lead.suppressed}
                    />
                  </TableCell>
                  <TableCell className="tabular">
                    {lead.rating !== null ? (
                      <>
                        {lead.rating.toFixed(1)} <span className="text-warm">★</span>
                      </>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="tabular">{formatNumber(lead.review_count)}</TableCell>
                  <TableCell>
                    <WebsiteCell lead={lead} />
                  </TableCell>
                  <TableCell>
                    <HealthScore score={lead.website_health_score} />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <OpportunityScore score={lead.opportunity_score} />
                      <OpportunityTags types={lead.opportunity_types} max={1} nowrap className="max-w-28" />
                    </div>
                  </TableCell>
                  <TableCell className="hidden max-w-28 truncate text-muted-foreground 2xl:table-cell">
                    {[lead.neighborhood, lead.city].filter(Boolean).join(", ") || "—"}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={lead.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {leads.data && items.length === 0 && (
          <EmptyState
            icon={SearchIcon}
            title={activeFilterCount(query) ? "No leads match these filters" : "No leads yet"}
            description={activeFilterCount(query) ? "Clear some filters to see more." : "Run a search or import a CSV."}
            action={
              activeFilterCount(query) ? (
                <Button size="sm" variant="outline" onClick={() => update({})}>
                  Clear filters
                </Button>
              ) : (
                <Button size="sm" asChild>
                  <Link to="/search">Find leads</Link>
                </Button>
              )
            }
          />
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t px-5 py-2 text-xs text-muted-foreground">
        <span className="tabular">
          {total === 0 ? "0" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)}`} of {formatNumber(total)}
        </span>
        <div className="flex items-center gap-2">
          <Select
            value={String(pageSize)}
            onValueChange={(v) => update({ ...query, page_size: Number(v), page: undefined })}
          >
            <SelectTrigger size="sm" className="w-24" aria-label="Rows per page">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[25, 50, 100, 200].map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n} / page
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="icon-sm"
            variant="outline"
            aria-label="Previous page"
            disabled={page <= 1}
            onClick={() => update({ ...query, page: page - 1 > 1 ? page - 1 : undefined })}
          >
            <ChevronLeftIcon />
          </Button>
          <Button
            size="icon-sm"
            variant="outline"
            aria-label="Next page"
            disabled={page * pageSize >= total}
            onClick={() => update({ ...query, page: page + 1 })}
          >
            <ChevronRightIcon />
          </Button>
        </div>
      </div>
    </div>
  );
}

function SortHead({ field, query, onChange, children }: {
  field: SortField;
  query: LeadListQuery;
  onChange: (q: LeadListQuery) => void;
  children: React.ReactNode;
}) {
  const active = (query.sort ?? "priority") === field;
  const order = query.order ?? "desc";
  const Icon = !active ? ArrowUpDownIcon : order === "desc" ? ArrowDownIcon : ArrowUpIcon;
  return (
    <TableHead aria-sort={active ? (order === "desc" ? "descending" : "ascending") : "none"}>
      <button
        type="button"
        className={cn("inline-flex items-center gap-1 uppercase hover:text-foreground", active && "text-foreground")}
        onClick={() =>
          onChange({
            ...query,
            sort: field,
            order: active && order === "desc" ? "asc" : "desc",
            page: undefined,
          })
        }
      >
        {children}
        <Icon className="size-3" aria-hidden />
      </button>
    </TableHead>
  );
}

function FilterBar({ query, onChange }: { query: LeadListQuery; onChange: (q: LeadListQuery) => void }) {
  const [text, setText] = useState(query.q ?? "");
  // Keep the box in sync when the URL changes elsewhere (back button, "Clear").
  const [syncedQ, setSyncedQ] = useState(query.q);
  if (query.q !== syncedQ) {
    setSyncedQ(query.q);
    setText(query.q ?? "");
  }
  useEffect(() => {
    const id = setTimeout(() => {
      if ((query.q ?? "") !== text) onChange({ ...query, q: text || undefined, page: undefined });
    }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const count = activeFilterCount(query);
  return (
    <div className="flex flex-wrap items-center gap-2 border-b px-5 py-2">
      <div className="relative w-64">
        <SearchIcon className="absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Search name, phone, address, domain"
          className="h-7 pl-7 text-xs"
          aria-label="Search leads"
        />
      </div>
      <div className="flex flex-wrap gap-1" role="group" aria-label="Quick filters">
        {QUICK_FILTERS.map((f) => {
          const on = f.isActive(query);
          return (
            <button
              key={f.id}
              type="button"
              aria-pressed={on}
              onClick={() => onChange(f.toggle(query))}
              className={cn(
                "h-7 rounded-md border px-2 text-xs font-medium transition-colors",
                on ? "border-foreground bg-foreground text-background" : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          );
        })}
      </div>
      <MoreFilters query={query} onChange={onChange} />
      <div className="ml-auto flex items-center gap-2">
        {query.job_id && (
          <Badge variant="outline" className="gap-1">
            Search #{query.job_id}
            <button type="button" aria-label="Remove search filter" onClick={() => onChange({ ...query, job_id: undefined })}>
              <XIcon />
            </button>
          </Badge>
        )}
        {count > 0 && (
          <Button size="xs" variant="ghost" onClick={() => onChange({ sort: query.sort, order: query.order })}>
            Clear ({count})
          </Button>
        )}
        <Select
          value={query.sort ?? "priority"}
          onValueChange={(v) => onChange({ ...query, sort: v as SortField, page: undefined })}
        >
          <SelectTrigger size="sm" className="w-40" aria-label="Sort by">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(SORT_LABELS) as SortField[]).map((s) => (
              <SelectItem key={s} value={s}>
                Sort: {SORT_LABELS[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

function MultiToggle<T extends string>({ label, options, value, onChange }: {
  label: string;
  options: { value: T; label: string }[];
  value: T[] | undefined;
  onChange: (v: T[] | undefined) => void;
}) {
  const current = value ?? [];
  return (
    <div className="grid gap-1">
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-1">
        {options.map((o) => {
          const on = current.includes(o.value);
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={on}
              onClick={() => {
                const next = on ? current.filter((v) => v !== o.value) : [...current, o.value];
                onChange(next.length ? next : undefined);
              }}
              className={cn(
                "rounded border px-1.5 py-0.5 text-[11px]",
                on ? "border-foreground bg-foreground text-background" : "hover:bg-accent",
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function MoreFilters({ query, onChange }: { query: LeadListQuery; onChange: (q: LeadListQuery) => void }) {
  const facets = useFacets();
  const set = (patch: Partial<LeadListQuery>) => onChange({ ...query, ...patch, page: undefined });
  const numberValue = (v: number | null | undefined) => (v === undefined || v === null ? "" : String(v));
  const parseNum = (s: string) => (s === "" ? undefined : Number(s));
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="xs" variant="outline" className="h-7">
          <FilterIcon /> Filters
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96" align="start">
        <div className="grid gap-3">
          <MultiToggle<LeadStatus>
            label="Status"
            options={LEAD_STATUSES.map((s) => ({ value: s, label: STATUS_LABELS[s] }))}
            value={query.status}
            onChange={(status) => set({ status })}
          />
          <MultiToggle<OpportunityType>
            label="Opportunity (any of)"
            options={OPPORTUNITY_TYPES.map((o) => ({ value: o, label: OPPORTUNITY_LABELS[o] }))}
            value={query.opportunity}
            onChange={(opportunity) => set({ opportunity })}
          />
          <div className="grid grid-cols-2 gap-2">
            <div className="grid gap-1">
              <Label>Category</Label>
              <Select value={query.category ?? "__any"} onValueChange={(v) => set({ category: v === "__any" ? undefined : v })}>
                <SelectTrigger size="sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__any">Any</SelectItem>
                  {facets.data?.categories.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.value} ({c.count})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1">
              <Label>City</Label>
              <Select value={query.city ?? "__any"} onValueChange={(v) => set({ city: v === "__any" ? undefined : v })}>
                <SelectTrigger size="sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__any">Any</SelectItem>
                  {facets.data?.cities.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.value} ({c.count})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="grid gap-1">
              <Label htmlFor="f-rating">Min rating</Label>
              <Input id="f-rating" type="number" step="0.1" className="h-7" value={numberValue(query.min_rating)}
                onChange={(e) => set({ min_rating: parseNum(e.target.value) })} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="f-reviews">Min reviews</Label>
              <Input id="f-reviews" type="number" className="h-7" value={numberValue(query.min_reviews)}
                onChange={(e) => set({ min_reviews: parseNum(e.target.value) })} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="f-score">Min score</Label>
              <Input id="f-score" type="number" className="h-7" value={numberValue(query.min_score)}
                onChange={(e) => set({ min_score: parseNum(e.target.value) })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="flex items-center gap-2 text-xs">
              <Checkbox checked={query.open_in_window === true}
                onCheckedChange={(v) => set({ open_in_window: v === true ? true : undefined })} />
              Open during calling window
            </label>
            <label className="flex items-center gap-2 text-xs">
              <Checkbox checked={query.has_website === true}
                onCheckedChange={(v) => set({ has_website: v === true ? true : undefined })} />
              Has own website
            </label>
            <label className="flex items-center gap-2 text-xs">
              <Checkbox checked={query.callback_due === true}
                onCheckedChange={(v) => set({ callback_due: v === true ? true : undefined })} />
              Callback due
            </label>
            <label className="flex items-center gap-2 text-xs">
              <Checkbox checked={query.assigned_to === "me"}
                onCheckedChange={(v) => set({ assigned_to: v === true ? "me" : undefined })} />
              Assigned to me
            </label>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function BulkBar({ ids, onDone }: { ids: number[]; onDone: () => void }) {
  const invalidate = useInvalidateLeads();
  const { user } = useAuth();
  const bulk = useMutation({
    mutationFn: api.bulkUpdate,
    onSuccess: (r) => {
      invalidate();
      toast.success(`Updated ${r.updated} lead(s)${r.skipped ? `, skipped ${r.skipped} on the do-not-contact list` : ""}`);
      onDone();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const audit = useMutation({
    mutationFn: () => api.auditMany(ids),
    onSuccess: () => {
      toast.success("Website audits queued");
      onDone();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <div className="flex items-center gap-2 border-b bg-muted/40 px-5 py-1.5 text-xs">
      <span className="font-medium">{ids.length} selected</span>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="xs" variant="outline">Set status</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>Set status</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {LEAD_STATUSES.map((s) => (
            <DropdownMenuItem key={s} onSelect={() => bulk.mutate({ ids, status: s })}>
              {STATUS_LABELS[s]}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      {user && (
        <Button size="xs" variant="outline" onClick={() => bulk.mutate({ ids, assigned_to_id: user.id })}>
          Assign to me
        </Button>
      )}
      <Button size="xs" variant="outline" onClick={() => audit.mutate()} disabled={audit.isPending}>
        <RefreshCwIcon /> Re-audit websites
      </Button>
      <Button size="xs" variant="ghost" onClick={onDone}>
        Clear selection
      </Button>
    </div>
  );
}
