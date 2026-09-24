import type { SearchRequest } from "@leadtracker/shared";
import { z } from "zod";

const optionalNumber = (min: number, max: number) =>
  z.union([z.nan(), z.number().min(min).max(max)]).optional().transform((v) => (v === undefined || Number.isNaN(v) ? null : v));
const time = z.string().regex(/^([01]?\d|2[0-3]):[0-5]\d$/, "Use HH:MM");

export const searchSchema = z
  .object({
    preset_key: z.string(),
    location: z.string().trim().min(2, "Enter a city"),
    neighborhoods: z.array(z.string()),
    category: z.string().trim().min(2, "Enter a business category"),
    keywords: z.string().trim().max(120),
    min_rating: optionalNumber(0, 5),
    min_reviews: optionalNumber(0, 1_000_000),
    max_reviews: optionalNumber(0, 1_000_000),
    has_website: z.enum(["any", "yes", "no"]),
    open_in_window: z.boolean(),
    window_start: time,
    window_end: time,
    lead_quality: z.enum(["any", "high", "medium", "low"]),
    max_results: z.number().int().min(1).max(2000),
    audit_websites: z.boolean(),
  })
  .refine((v) => v.min_reviews === null || v.max_reviews === null || v.min_reviews <= v.max_reviews, {
    message: "Min reviews must be ≤ max reviews",
    path: ["max_reviews"],
  });
export type SearchFormInput = z.input<typeof searchSchema>;
export type SearchFormValues = z.output<typeof searchSchema>;

export function toSearchRequest(v: SearchFormValues): SearchRequest {
  return {
    category: v.category,
    location: v.location,
    neighborhoods: v.neighborhoods,
    keywords: v.keywords || null,
    preset_key: v.preset_key === "custom" ? null : v.preset_key,
    min_rating: v.min_rating,
    min_reviews: v.min_reviews,
    max_reviews: v.max_reviews,
    has_website: v.has_website,
    open_in_window: v.open_in_window,
    window_start: v.window_start,
    window_end: v.window_end,
    lead_quality: v.lead_quality,
    max_results: v.max_results,
    audit_websites: v.audit_websites,
  };
}

