import {
  JOB_STATUS_LABELS,
  LEAD_STATUSES,
  OUTCOME_LABELS,
  STATUS_LABELS,
  type CallOutcome,
  type Dashboard,
  type JobStatus,
  type LeadStatus,
  type LeadSummary,
} from "@leadtracker/shared";
import { ArrowRightIcon, SearchIcon } from "lucide-react";
import { Link, useNavigate } from "react-router";

import { CategoryBadge, DealValue } from "@/components/app/badges";
import { BarList } from "@/components/app/bar-list";
import { PhoneLink } from "@/components/app/phone";
import { StartCallingDialog } from "@/components/app/start-calling-dialog";
import { EmptyState, ErrorState, InlineNotice, PageHeader } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime, formatMoney, formatNumber, jobTitle, relativeTime } from "@/lib/format";
import { useDashboard, useMeta } from "@/lib/queries";
import { cn } from "@/lib/utils";

interface Tile {
  label: string;
  value: number;
  to: string;
  hint?: string;
}

function tiles(d: Dashboard): Tile[] {
  const k = d.kpis;
  return [
    { label: "Leads discovered", value: k.total_leads, to: "/leads" },
    { label: "Hot leads", value: k.hot_leads, to: "/leads?priority=HOT" },
    { label: "No website", value: k.no_website, to: "/leads?opportunity=NO_WEBSITE" },
    { label: "Website problems", value: k.website_problems, to: "/leads?website_problems=true" },
    { label: "Google opportunities", value: k.google_opportunities, to: "/leads?google_opportunity=true" },
    { label: "Phone numbers", value: k.phones_found, to: "/leads?has_phone=true" },
    { label: "Contacted", value: k.contacted, to: "/leads?contacted=true" },
    { label: "Calls today", value: k.calls_today, to: "/leads?sort=last_contacted_at&order=desc&contacted=true" },
    { label: "Interested", value: k.interested, to: "/leads?status=INTERESTED&status=QUALIFIED&status=PROPOSAL" },
    { label: "Callbacks due", value: k.callbacks_due, to: "/leads?callback_due=true&sort=next_callback_at&order=asc" },
  ];
}

function StatTile({ tile }: { tile: Tile }) {
  return (
    <Link
      to={tile.to}
      className="group flex flex-col gap-0.5 rounded-md border bg-card px-3 py-2 outline-none transition-colors hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring/40"
    >
      <span className="truncate text-xs text-muted-foreground">{tile.label}</span>
      <span className="text-xl font-semibold leading-7">{formatNumber(tile.value)}</span>
    </Link>
  );
}

function LeadMiniRow({ lead, right }: { lead: LeadSummary; right?: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[auto_1fr_auto] items-center gap-2 border-b px-3 py-1.5 last:border-0">
      <CategoryBadge category={lead.lead_category} />
      <div className="min-w-0">
        <Link to={`/leads/${lead.id}`} className="block truncate font-medium hover:underline">
          {lead.name}
        </Link>
        <p className="truncate text-xs text-muted-foreground">{lead.top_reason ?? lead.category ?? "—"}</p>
      </div>
      <div className="flex flex-col items-end gap-0.5 text-xs">
        <PhoneLink
          phone={lead.normalized_phone}
          display={lead.international_phone}
          isDemo={lead.is_demo}
          invalid={lead.phone_invalid}
          suppressed={lead.suppressed}
        />
        {right}
      </div>
    </li>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const dashboard = useDashboard();
  const meta = useMeta();
  const provider = meta.data?.provider;
  const d = dashboard.data;

  return (
    <div className="flex flex-col">
      <PageHeader
        title="Dashboard"
        description="Who to call, why, and what it cost"
        actions={
          <>
            <Button size="sm" variant="outline" asChild>
              <Link to="/search">
                <SearchIcon /> Find leads
              </Link>
            </Button>
            <StartCallingDialog />
          </>
        }
      />
      <div className="flex flex-col gap-4 p-5">
        {provider && !provider.configured && !provider.demo_mode && (
          <InlineNotice
            tone="warning"
            title="Provider not configured"
            action={
              <Button size="xs" variant="outline" asChild>
                <Link to="/settings?tab=provider">Setup</Link>
              </Button>
            }
          >
            Set <code>PROVIDER_API_KEY</code> (Google Places API (New)) on the backend to search real businesses.
            Existing and imported leads keep working.
          </InlineNotice>
        )}

        {dashboard.error ? (
          <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
        ) : (
          <>
            {d && <GoalCard goal={d.goal} />}

            <section aria-label="Key figures" className="grid grid-cols-2 gap-2 sm:grid-cols-5 2xl:grid-cols-10">
              {d
                ? tiles(d).map((t) => <StatTile key={t.label} tile={t} />)
                : Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="h-[58px]" />)}
            </section>

            {d && d.kpis.total_leads === 0 ? (
              <Card>
                <EmptyState
                  icon={SearchIcon}
                  title="No leads yet"
                  description="Pick a city on Find leads and click once — it finds businesses that need a website and sorts them by deal value."
                  action={
                    <div className="flex gap-2">
                      <Button size="sm" asChild>
                        <Link to="/search">Find leads</Link>
                      </Button>
                      <Button size="sm" variant="outline" asChild>
                        <Link to="/leads/import">Import CSV</Link>
                      </Button>
                    </div>
                  }
                />
              </Card>
            ) : (
              <>
                <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
                  <Card>
                    <CardHeader>
                      <CardTitle>Call these first</CardTitle>
                      <Link to="/leads?contacted=false&sort=expected_value&order=desc" className="text-xs text-muted-foreground hover:underline">
                        All uncalled, best deals first <ArrowRightIcon className="inline size-3" />
                      </Link>
                    </CardHeader>
                    {d ? (
                      d.top_hot.length ? (
                        <ul>
                          {d.top_hot.map((lead) => (
                            <LeadMiniRow key={lead.id} lead={lead} right={<DealValue value={lead.deal_value} odds={lead.close_odds} />} />
                          ))}
                        </ul>
                      ) : (
                        <EmptyState title="Nobody left to call" description="Click Find leads for a fresh batch." />
                      )
                    ) : (
                      <div className="space-y-2 p-3">
                        {Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-9" />)}
                      </div>
                    )}
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle>Callbacks due</CardTitle>
                      <span className="text-xs text-muted-foreground">{d ? `${d.callbacks.length} shown` : ""}</span>
                    </CardHeader>
                    {d?.callbacks.length ? (
                      <ul>
                        {d.callbacks.map((lead) => (
                          <LeadMiniRow
                            key={lead.id}
                            lead={lead}
                            right={
                              <span className={cn("text-muted-foreground", new Date(lead.next_callback_at ?? 0) < new Date() && "text-bad")}>
                                {relativeTime(lead.next_callback_at)}
                              </span>
                            }
                          />
                        ))}
                      </ul>
                    ) : (
                      <EmptyState title="Nothing due today" />
                    )}
                  </Card>
                </div>

                <div className="grid gap-4 lg:grid-cols-3">
                  <Card>
                    <CardHeader>
                      <CardTitle>Ready to call, by what to sell</CardTitle>
                      <span className="text-xs text-muted-foreground">uncalled leads</span>
                    </CardHeader>
                    <CardContent className={cn(dashboard.isFetching && "opacity-80")}>
                      <BarList
                        emptyLabel="No uncalled leads"
                        data={(d?.by_category ?? []).map((c) => ({
                          key: c.key,
                          label: c.deal_value ? `${c.label} · €${c.deal_value.toLocaleString()}` : c.label,
                          value: c.count,
                        }))}
                        onSelect={(key) => navigate(`/leads?lead_category=${key}&contacted=false`)}
                      />
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle>Calls by outcome</CardTitle>
                      <span className="text-xs text-muted-foreground">last 30 days</span>
                    </CardHeader>
                    <CardContent>
                      <BarList
                        emptyLabel="No calls logged yet"
                        data={(d?.calls_by_outcome ?? []).map((o) => ({
                          key: o.key,
                          label: OUTCOME_LABELS[o.key as CallOutcome] ?? o.key,
                          value: o.count,
                        }))}
                      />
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle>Lead pipeline</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <BarList
                        data={LEAD_STATUSES.map((status) => ({
                          key: status,
                          label: STATUS_LABELS[status as LeadStatus],
                          value: d?.pipeline.find((p) => p.key === status)?.count ?? 0,
                        }))}
                        onSelect={(key) => navigate(`/leads?status=${key}`)}
                      />
                    </CardContent>
                  </Card>
                </div>
              </>
            )}

            <div className="grid gap-4 lg:grid-cols-[2fr_3fr]">
              <Card>
                <CardHeader>
                  <CardTitle>This month</CardTitle>
                  <Link to="/settings?tab=pricing" className="text-xs text-muted-foreground hover:underline">
                    Pricing
                  </Link>
                </CardHeader>
                <CardContent>
                  {d ? <MonthUsage month={d.month} /> : <Skeleton className="h-24" />}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Recent searches</CardTitle>
                  <Link to="/campaigns?tab=searches" className="text-xs text-muted-foreground hover:underline">
                    History
                  </Link>
                </CardHeader>
                {d?.recent_jobs.length ? (
                  <ul>
                    {d.recent_jobs.map((job) => (
                      <li key={job.id} className="flex items-center justify-between gap-2 border-b px-3 py-1.5 last:border-0">
                        <Link to={`/search?job=${job.id}`} className="min-w-0 truncate hover:underline">
                          {jobTitle(job.params)}
                        </Link>
                        <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                          <span className="tabular">{job.progress_total} found</span>
                          <Badge variant="muted">{JOB_STATUS_LABELS[job.status as JobStatus] ?? job.status}</Badge>
                          {formatDateTime(job.created_at)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState title="No searches yet" />
                )}
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function MonthUsage({ month }: { month: Dashboard["month"] }) {
  const cost = month.cost;
  const rows: [string, string][] = [
    ["Searches", formatNumber(month.searches)],
    ["Businesses", formatNumber(month.businesses)],
    ["Phone numbers", formatNumber(month.phone_numbers)],
    ["Website audits", formatNumber(month.website_audits)],
    ["API calls", `${formatNumber(month.api_calls)} (+${formatNumber(month.cached_calls)} cached)`],
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="text-right font-medium tabular">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-col justify-center rounded-md bg-muted/50 px-4 py-2 text-right">
        <span className="text-xs text-muted-foreground">Estimated API cost</span>
        <span className="text-2xl font-semibold">{formatMoney(cost.display_total, cost.display_currency)}</span>
        <span className="text-xs text-muted-foreground">
          {formatMoney(cost.total, cost.currency)} after free tier
        </span>
      </div>
    </div>
  );
}

/** The weekly money goal: won so far, what's in play, and whether the calls are on pace. */
function GoalCard({ goal }: { goal: Dashboard["goal"] }) {
  const target = goal.weekly_goal;
  const won = goal.won_value_7d;
  const percent = target > 0 ? Math.min(100, (won / target) * 100) : 0;
  const callsTarget = goal.calls_per_day * 7;
  const left = Math.max(0, target - won);
  return (
    <Card>
      <CardContent className="grid gap-3 py-3 md:grid-cols-[2fr_1fr_1fr_1fr] md:items-center">
        <div className="grid gap-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[13px] font-medium">7-day goal</span>
            <span className="text-xs text-muted-foreground tabular">
              <span className="text-lg font-semibold text-foreground">€{won.toLocaleString()}</span> / €{target.toLocaleString()}
            </span>
          </div>
          <Progress value={percent} aria-label="Revenue goal progress" />
          <span className="text-xs text-muted-foreground">
            {left > 0
              ? `€${left.toLocaleString()} to go · ${goal.won_count_7d} deal${goal.won_count_7d === 1 ? "" : "s"} won (mark a lead Won to count it)`
              : "Goal reached — keep going"}
          </span>
        </div>
        <GoalStat label="In play" value={`€${goal.in_play_value.toLocaleString()}`} hint={`${goal.in_play_count} interested / proposal`} to="/leads?status=INTERESTED&status=QUALIFIED&status=PROPOSAL" />
        <GoalStat label="Calls, last 7 days" value={`${formatNumber(goal.calls_7d)} / ${formatNumber(callsTarget)}`} hint={`target ${goal.calls_per_day}/day`} />
        <GoalStat label="Ready to call" value={formatNumber(goal.ready_leads)} hint={`≈ €${goal.ready_expected_value.toLocaleString()} expected`} to="/leads?contacted=false&sort=expected_value&order=desc" />
      </CardContent>
    </Card>
  );
}

function GoalStat({ label, value, hint, to }: { label: string; value: string; hint: string; to?: string }) {
  const body = (
    <>
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-lg font-semibold leading-6 tabular">{value}</span>
      <span className="text-[11px] text-muted-foreground">{hint}</span>
    </>
  );
  return to ? (
    <Link to={to} className="flex flex-col rounded-md px-2 py-1 hover:bg-accent/50">
      {body}
    </Link>
  ) : (
    <div className="flex flex-col px-2 py-1">{body}</div>
  );
}
