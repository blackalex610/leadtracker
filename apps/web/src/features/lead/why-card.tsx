import { OPPORTUNITY_LABELS, type LeadDetail } from "@leadtracker/shared";

import { DataQualityBadge, OpportunityScore } from "@/components/app/badges";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TIER_LABEL: Record<string, string> = {
  very_strong: "very strong",
  strong: "strong",
  moderate: "moderate",
  contextual: "context",
};

export function WhyCard({ lead }: { lead: LeadDetail }) {
  const opportunities = lead.score_reasons.filter((r) => r.opportunity);
  const context = lead.score_reasons.filter((r) => !r.opportunity && r.tier !== "note");
  const notes = lead.score_reasons.filter((r) => r.tier === "note");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Why this lead?</CardTitle>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          Opportunity score <OpportunityScore score={lead.opportunity_score} />
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        {opportunities.length ? (
          <ol className="grid gap-1.5">
            {opportunities.map((r, i) => (
              <li key={`${r.rule}-${i}`} className="grid grid-cols-[1.25rem_1fr_auto] items-baseline gap-2">
                <span className="text-xs text-muted-foreground tabular">{i + 1}.</span>
                <span className="text-[13px]">
                  <span className="font-medium">{r.text}</span>
                  {r.opportunity && (
                    <Badge variant="outline" className="ml-2 font-mono text-[10px] font-normal">
                      {r.opportunity}
                    </Badge>
                  )}
                </span>
                <span className="text-xs text-muted-foreground tabular" title={TIER_LABEL[r.tier] ?? r.tier}>
                  +{r.points}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-[13px] text-muted-foreground">No concrete opportunity observed yet.</p>
        )}
        {context.length > 0 && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 border-t pt-2 text-xs text-muted-foreground">
            {context.map((r, i) => (
              <span key={`${r.rule}-${i}`}>
                {r.text} <span className="tabular">+{r.points}</span>
              </span>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {lead.priority_reason && <span>{lead.priority_reason}</span>}
          <span className="flex items-center gap-1">
            Data quality <DataQualityBadge quality={lead.data_quality} />
          </span>
        </div>
        {notes.length > 0 && (
          <ul className="text-xs text-muted-foreground">
            {notes.map((n, i) => (
              <li key={i}>· {n.text}</li>
            ))}
          </ul>
        )}
        <p className="sr-only">
          Opportunities: {lead.opportunity_types.map((o) => OPPORTUNITY_LABELS[o]).join(", ")}
        </p>
      </CardContent>
    </Card>
  );
}
