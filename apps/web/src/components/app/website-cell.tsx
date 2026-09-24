import type { LeadSummary } from "@leadtracker/shared";
import { ExternalLinkIcon } from "lucide-react";

import { displayDomain } from "@/lib/format";

export function WebsiteCell({ lead }: { lead: Pick<LeadSummary, "website_url" | "website_kind" | "website_status"> }) {
  if (!lead.website_url) return <span className="text-muted-foreground">No website</span>;
  const kind =
    lead.website_kind === "social" ? "Social page" : lead.website_kind === "booking_platform" ? "Booking profile" : null;
  return (
    <a
      href={lead.website_url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      onClick={(e) => e.stopPropagation()}
      className="inline-flex max-w-32 items-center gap-1 truncate text-foreground hover:underline"
      title={lead.website_url}
    >
      <span className="truncate">{kind ?? displayDomain(lead.website_url)}</span>
      {lead.website_status === "broken" && <span className="text-bad">(broken)</span>}
      <ExternalLinkIcon className="size-3 shrink-0 text-muted-foreground" aria-hidden />
    </a>
  );
}
