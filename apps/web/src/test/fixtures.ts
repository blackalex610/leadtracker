import type {
  CallingCard,
  CallingSession,
  JobOut,
  LeadDetail,
  LeadSummary,
  Meta,
  Preset,
  SettingsOut,
  User,
} from "@leadtracker/shared";

import leadDetailJson from "./data/lead-detail.json";
import metaJson from "./data/meta.json";
import presetsJson from "./data/presets.json";
import settingsJson from "./data/settings.json";

const leadDetail = leadDetailJson as unknown as LeadDetail;

export function makeLead(overrides: Partial<LeadSummary> = {}): LeadSummary {
  return {
    id: 1,
    name: "Bella Nails",
    category: "Nail salon",
    city: "Sofia",
    neighborhood: "Lozenets",
    address: "ul. Krum Popov 5, Sofia",
    international_phone: "+359 88 812 3456",
    national_phone: "088 812 3456",
    normalized_phone: "+359888123456",
    phone_invalid: false,
    rating: 4.8,
    review_count: 217,
    website_url: null,
    website_kind: null,
    website_status: "none",
    website_health_score: null,
    outdated_score: null,
    opportunity_score: 65,
    priority: "HOT",
    opportunity_types: ["NO_WEBSITE", "NO_BOOKING"],
    top_reason: "No website listed",
    status: "NEW",
    suppressed: false,
    is_demo: false,
    data_quality: "GOOD",
    google_maps_url: "https://maps.google.com/?cid=1",
    business_status: "OPERATIONAL",
    open_in_calling_window: true,
    assigned_to_id: null,
    last_contacted_at: null,
    next_callback_at: null,
    call_count: 0,
    created_at: "2026-09-20T10:00:00Z",
    ...overrides,
  };
}

export function makeJob(overrides: Partial<JobOut> = {}): JobOut {
  return {
    id: 7,
    kind: "search",
    status: "completed",
    params: { category: "gyms", location: "Sofia", lead_quality: "any" },
    stage: "done",
    progress_total: 2,
    progress_processed: 2,
    counters: { found: 2, new: 2, matched: 2 },
    errors: [],
    error_code: null,
    error_message: null,
    cancel_requested: false,
    attempts: 1,
    retry_of_id: null,
    created_by_id: 1,
    created_at: "2026-09-24T10:00:00Z",
    started_at: "2026-09-24T10:00:01Z",
    finished_at: "2026-09-24T10:00:30Z",
    ...overrides,
  };
}

export function makeCard(lead: LeadSummary, overrides: Partial<CallingCard> = {}): CallingCard {
  return {
    lead,
    reasons: [{ rule: "no_website", points: 35, text: "No website listed", opportunity: "NO_WEBSITE", tier: "very_strong" }],
    pitch: { language: "en", text: `Hi, I came across ${lead.name}…`, primary_opportunity: "NO_WEBSITE", talking_points: [] },
    hours_today: "Thursday: 9:00 AM – 9:00 PM",
    open_in_window_today: true,
    website_summary: "No website",
    last_call_outcome: null,
    last_call_at: null,
    last_note: null,
    callable: true,
    not_callable_reason: null,
    ...overrides,
  };
}

export function makeSession(cards: CallingCard[]): CallingSession {
  return {
    id: 3,
    filters: { priorities: ["HOT", "WARM"] },
    lead_ids: cards.map((c) => c.lead.id),
    position: 0,
    started_at: "2026-09-24T17:00:00Z",
    ended_at: null,
    stats: { total_calls: 0 },
    cards,
  };
}

export const fixtures = {
  user: {
    id: 1,
    email: "default@leadtracker.local",
    name: "Default user",
    role: "admin",
    is_active: true,
    created_at: "2026-09-01T00:00:00Z",
    last_login_at: null,
  } satisfies User,
  meta: metaJson as unknown as Meta,
  presets: presetsJson as unknown as Preset[],
  settings: settingsJson as unknown as SettingsOut,
  leadDetail,
};
