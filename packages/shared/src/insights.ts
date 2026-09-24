/**
 * Future AI layer (not used in V1). V1 is fully deterministic; an LLM-backed
 * implementation may later summarize opportunities or draft openers from
 * observed data only. Mirrors `app/insights/base.py` on the backend.
 */
export interface BusinessAnalysisInput {
  name: string;
  category: string | null;
  city: string | null;
  opportunities: string[];
  reasons: string[];
  websiteSignals?: Record<string, unknown>[];
  googleSignals?: Record<string, unknown>[];
  screenshotUrl?: string | null;
}

export interface LeadInsight {
  summary: string;
  openingLine?: string | null;
  redesignAngle?: string | null;
  provider: string;
  confidence?: number | null;
}

export interface LeadInsightProvider {
  readonly name: string;
  analyzeBusiness(input: BusinessAnalysisInput): Promise<LeadInsight>;
}
