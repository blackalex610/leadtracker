import type { CallingFilters, LeadCategory, Priority } from "@leadtracker/shared";
import { z } from "zod";

const time = z.string().regex(/^([01]?\d|2[0-3]):[0-5]\d$/, "Use HH:MM");

export const callingSchema = z.object({
  categories: z.array(z.string()),
  target_key: z.string(),
  city: z.string().max(120),
  window_start: time,
  window_end: time,
  open_today: z.boolean(),
  priorities: z.array(z.enum(["HOT", "WARM", "COLD"])),
  website: z.enum(["any", "none", "poor"]),
  limit: z.number().int().min(1).max(500),
  include_unknown_hours: z.boolean(),
});
export type CallingFormValues = z.infer<typeof callingSchema>;

export function toCallingFilters(values: CallingFormValues): Partial<CallingFilters> {
  return {
    categories: values.categories as LeadCategory[],
    target_key: values.target_key === "any" ? null : values.target_key,
    city: values.city.trim() || null,
    window_start: values.window_start,
    window_end: values.window_end,
    open_today: values.open_today,
    priorities: values.priorities as Priority[],
    website: values.website,
    limit: values.limit,
    include_unknown_hours: values.include_unknown_hours,
  };
}

