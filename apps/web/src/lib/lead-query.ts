import {
  LEAD_STATUSES,
  OPPORTUNITY_TYPES,
  PRIORITIES,
  SORT_LABELS,
  type LeadListQuery,
  type LeadStatus,
  type OpportunityType,
  type Priority,
  type SortField,
} from "@leadtracker/shared";

const BOOL_KEYS = [
  "has_phone",
  "has_website",
  "website_problems",
  "google_opportunity",
  "contacted",
  "open_in_window",
  "callback_due",
] as const;
type BoolKey = (typeof BOOL_KEYS)[number];

function parseBool(value: string | null): boolean | undefined {
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

function parseNumber(value: string | null): number | undefined {
  if (value === null || value === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

/** URL search params → typed lead query (unknown values are dropped). */
export function parseLeadQuery(params: URLSearchParams): LeadListQuery {
  const query: LeadListQuery = {};
  const q = params.get("q");
  if (q) query.q = q;
  const priority = params.getAll("priority").filter((p): p is Priority => PRIORITIES.includes(p as Priority));
  if (priority.length) query.priority = priority;
  const status = params.getAll("status").filter((s): s is LeadStatus => LEAD_STATUSES.includes(s as LeadStatus));
  if (status.length) query.status = status;
  const opportunity = params
    .getAll("opportunity")
    .filter((o): o is OpportunityType => OPPORTUNITY_TYPES.includes(o as OpportunityType));
  if (opportunity.length) query.opportunity = opportunity;
  for (const key of ["category", "city", "niche_key", "assigned_to"] as const) {
    const value = params.get(key);
    if (value) query[key] = value;
  }
  for (const key of BOOL_KEYS) {
    const value = parseBool(params.get(key));
    if (value !== undefined) query[key as BoolKey] = value;
  }
  const minRating = parseNumber(params.get("min_rating"));
  if (minRating !== undefined) query.min_rating = minRating;
  const minReviews = parseNumber(params.get("min_reviews"));
  if (minReviews !== undefined) query.min_reviews = minReviews;
  const minScore = parseNumber(params.get("min_score"));
  if (minScore !== undefined) query.min_score = minScore;
  const jobId = parseNumber(params.get("job_id"));
  if (jobId !== undefined) query.job_id = jobId;
  const sort = params.get("sort");
  if (sort && sort in SORT_LABELS) query.sort = sort as SortField;
  const order = params.get("order");
  if (order === "asc" || order === "desc") query.order = order;
  const page = parseNumber(params.get("page"));
  if (page && page > 1) query.page = page;
  const pageSize = parseNumber(params.get("page_size"));
  if (pageSize) query.page_size = pageSize;
  return query;
}

export function serializeLeadQuery(query: LeadListQuery): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)));
    else params.set(key, String(value));
  }
  return params;
}

export interface QuickFilter {
  id: string;
  label: string;
  isActive: (q: LeadListQuery) => boolean;
  toggle: (q: LeadListQuery) => LeadListQuery;
}

function toggleArray<T>(list: T[] | undefined, value: T): T[] | undefined {
  const current = list ?? [];
  const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
  return next.length ? next : undefined;
}

function toggleBool(q: LeadListQuery, key: BoolKey, value: boolean): LeadListQuery {
  return { ...q, [key]: q[key] === value ? undefined : value, page: undefined };
}

export const QUICK_FILTERS: QuickFilter[] = [
  {
    id: "hot",
    label: "HOT",
    isActive: (q) => !!q.priority?.includes("HOT"),
    toggle: (q) => ({ ...q, priority: toggleArray(q.priority, "HOT"), page: undefined }),
  },
  {
    id: "warm",
    label: "WARM",
    isActive: (q) => !!q.priority?.includes("WARM"),
    toggle: (q) => ({ ...q, priority: toggleArray(q.priority, "WARM"), page: undefined }),
  },
  {
    id: "no-website",
    label: "No website",
    isActive: (q) => !!q.opportunity?.includes("NO_WEBSITE"),
    toggle: (q) => ({ ...q, opportunity: toggleArray(q.opportunity, "NO_WEBSITE"), page: undefined }),
  },
  {
    id: "bad-website",
    label: "Bad website",
    isActive: (q) => q.website_problems === true,
    toggle: (q) => toggleBool(q, "website_problems", true),
  },
  {
    id: "google",
    label: "Google opportunity",
    isActive: (q) => q.google_opportunity === true,
    toggle: (q) => toggleBool(q, "google_opportunity", true),
  },
  {
    id: "has-phone",
    label: "Has phone",
    isActive: (q) => q.has_phone === true,
    toggle: (q) => toggleBool(q, "has_phone", true),
  },
  {
    id: "uncontacted",
    label: "Uncontacted",
    isActive: (q) => q.contacted === false,
    toggle: (q) => toggleBool(q, "contacted", false),
  },
  {
    id: "contacted",
    label: "Contacted",
    isActive: (q) => q.contacted === true,
    toggle: (q) => toggleBool(q, "contacted", true),
  },
];

export function withoutPaging(query: LeadListQuery): Omit<LeadListQuery, "page" | "page_size"> {
  const { page: _page, page_size: _size, ...rest } = query;
  return rest;
}

export function activeFilterCount(query: LeadListQuery): number {
  const { sort: _s, order: _o, page: _p, page_size: _ps, ...rest } = query;
  return Object.values(rest).filter((v) => v !== undefined && !(Array.isArray(v) && v.length === 0)).length;
}
