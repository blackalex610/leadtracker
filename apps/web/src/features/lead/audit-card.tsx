import type { AuditOut, LeadDetail } from "@leadtracker/shared";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangleIcon, CheckCircle2Icon, Loader2Icon, RefreshCwIcon } from "lucide-react";
import { toast } from "sonner";

import { HealthScore } from "@/components/app/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, errorMessage } from "@/lib/api";
import { displayDomain, healthTone, relativeTime } from "@/lib/format";
import { useInvalidateLeads } from "@/lib/queries";
import { cn } from "@/lib/utils";

interface Signal {
  code: string;
  category: string;
  severity: string;
  label: string;
  detail?: string | null;
  penalty: number;
}
interface CategoryScore {
  label: string;
  score: number;
  max: number;
}
interface OutdatedSignal {
  code: string;
  label: string;
  points: number;
  detail?: string | null;
}

const CATEGORY_ORDER = ["technical", "mobile", "conversion", "content", "trust"];
const TONE_BG = { bad: "bg-bad", ok: "bg-ok", good: "bg-good", none: "bg-muted-foreground" } as const;

function asSignals(audit: AuditOut): Signal[] {
  return (audit.signals as unknown as Signal[]).filter((s) => s.penalty > 0);
}

export function AuditCard({ lead }: { lead: LeadDetail }) {
  const invalidate = useInvalidateLeads();
  const run = useMutation({
    mutationFn: () => api.auditLead(lead.id),
    onSuccess: () => {
      toast("Website audit started");
      invalidate(lead.id);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const running = !!lead.active_job_id || run.isPending;
  const audit = lead.audit;
  const auditable = !!lead.website_url && lead.website_kind === "own";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Website audit</CardTitle>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {audit?.finished_at && !running && <span>Audited {relativeTime(audit.finished_at)}</span>}
          {auditable && (
            <Button size="xs" variant="outline" onClick={() => run.mutate()} disabled={running}>
              {running ? <Loader2Icon className="animate-spin" /> : <RefreshCwIcon />}
              {running ? "Auditing…" : audit ? "Re-run audit" : "Run audit"}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {!lead.website_url ? (
          <p className="text-[13px] text-muted-foreground">No website listed — nothing to audit.</p>
        ) : !auditable ? (
          <p className="text-[13px] text-muted-foreground">
            The listing links to {displayDomain(lead.website_url)} (a {lead.website_kind?.replace("_", " ")} page), not
            an own website.
          </p>
        ) : lead.website_status === "unaudited" || !audit ? (
          <p className="text-[13px] text-muted-foreground">{running ? "Audit in progress…" : "Not audited yet."}</p>
        ) : audit.status !== "success" ? (
          <AuditFailure audit={audit} />
        ) : (
          <AuditDetails audit={audit} />
        )}
      </CardContent>
    </Card>
  );
}

function AuditFailure({ audit }: { audit: AuditOut }) {
  const skipped = audit.status === "skipped";
  return (
    <div className="flex items-start gap-2" role="status">
      <AlertTriangleIcon className={cn("mt-0.5 size-4", skipped ? "text-warm" : "text-bad")} aria-hidden />
      <div className="text-[13px]">
        <p className="font-medium">{skipped ? "Website audit skipped" : "Website audit failed"}</p>
        <p className="text-muted-foreground">
          Reason: {audit.error_message ?? audit.error_code}
          {audit.http_status ? ` (HTTP ${audit.http_status})` : ""}
        </p>
        <p className="text-xs text-muted-foreground">Business data remains available.</p>
      </div>
    </div>
  );
}

function AuditDetails({ audit }: { audit: AuditOut }) {
  const signals = asSignals(audit);
  const categories = audit.category_scores as unknown as Record<string, CategoryScore>;
  const outdated = audit.outdated_signals as unknown as OutdatedSignal[];
  const facts = audit.facts as Record<string, unknown>;
  const booking = Array.isArray(facts.booking_providers) ? (facts.booking_providers as string[]) : [];
  const social = (facts.social_profiles ?? {}) as Record<string, string>;
  const phones = Array.isArray(facts.phones_on_site) ? (facts.phones_on_site as string[]) : [];
  const pagespeed = facts.pagespeed as { performance?: number | null } | undefined;

  return (
    <div className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-[auto_1fr]">
        <div className="flex gap-6">
          <div>
            <p className="text-xs text-muted-foreground">Website Health</p>
            <p className="text-2xl font-semibold">
              <HealthScore score={audit.health_score} />
              <span className="text-sm font-normal text-muted-foreground">/100</span>
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Outdated index</p>
            <p className="text-2xl font-semibold">
              {audit.outdated_score ?? "—"}
              <span className="text-sm font-normal text-muted-foreground">/100</span>
            </p>
            <p className="text-xs text-muted-foreground">{audit.outdated_band}</p>
          </div>
        </div>
        <ul className="grid gap-1" aria-label="Health by category">
          {CATEGORY_ORDER.filter((c) => categories[c]).map((c) => {
            const cat = categories[c]!;
            const pct = (cat.score / cat.max) * 100;
            return (
              <li key={c} className="grid grid-cols-[8.5rem_1fr_3rem] items-center gap-2 text-xs">
                <span className="text-muted-foreground">{cat.label}</span>
                <span className="relative h-1.5 rounded-full bg-muted">
                  <span className={cn("absolute inset-y-0 left-0 rounded-full", TONE_BG[healthTone(pct)])} style={{ width: `${pct}%` }} />
                </span>
                <span className="text-right tabular">
                  {cat.score}/{cat.max}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-muted-foreground">Problems observed ({signals.length})</p>
        {signals.length ? (
          <ul className="grid gap-1 sm:grid-cols-2">
            {signals
              .sort((a, b) => b.penalty - a.penalty)
              .map((s) => (
                <li key={s.code} className="flex items-start gap-1.5 text-[13px]">
                  <span
                    className={cn(
                      "mt-1.5 size-1.5 shrink-0 rounded-full",
                      s.severity === "critical" || s.severity === "major" ? "bg-bad" : "bg-ok",
                    )}
                    aria-hidden
                  />
                  <span>
                    {s.label}
                    {s.detail && <span className="text-muted-foreground"> — {s.detail}</span>}
                  </span>
                </li>
              ))}
          </ul>
        ) : (
          <p className="flex items-center gap-1.5 text-[13px] text-good">
            <CheckCircle2Icon className="size-4" /> No problems detected
          </p>
        )}
      </div>

      {outdated.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Outdated signals</p>
          <div className="flex flex-wrap gap-1">
            {outdated.map((o) => (
              <Badge key={o.code} variant="outline" className="font-normal" title={o.detail ?? undefined}>
                {o.label} <span className="text-muted-foreground">+{o.points}</span>
              </Badge>
            ))}
          </div>
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
        <Fact label="Final URL" value={audit.final_url ? displayDomain(audit.final_url) : "—"} />
        <Fact label="HTTPS" value={audit.https ? "Yes" : "No"} />
        <Fact label="Response" value={audit.response_time_ms ? `${(audit.response_time_ms / 1000).toFixed(1)}s` : "—"} />
        <Fact label="Pages checked" value={String(audit.pages.length)} />
        <Fact label="Booking" value={booking.length ? booking.join(", ") : facts.booking_detected ? "Detected" : "Not detected"} />
        <Fact label="Phones on site" value={phones.length ? phones.join(", ") : "None found"} />
        <Fact label="Social" value={Object.keys(social).length ? Object.keys(social).join(", ") : "None"} />
        <Fact label="Copyright" value={facts.copyright_year ? String(facts.copyright_year) : "—"} />
        {pagespeed?.performance !== undefined && (
          <Fact label="PageSpeed (mobile)" value={pagespeed.performance === null ? "—" : String(pagespeed.performance)} />
        )}
      </dl>
      <p className="text-[11px] text-muted-foreground">
        Heuristic audit of the homepage and up to a few linked pages (robots.txt respected). Mobile checks detect
        obvious problems only{pagespeed ? "" : " — enable PageSpeed Insights in Settings for Lighthouse data"}.
      </p>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate font-medium" title={value}>
        {value}
      </dd>
    </div>
  );
}
