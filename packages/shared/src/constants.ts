import type { CallOutcome, DataQuality, JobStatus, LeadStatus, OpportunityType, Priority, SortField } from "./types";

export const PRIORITY_LABELS: Record<Priority, string> = { HOT: "Hot", WARM: "Warm", COLD: "Cold" };
export const PRIORITIES: Priority[] = ["HOT", "WARM", "COLD"];

export const STATUS_LABELS: Record<LeadStatus, string> = {
  NEW: "New",
  CALLED: "Called",
  NO_ANSWER: "No answer",
  CALLBACK: "Callback",
  INTERESTED: "Interested",
  QUALIFIED: "Qualified",
  PROPOSAL: "Proposal",
  WON: "Won",
  LOST: "Lost",
  DO_NOT_CONTACT: "Do not contact",
};
export const LEAD_STATUSES = Object.keys(STATUS_LABELS) as LeadStatus[];

export const OUTCOME_LABELS: Record<CallOutcome, string> = {
  NO_ANSWER: "No answer",
  INTERESTED: "Interested",
  CALLBACK: "Callback",
  NOT_INTERESTED: "Not interested",
  WRONG_NUMBER: "Wrong number",
  ALREADY_HAS_PROVIDER: "Already has provider",
  DO_NOT_CONTACT: "Do not contact",
};
export const CALL_OUTCOMES = Object.keys(OUTCOME_LABELS) as CallOutcome[];

/** Keyboard shortcuts in calling mode. */
export const OUTCOME_SHORTCUTS: Partial<Record<CallOutcome, string>> = {
  NO_ANSWER: "n",
  CALLBACK: "b",
  INTERESTED: "i",
  NOT_INTERESTED: "x",
  DO_NOT_CONTACT: "d",
};

export const OPPORTUNITY_LABELS: Record<OpportunityType, string> = {
  NO_WEBSITE: "No website",
  BROKEN_WEBSITE: "Broken website",
  OUTDATED_WEBSITE: "Outdated website",
  WEBSITE_REDESIGN: "Website redesign",
  MOBILE_PROBLEM: "Mobile problem",
  NO_BOOKING: "No online booking",
  NO_CONTACT_CTA: "No contact CTA",
  WEAK_CONVERSION: "Weak conversion",
  SLOW_WEBSITE: "Slow website",
  GOOGLE_PROFILE: "Google profile gaps",
  LOW_REVIEWS: "Low reviews",
  MISSING_BUSINESS_INFO: "Missing business info",
};
export const OPPORTUNITY_TYPES = Object.keys(OPPORTUNITY_LABELS) as OpportunityType[];

export const DATA_QUALITY_LABELS: Record<DataQuality, string> = {
  EXCELLENT: "Excellent",
  GOOD: "Good",
  PARTIAL: "Partial",
  POOR: "Poor",
};

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  partial: "Partially completed",
  failed: "Failed",
  cancelled: "Cancelled",
};
export const ACTIVE_JOB_STATUSES: JobStatus[] = ["queued", "running"];

export const SORT_LABELS: Record<SortField, string> = {
  priority: "Priority",
  opportunity_score: "Opportunity score",
  website_score: "Website score",
  review_count: "Reviews",
  rating: "Rating",
  name: "Name",
  created_at: "Date added",
  last_contacted_at: "Last contacted",
  next_callback_at: "Next callback",
};

export const WEBSITE_STATUS_LABELS: Record<string, string> = {
  none: "No website",
  unaudited: "Not audited",
  ok: "Audited",
  broken: "Broken",
  skipped: "Audit skipped",
};

export const JOB_STAGE_LABELS: Record<string, string> = {
  queued: "Waiting for a worker",
  requeued: "Waiting for a worker",
  starting: "Starting",
  searching: "Searching businesses",
  auditing: "Auditing websites",
  scoring: "Scoring leads",
  cancelled: "Cancelled",
  done: "Done",
  failed: "Failed",
};
