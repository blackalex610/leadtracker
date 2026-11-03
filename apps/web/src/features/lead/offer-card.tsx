import { OFFER_LABELS, type LeadDetail } from "@leadtracker/shared";

import { CategoryBadge, DealValue } from "@/components/app/badges";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMeta } from "@/lib/queries";

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

/** What to sell this lead, for how much, and why — the first thing a caller reads. */
export function OfferCard({ lead }: { lead: LeadDetail }) {
  const meta = useMeta();
  const category = lead.lead_category;
  if (!category) return null;
  const info = meta.data?.lead_categories.find((c) => c.key === category);
  const upsells = strings(lead.category_details.upsells);
  const notes = strings(lead.category_details.fit_notes);
  return (
    <Card>
      <CardHeader>
        <CardTitle>What to sell</CardTitle>
        <CategoryBadge category={category} />
      </CardHeader>
      <CardContent className="grid gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-base font-semibold">{OFFER_LABELS[category]}</p>
          <DealValue value={lead.deal_value} odds={lead.close_odds} className="text-[13px]" />
        </div>
        {lead.category_reason && <p className="text-[13px]">{lead.category_reason}</p>}
        {info && <p className="text-xs text-muted-foreground">{info.description}</p>}
        {(notes.length > 0 || upsells.length > 0) && (
          <div className="grid gap-2 text-xs sm:grid-cols-2">
            {notes.length > 0 && (
              <div>
                <p className="font-medium">Fit</p>
                <ul className="list-disc pl-4 text-muted-foreground">
                  {notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              </div>
            )}
            {upsells.length > 0 && (
              <div>
                <p className="font-medium">Also offer</p>
                <ul className="list-disc pl-4 text-muted-foreground">
                  {upsells.map((u) => (
                    <li key={u}>{u}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
