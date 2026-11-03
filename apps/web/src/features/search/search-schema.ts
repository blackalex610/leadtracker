import type { SearchRequest } from "@leadtracker/shared";
import { z } from "zod";

/** "Find leads" has no niches to pick: the backend's ICP target list decides what to search. */
export const searchSchema = z.object({
  location: z.string().trim().min(2, "Enter a city"),
  target_leads: z.number({ error: "Enter a number" }).int().min(1, "At least 1").max(2000, "At most 2000"),
  max_queries: z.number({ error: "Enter a number" }).int().min(1).max(200),
  use_neighborhoods: z.boolean(),
  audit_websites: z.boolean(),
});
export type SearchFormInput = z.input<typeof searchSchema>;
export type SearchFormValues = z.output<typeof searchSchema>;

export function toSearchRequest(v: SearchFormValues): SearchRequest {
  return {
    location: v.location,
    target_leads: v.target_leads,
    max_queries: v.max_queries,
    use_neighborhoods: v.use_neighborhoods,
    audit_websites: v.audit_websites,
  };
}
