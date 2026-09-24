import type { LeadDetail } from "@leadtracker/shared";
import { CheckIcon, MinusIcon } from "lucide-react";

import { Rating } from "@/components/app/badges";
import { PhoneLink } from "@/components/app/phone";
import { WebsiteCell } from "@/components/app/website-cell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const TODAY = new Date().toLocaleDateString("en-US", { weekday: "long" });

export function BusinessCard({ lead }: { lead: LeadDetail }) {
  const hours = (lead.opening_hours?.weekday_descriptions ?? []) as string[];
  const checklist = lead.data_quality_checklist;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Business</CardTitle>
        {lead.business_status && lead.business_status !== "OPERATIONAL" && (
          <Badge variant="hot">{lead.business_status.replaceAll("_", " ").toLowerCase()}</Badge>
        )}
      </CardHeader>
      <CardContent className="grid gap-3 text-[13px]">
        <dl className="grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-1.5">
          <dt className="text-muted-foreground">Phone</dt>
          <dd className="grid gap-0.5">
            {lead.contacts.length ? (
              lead.contacts.map((c) => (
                <span key={c.id} className="flex flex-wrap items-center gap-1.5">
                  <PhoneLink
                    phone={c.normalized_phone}
                    display={c.international_format}
                    isDemo={lead.is_demo}
                    invalid={c.invalid}
                    suppressed={lead.suppressed}
                  />
                  <span className="text-xs text-muted-foreground">
                    {c.phone_type?.replaceAll("_", " ")} · {c.phone_source.replace("_", " ")}
                  </span>
                  {c.phone_verified && <Badge variant="good">verified</Badge>}
                  {c.invalid && <Badge variant="hot">wrong number</Badge>}
                </span>
              ))
            ) : (
              <span className="text-muted-foreground">{lead.phone_raw ? `${lead.phone_raw} (could not validate)` : "—"}</span>
            )}
          </dd>
          <dt className="text-muted-foreground">Address</dt>
          <dd>{lead.address ?? "—"}</dd>
          <dt className="text-muted-foreground">Rating</dt>
          <dd>
            <Rating rating={lead.rating} reviews={lead.review_count} />
          </dd>
          <dt className="text-muted-foreground">Website</dt>
          <dd>
            <WebsiteCell lead={lead} />
          </dd>
          <dt className="text-muted-foreground">Hours</dt>
          <dd>
            {hours.length ? (
              <ul className="grid gap-px text-xs">
                {hours.map((h) => (
                  <li key={h} className={cn(h.startsWith(TODAY) ? "font-medium text-foreground" : "text-muted-foreground")}>
                    {h}
                  </li>
                ))}
              </ul>
            ) : (
              <span className="text-muted-foreground">Not listed</span>
            )}
            {lead.open_today_in_window !== null && lead.open_today_in_window !== undefined && (
              <p className={cn("mt-1 text-xs", lead.open_today_in_window ? "text-good" : "text-muted-foreground")}>
                {lead.open_today_in_window ? "Open during today's calling window" : "Closed during today's calling window"}
              </p>
            )}
          </dd>
        </dl>
        <div>
          <p className="mb-1 text-xs text-muted-foreground">Data quality</p>
          <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {Object.entries(checklist).map(([field, present]) => (
              <li key={field} className={cn("flex items-center gap-1", !present && "text-muted-foreground")}>
                {present ? <CheckIcon className="size-3 text-good" /> : <MinusIcon className="size-3" />}
                {field}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-[11px] text-muted-foreground">
          Source: {lead.provider === "google_places" ? "Google Maps" : lead.provider}
          {lead.source_timestamp && ` · fetched ${formatDateTime(lead.source_timestamp)}`}
          {lead.sources.length > 1 && ` · ${lead.sources.length} listings merged`}
        </p>
      </CardContent>
    </Card>
  );
}

export function GoogleProfileCard({ lead }: { lead: LeadDetail }) {
  const signals = lead.google_signals as { code: string; label: string; severity: string }[];
  if (lead.google_profile_score === null && !signals.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Google Business Profile</CardTitle>
        {lead.google_profile_score !== null && (
          <span className="text-xs text-muted-foreground">
            Completeness <span className="font-medium text-foreground tabular">{lead.google_profile_score}/100</span>
          </span>
        )}
      </CardHeader>
      <CardContent>
        {signals.length ? (
          <ul className="grid gap-1 text-[13px]">
            {signals.map((s) => (
              <li key={s.code} className="flex items-start gap-1.5">
                <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", s.severity === "major" ? "bg-bad" : "bg-ok")} aria-hidden />
                {s.label}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-muted-foreground">No gaps observed in the listing data.</p>
        )}
        <p className="mt-2 text-[11px] text-muted-foreground">
          Review volume is a visibility signal, not a verdict on the business.
        </p>
      </CardContent>
    </Card>
  );
}
