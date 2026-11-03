import {
  CATEGORY_LABELS,
  DATA_QUALITY_LABELS,
  OFFER_LABELS,
  OPPORTUNITY_LABELS,
  PRIORITY_LABELS,
  STATUS_LABELS,
  type DataQuality,
  type LeadCategory,
  type LeadStatus,
  type OpportunityType,
  type Priority,
} from "@leadtracker/shared";
import { FlameIcon, SnowflakeIcon, SunIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { healthTone } from "@/lib/format";
import { cn } from "@/lib/utils";

const PRIORITY_VARIANT = { HOT: "hot", WARM: "warm", COLD: "cold" } as const;
const PRIORITY_ICON = { HOT: FlameIcon, WARM: SunIcon, COLD: SnowflakeIcon } as const;

export function PriorityBadge({ priority, reason, className }: { priority: Priority; reason?: string | null; className?: string }) {
  const Icon = PRIORITY_ICON[priority];
  return (
    <Tooltip content={reason}>
      <Badge variant={PRIORITY_VARIANT[priority]} className={cn("uppercase tracking-wide", className)}>
        <Icon aria-hidden />
        {PRIORITY_LABELS[priority]}
      </Badge>
    </Tooltip>
  );
}

const STATUS_VARIANT: Partial<Record<LeadStatus, "good" | "warm" | "hot" | "muted" | "outline">> = {
  INTERESTED: "good",
  QUALIFIED: "good",
  PROPOSAL: "good",
  WON: "good",
  CALLBACK: "warm",
  DO_NOT_CONTACT: "hot",
  LOST: "muted",
  NEW: "outline",
};

export function StatusBadge({ status }: { status: LeadStatus }) {
  return <Badge variant={STATUS_VARIANT[status] ?? "secondary"}>{STATUS_LABELS[status]}</Badge>;
}

export function OpportunityTags({ types, max = 3, nowrap = false, className }: {
  types: OpportunityType[];
  max?: number;
  nowrap?: boolean;
  className?: string;
}) {
  if (!types.length) return <span className="text-muted-foreground">—</span>;
  const shown = types.slice(0, max);
  const rest = types.slice(max);
  return (
    <div className={cn("flex items-center gap-1", nowrap ? "flex-nowrap" : "flex-wrap", className)}>
      {shown.map((t) => (
        <Badge key={t} variant="outline" className="min-w-0 font-mono text-[10px] font-normal uppercase" title={OPPORTUNITY_LABELS[t]}>
          <span className="truncate">{t}</span>
        </Badge>
      ))}
      {rest.length > 0 && (
        <Tooltip content={rest.map((t) => OPPORTUNITY_LABELS[t]).join(", ")}>
          <span className="text-[11px] text-muted-foreground">+{rest.length}</span>
        </Tooltip>
      )}
    </div>
  );
}

const TONE_CLASS = { bad: "text-bad", ok: "text-ok", good: "text-good", none: "text-muted-foreground" } as const;

export function HealthScore({ score, className }: { score: number | null | undefined; className?: string }) {
  const tone = healthTone(score);
  return (
    <span className={cn("tabular font-medium", TONE_CLASS[tone], className)}>
      {score === null || score === undefined ? "—" : score}
    </span>
  );
}

export function OpportunityScore({ score, className }: { score: number; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 tabular", className)}>
      <span className="relative h-1.5 w-8 overflow-hidden rounded-full bg-muted" aria-hidden>
        <span className="absolute inset-y-0 left-0 rounded-full bg-foreground/70" style={{ width: `${score}%` }} />
      </span>
      <span className="font-medium">{score}</span>
    </span>
  );
}

const QUALITY_VARIANT = { EXCELLENT: "good", GOOD: "secondary", PARTIAL: "warm", POOR: "hot" } as const;

export function DataQualityBadge({ quality }: { quality: DataQuality }) {
  return <Badge variant={QUALITY_VARIANT[quality]}>{DATA_QUALITY_LABELS[quality]}</Badge>;
}

export function Rating({ rating, reviews }: { rating: number | null; reviews: number | null }) {
  if (rating === null) {
    return <span className="text-muted-foreground">{reviews ? `${reviews} reviews` : "—"}</span>;
  }
  return (
    <span className="tabular whitespace-nowrap">
      <span className="font-medium">{rating.toFixed(1)}</span>
      <span className="text-warm"> ★</span>
      {reviews !== null && <span className="text-muted-foreground"> ({reviews})</span>}
    </span>
  );
}

export function DemoBadge() {
  return (
    <Tooltip content="Synthetic demo record — not a real business">
      <Badge variant="muted" className="uppercase">
        Demo
      </Badge>
    </Tooltip>
  );
}

/** Needs a whole website = biggest, easiest deals; site/Google upgrades next; the rest muted. */
const CATEGORY_VARIANT: Record<LeadCategory, "hot" | "warm" | "secondary" | "muted"> = {
  BROKEN_SITE: "hot",
  NO_SITE: "hot",
  SOCIAL_ONLY: "hot",
  NEW_BUSINESS: "hot",
  PLATFORM_ONLY: "warm",
  WEAK_SITE: "warm",
  NO_BOOKING: "warm",
  WEAK_GOOGLE: "secondary",
  UNCHECKED: "muted",
  NOT_A_FIT: "muted",
};

export function CategoryBadge({
  category,
  reason,
  className,
}: {
  category: LeadCategory | null | undefined;
  reason?: string | null;
  className?: string;
}) {
  if (!category) return <span className="text-muted-foreground">—</span>;
  return (
    <Tooltip content={reason ? `${OFFER_LABELS[category]} — ${reason}` : OFFER_LABELS[category]}>
      <Badge variant={CATEGORY_VARIANT[category]} className={cn("whitespace-nowrap", className)}>
        {CATEGORY_LABELS[category]}
      </Badge>
    </Tooltip>
  );
}

/** "€390 · 36%" — the offer price and its close odds. */
export function DealValue({ value, odds, className }: { value: number; odds: number; className?: string }) {
  if (!value) return <span className={cn("text-muted-foreground", className)}>—</span>;
  return (
    <Tooltip content={`Offer price €${value}, estimated close odds ${odds}% → worth €${Math.round((value * odds) / 100)} per lead`}>
      <span className={cn("tabular whitespace-nowrap", className)}>
        <span className="font-semibold">€{value}</span>
        <span className="text-muted-foreground"> · {odds}%</span>
      </span>
    </Tooltip>
  );
}
